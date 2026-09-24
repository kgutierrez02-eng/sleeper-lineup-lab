"""Transparent historical baselines, exact slot assignment, and bilateral trade fit.

No external rankings, fabricated stats, official projections, or acceptance probabilities.
"""

from dataclasses import dataclass
from itertools import product
import math
from statistics import fmean, pstdev

import numpy as np
from scipy.optimize import linear_sum_assignment


NON_STARTER = {"BN", "IR", "TAXI", "RESERVE"}
FLEX = {"FLEX": {"RB", "WR", "TE"}, "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
        "REC_FLEX": {"WR", "TE"}, "WRRB_FLEX": {"RB", "WR"},
        "IDP_FLEX": {"DL", "LB", "DB", "DE", "DT", "NT", "OLB", "ILB", "CB", "S", "FS", "SS"},
        "DL": {"DL", "DE", "DT", "NT"}, "LB": {"LB", "OLB", "ILB"},
        "DB": {"DB", "CB", "S", "FS", "SS"}}
UNAVAILABLE = {"out", "ir", "injured reserve", "pup", "suspended", "susp", "doubtful", "d", "o"}


def number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def player_name(pid: str, players: dict) -> str:
    p = players.get(pid, {})
    return p.get("full_name") or " ".join(filter(None, [p.get("first_name"), p.get("last_name")])) or pid


def positions(pid: str, players: dict) -> set[str]:
    p = players.get(pid, {})
    return {str(pos).upper() for pos in (p.get("fantasy_positions") or [p.get("position")]) if pos}


def eligible(pid: str, slot: str, players: dict) -> bool:
    return bool(positions(pid, players) & FLEX.get(slot, {slot}))


def starter_slots(league: dict) -> list[str]:
    return [s for s in league.get("roster_positions", []) if s not in NON_STARTER]


def active_players(roster: dict) -> list[str]:
    inactive = set(roster.get("reserve") or []) | set(roster.get("taxi") or [])
    return list(dict.fromkeys(str(p) for p in (roster.get("players") or []) if p and p != "0" and p not in inactive))


def unavailable(pid: str, players: dict) -> bool:
    p = players.get(pid, {})
    return any(str(p.get(key) or "").casefold() in UNAVAILABLE for key in ("injury_status", "status"))


def history_points(history: dict[int, list[dict]]) -> dict[str, dict[int, float]]:
    result: dict[str, dict[int, float]] = {}
    for week, matchups in sorted(history.items()):
        for matchup in matchups:
            # A missing field is NOT a zero. Exact reported zeros ARE observations;
            # this API cannot distinguish a bye/DNP from an actual zero-point game.
            for pid, value in (matchup.get("players_points") or {}).items():
                point = number(value)
                if point is not None:
                    result.setdefault(str(pid), {})[week] = point
    return result


@dataclass(frozen=True)
class ModelSettings:
    decay: float = 0.8
    prior_weeks: float = 2.0
    risk: float = 0.0
    questionable_discount: float = 0.10


def build_metrics(players: dict, ids: list[str], history: dict, settings: ModelSettings) -> dict[str, dict]:
    series = history_points(history)
    # One mean per player; not one observation per week. Only league-observed players.
    pools: dict[str, list[float]] = {}
    for pid, weekly in series.items():
        for pos in positions(pid, players):
            pools.setdefault(pos, []).append(fmean(weekly.values()))
    latest = max(history, default=0)
    result = {}
    for pid in dict.fromkeys(ids):
        p = players.get(pid, {})
        samples = series.get(pid, {})
        values = list(samples.values())
        weights = [settings.decay ** (latest - w) for w in samples]
        weight = sum(weights)
        weighted = sum(v * w for v, w in zip(values, weights)) / weight if weight else None
        primary = p.get("position") or next(iter(sorted(positions(pid, players))), "UNK")
        # Do not invent estimates for rookies/newly rostered players with no evidence.
        prior = fmean(pools[primary]) if pools.get(primary) else weighted
        baseline = None
        if weighted is not None:
            baseline = (weighted * weight + (prior if prior is not None else weighted) * settings.prior_weeks) / (weight + settings.prior_weeks)
        spread = pstdev(values) if len(values) >= 2 else None
        adjustment = settings.risk * (spread or 0)
        score = None if baseline is None else baseline + adjustment
        status = p.get("injury_status") or p.get("status") or "Unknown"
        if score is not None and str(status).casefold() in {"questionable", "q"}:
            score -= abs(score) * settings.questionable_discount
        result[pid] = {"id": pid, "name": player_name(pid, players), "position": primary,
                       "team": p.get("team") or "—", "status": status,
                       "practice": p.get("practice_participation") or "Not provided",
                       "depth": p.get("depth_chart_order"), "age": p.get("age"),
                       "experience": p.get("years_exp"), "news_updated": p.get("news_updated"),
                       "weeks": len(values), "mean": fmean(values) if values else None,
                       "recent": samples[max(samples)] if samples else None,
                       "weighted": weighted, "stdev": spread, "baseline": baseline, "score": score,
                       "history": samples, "evidence": "None" if not values else "Very low (1 week)" if len(values) == 1 else "Limited (2–3 weeks)" if len(values) < 4 else "4+ observed weeks"}
    return result


@dataclass
class Lineup:
    assignments: list[str | None]
    total: float
    missing: list[str]


def optimize_lineup(ids: list[str], slots: list[str], players: dict, scores: dict[str, float | None],
                    excluded: set[str] | None = None, locks: dict[int, str] | None = None) -> Lineup:
    """Maximum-weight bipartite assignment; FLEX and duplicate slots handled exactly.

    Empty slots cost far more than negative player scores, so a legal negative-scoring
    player fills a required slot. Locked players remain in their exact slot.
    """
    ids = list(dict.fromkeys(ids))
    excluded = excluded or set()
    locks = locks or {}
    if len(set(locks.values())) != len(locks):
        raise ValueError("A player cannot be locked into two slots.")
    for index, pid in locks.items():
        if index not in range(len(slots)) or pid not in ids or pid in excluded:
            raise ValueError("A locked player is excluded, inactive, or not on this roster.")
        if not eligible(pid, slots[index], players):
            raise ValueError(f"{player_name(pid, players)} cannot fill {slots[index]}.")
        if scores.get(pid) is None:
            raise ValueError(f"{player_name(pid, players)} has no estimate. Enter a manual override to lock this player.")
    assigned: list[str | None] = [None] * len(slots)
    for index, pid in locks.items():
        assigned[index] = pid
    remaining = [i for i in range(len(slots)) if i not in locks]
    candidates = [p for p in ids if p not in excluded and p not in locks.values() and scores.get(p) is not None]
    if remaining:
        matrix = np.full((len(remaining), len(candidates) + len(remaining)), -1e9)
        for row, index in enumerate(remaining):
            matrix[row, len(candidates):] = -1e6
            for col, pid in enumerate(candidates):
                if eligible(pid, slots[index], players):
                    matrix[row, col] = scores[pid]
        rows, cols = linear_sum_assignment(matrix, maximize=True)
        for row, col in zip(rows, cols):
            if col < len(candidates) and matrix[row, col] > -1e6:
                assigned[remaining[row]] = candidates[col]
    total = sum(float(scores[p]) for p in assigned if p is not None)
    missing = [f"{i + 1}. {slots[i]}" for i, pid in enumerate(assigned) if pid is None]
    return Lineup(assigned, total, missing)


def opponents(matchups: list[dict], roster_id: int) -> tuple[dict | None, list[dict]]:
    mine = next((m for m in matchups if m.get("roster_id") == roster_id), None)
    if not mine or mine.get("matchup_id") is None:
        return mine, []
    return mine, [m for m in matchups if m.get("matchup_id") == mine["matchup_id"] and m.get("roster_id") != roster_id]


def evaluate_trade(mine: list[str], theirs: list[str], give: list[str], receive: list[str],
                   slots: list[str], players: dict, scores: dict, excluded: set[str] | None = None,
                   depth_weight: float = 0.15) -> dict:
    """Equal-size active-roster packages; no implicit drops, picks, or IR promotions."""
    if not give or len(give) != len(receive) or len(set(give)) != len(give) or len(set(receive)) != len(receive):
        raise ValueError("Choose equal-size, nonempty packages with no duplicate players.")
    if not set(give) <= set(mine) or not set(receive) <= set(theirs) or set(mine) & set(theirs):
        raise ValueError("Trade players must belong to their respective active rosters.")
    excluded = excluded or set()
    if any(scores.get(pid) is None or pid in excluded for pid in give + receive):
        raise ValueError("Every trade player needs an estimate and must not be excluded.")
    mine_after = [p for p in mine if p not in give] + receive
    theirs_after = [p for p in theirs if p not in receive] + give
    mb, ma, tb, ta = [optimize_lineup(ids, slots, players, scores, excluded) for ids in (mine, mine_after, theirs, theirs_after)]
    if any(lineup.missing for lineup in (mb, ma, tb, ta)):
        raise ValueError("Insufficient eligible, scored players to fill both teams before and after this trade.")

    def utility(ids, lineup):
        bench = sum(max(0.0, scores.get(p) or 0.0) for p in ids if p not in lineup.assignments and p not in excluded)
        return lineup.total + depth_weight * bench

    give_value = sum(abs(scores[p]) for p in give)
    get_value = sum(abs(scores[p]) for p in receive)
    gap = abs(give_value - get_value) / max(give_value, get_value, 1.0)
    return {"give": give, "receive": receive, "my_before": mb, "my_after": ma,
            "their_before": tb, "their_after": ta, "my_gain": ma.total - mb.total,
            "their_gain": ta.total - tb.total,
            "my_utility": utility(mine_after, ma) - utility(mine, mb),
            "their_utility": utility(theirs_after, ta) - utility(theirs, tb), "value_gap": gap}


def suggest_trades(rosters: list[dict], my_id: int, slots: list[str], players: dict, scores: dict,
                   excluded: set[str], untouchable: set[str], depth_weight: float = 0.15,
                   max_gap: float = 0.35, min_gain: float = 0.5, partner_loss: float = 0.0,
                   targets: set[str] | None = None, *, draft_rounds: dict[str, int] | None = None,
                   max_draft_round_gap: int = 2) -> list[dict]:
    mine = active_players(next(r for r in rosters if r["roster_id"] == my_id))
    results = []
    give_options = [p for p in mine if p not in untouchable | excluded and scores.get(p) is not None]
    for roster in rosters:
        if roster["roster_id"] == my_id or not roster.get("owner_id"):
            continue
        theirs = active_players(roster)
        get_options = [p for p in theirs if p not in excluded and scores.get(p) is not None and (not targets or p in targets)]
        for give, receive in product(give_options, get_options):
            # Optional historical draft-cost guard, deliberately NOT a market valuation.
            # Fail closed on missing draft data rather than silently treating it as fair.
            if draft_rounds is not None:
                if give not in draft_rounds or receive not in draft_rounds:
                    continue
                if abs(draft_rounds[give] - draft_rounds[receive]) > max_draft_round_gap:
                    continue
            # A quick magnitude filter keeps the full bilateral optimization inexpensive.
            a, b = abs(scores[give]), abs(scores[receive])
            if abs(a - b) / max(a, b, 1.0) > max_gap:
                continue
            try:
                trade = evaluate_trade(mine, theirs, [give], [receive], slots, players, scores, excluded, depth_weight)
            except ValueError:
                continue
            if trade["my_gain"] >= min_gain and trade["my_utility"] > 0 and trade["their_utility"] >= -partner_loss:
                results.append({**trade, "roster_id": roster["roster_id"]})
    return sorted(results, key=lambda t: (t["my_utility"], t["their_utility"]), reverse=True)