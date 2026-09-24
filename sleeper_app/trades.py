"""Package search and evidence-based league context, without market-value claims."""

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from statistics import fmean, median

from sleeper_app.analysis import (active_players, number, opponents,
                                  optimize_lineup, player_name, starter_slots, unavailable)


@dataclass(frozen=True)
class TradeFilters:
    min_weeks: int = 2
    min_gain: float = 0.5
    max_gap: float = 0.35
    partner_loss: float = 0.0
    depth_weight: float = 0.15
    include_packages: bool = True
    include_specialists: bool = False
    draft_gap: int = 2


class PackageEvaluator:
    """Reoptimize both rosters, explicitly trimming any active-roster overflow.

    Incoming players cannot immediately be dropped. Cuts maximize retained roster
    utility, NOT simply the lowest raw score (positional eligibility matters).
    Open spots get no fabricated waiver-player value. IR/taxi players stay separate.
    """

    def __init__(self, slots, players, scores, capacity, excluded=None, depth_weight=0.15):
        self.slots, self.players, self.scores = slots, players, scores
        self.capacity = capacity
        self.excluded = set(excluded or [])
        self.depth_weight = depth_weight

        @lru_cache(maxsize=20000)
        def lineup(ids):
            return optimize_lineup(list(ids), slots, players, scores, self.excluded)

        self.lineup = lineup

    def utility(self, ids, lineup):
        return lineup.total + self.depth_weight * sum(
            max(0.0, self.scores.get(p) or 0.0) for p in ids
            if p not in lineup.assignments and p not in self.excluded)

    def trim(self, ids, protected):
        excess = max(0, len(ids) - self.capacity)
        if excess > 2:
            raise ValueError("Roster overflow exceeds the supported two-cut scenario.")
        choices = combinations([p for p in ids if p not in protected], excess)
        best = None
        for cuts in choices:
            kept = tuple(sorted(set(ids) - set(cuts)))
            lineup = self.lineup(kept)
            if lineup.missing:
                continue
            utility = self.utility(kept, lineup)
            if best is None or utility > best[0]:
                best = (utility, list(kept), lineup, list(cuts))
        if best is None:
            raise ValueError("No full legal lineup remains after necessary roster cuts.")
        return best

    def evaluate(self, mine, theirs, give, receive, keep=None):
        if not give or not receive or max(len(give), len(receive)) > 3:
            raise ValueError("Select one to three players on each side.")
        if len(set(give)) != len(give) or len(set(receive)) != len(receive):
            raise ValueError("Packages cannot contain duplicate players.")
        if not set(give) <= set(mine) or not set(receive) <= set(theirs) or set(mine) & set(theirs):
            raise ValueError("Trade players must belong to their respective active rosters.")
        if any(number(self.scores.get(p)) is None or p in self.excluded for p in give + receive):
            raise ValueError("Every traded player needs a finite estimate and must not be excluded.")
        if max(len(mine), len(theirs)) > self.capacity:
            raise ValueError("An active roster is already over capacity. Resolve this in Sleeper before evaluating trades.")
        mb, tb = (self.lineup(tuple(sorted(ids))) for ids in (mine, theirs))
        if mb.missing or tb.missing:
            raise ValueError("Both teams need a full eligible, scored starting lineup before a trade.")
        mine_after = [p for p in mine if p not in give] + receive
        theirs_after = [p for p in theirs if p not in receive] + give
        mu, mine_after, ma, my_cuts = self.trim(mine_after, set(receive) | set(keep or []))
        tu, theirs_after, ta, their_cuts = self.trim(theirs_after, set(give))
        a, b = (sum(abs(self.scores[p]) for p in package) for package in (give, receive))
        return {"give": list(give), "receive": list(receive), "my_before": mb, "my_after": ma,
                "their_before": tb, "their_after": ta, "my_gain": ma.total - mb.total,
                "their_gain": ta.total - tb.total, "my_utility": mu - self.utility(mine, mb),
                "their_utility": tu - self.utility(theirs, tb), "value_gap": abs(a - b) / max(a, b, 1.0),
                "my_cuts": my_cuts, "their_cuts": their_cuts, "my_players_after": mine_after,
                "their_players_after": theirs_after, "my_open_slots": self.capacity - len(mine_after),
                "their_open_slots": self.capacity - len(theirs_after)}


def roster_capacity(league):
    return sum(s not in {"IR", "TAXI", "RESERVE"} for s in league.get("roster_positions", []))


def draft_compatible(give, receive, rounds, gap):
    if rounds is None:
        return True
    if any(p not in rounds for p in give + receive):
        return False
    # Compare the most expensive pick on each side; never sum ordinal rounds.
    return abs(min(rounds[p] for p in give) - min(rounds[p] for p in receive)) <= gap


def search_packages(rosters, my_id, league, players, scores, metrics, excluded, untouchable,
                    filters=None, anchor=None, targets=None, draft_rounds=None):
    """All eligible 1:1 and (optionally) 2:1 offers; anchor stays in every offer.

    Search considers two of MY players for one target, not 1:2 or arbitrary 2:2.
    No candidate truncation before evaluation. Top results can be limited by the UI.
    """
    filters = filters or TradeFilters()
    mine = active_players(next(r for r in rosters if r["roster_id"] == my_id))

    def supported(p):
        return (p not in excluded and number(scores.get(p)) is not None
                and metrics.get(p, {}).get("weeks", 0) >= filters.min_weeks
                and (filters.include_specialists or players.get(p, {}).get("position") in {"QB", "RB", "WR", "TE"}))

    senders = [p for p in mine if p not in untouchable and supported(p)]
    if anchor is not None and anchor not in senders:
        return []
    if targets is not None and not targets:
        return []
    packages = [[p] for p in senders if anchor is None or p == anchor]
    if filters.include_packages:
        packages += [list(pair) for pair in combinations(senders, 2) if anchor is None or anchor in pair]
    evaluator = PackageEvaluator(starter_slots(league), players, scores, roster_capacity(league), excluded, filters.depth_weight)
    results = []
    for roster in rosters:
        if roster["roster_id"] == my_id or not roster.get("owner_id"):
            continue
        theirs = active_players(roster)
        for target in theirs:
            if not supported(target) or (targets is not None and target not in targets):
                continue
            for give in packages:
                receive = [target]
                if not draft_compatible(give, receive, draft_rounds, filters.draft_gap):
                    continue
                a, b = sum(abs(scores[p]) for p in give), abs(scores[target])
                if abs(a - b) / max(a, b, 1.0) > filters.max_gap:
                    continue
                try:
                    trade = evaluator.evaluate(mine, theirs, give, receive, untouchable)
                except ValueError:
                    continue
                if (trade["my_gain"] >= filters.min_gain and trade["my_utility"] > 0
                        and trade["their_utility"] >= -filters.partner_loss):
                    results.append({**trade, "roster_id": roster["roster_id"], "anchor": anchor})
    return sorted(results, key=lambda t: (t["my_utility"], t["their_utility"], -len(t["give"])), reverse=True)


def standings(rosters, names):
    rows = []
    for roster in rosters:
        s = roster.get("settings") or {}
        w, l, t = (int(s.get(k) or 0) for k in ("wins", "losses", "ties"))
        pf = float(s.get("fpts") or 0) + float(s.get("fpts_decimal") or 0) / 100
        pa = float(s.get("fpts_against") or 0) + float(s.get("fpts_against_decimal") or 0) / 100
        pct = (w + t / 2) / (w + l + t) if w + l + t else None
        rows.append({"roster_id": roster["roster_id"], "Team": names.get(roster["roster_id"], str(roster["roster_id"])),
                     "Record": f"{w}-{l}-{t}", "Wins": w, "Losses": l, "Win rate": pct,
                     "Points for": pf, "Points against": pa, "Streak": (roster.get("metadata") or {}).get("streak", "—")})
    rows.sort(key=lambda r: (r["Win rate"] if r["Win rate"] is not None else -1, r["Points for"]), reverse=True)
    previous, rank = None, 0
    for index, row in enumerate(rows, 1):
        key = (row["Win rate"], row["Points for"])
        if key != previous:
            rank = index
        row["Table rank"] = rank
        previous = key
    return rows


def slot_averages(lineup, slots, scores):
    result = {}
    for slot in dict.fromkeys(slots):
        entries = [scores.get(p) for s, p in zip(slots, lineup.assignments) if s == slot]
        result[slot] = fmean(entries) if entries and all(v is not None for v in entries) else None
    return result


def depth_risks(ids, slots, players, scores, excluded):
    base = optimize_lineup(ids, slots, players, scores, excluded)
    if base.missing:
        return []
    risks = []
    for pid in base.assignments:
        after = optimize_lineup(ids, slots, players, scores, set(excluded) | {pid})
        risks.append({"Player": player_name(pid, players), "id": pid,
                      "Model score lost": None if after.missing else base.total - after.total,
                      "Unfilled slots if absent": ", ".join(after.missing)})
    return sorted(risks, key=lambda r: (bool(r["Unfilled slots if absent"]), r["Model score lost"] or 0), reverse=True)


def league_context(snapshot, my_id, scores, excluded, horizon=3):
    """Current standings + finalized scoring + static upcoming fantasy matchup scenarios."""
    rosters, players, league = snapshot["rosters"], snapshot["players"], snapshot["league"]
    slots, names = starter_slots(league), snapshot["names"]
    mine = next(r for r in rosters if r["roster_id"] == my_id)
    lineups = {r["roster_id"]: optimize_lineup(active_players(r), slots, players, scores, excluded) for r in rosters}
    averages = {rid: slot_averages(lineup, slots, scores) for rid, lineup in lineups.items()}
    needs = []
    for slot, value in averages[my_id].items():
        peers = [av[slot] for rid, av in averages.items() if rid != my_id and av[slot] is not None]
        typical = median(peers) if peers else None
        needs.append({"Slot group": slot, "Your model / slot": value, "Peer median / slot": typical,
                      "Gap / slot": value - typical if value is not None and typical is not None else None})
    table = standings(rosters, names)
    my_standing = next(r for r in table if r["roster_id"] == my_id)
    weekly = []
    for week, matches in sorted(snapshot["history"].items()):
        values = {}
        for matchup in matches:
            points = matchup.get("custom_points")
            if points is None:
                points = matchup.get("points")
            points = number(points)
            if points is not None:
                values[matchup["roster_id"]] = points
        if my_id in values:
            weekly.append({"Week": week, "Actual points": values[my_id],
                           "League median": median(values.values()),
                           "Weekly scoring rank": 1 + sum(v > values[my_id] for v in values.values())})
    trend = None
    if len(weekly) >= 2:
        split = min(2, len(weekly) // 2)
        trend = fmean(r["Actual points"] for r in weekly[-split:]) - fmean(r["Actual points"] for r in weekly[-2 * split:-split])
    upcoming = []
    for week, matches in sorted(snapshot.get("schedule", {}).items())[:horizon]:
        _, rivals = opponents(matches, my_id)
        if not rivals:
            upcoming.append({"Week": week, "Opponent": "Not assigned / bye", "Model gap": None})
        for rival in rivals:
            rid = rival["roster_id"]
            other = lineups.get(rid)
            gap = lineups[my_id].total - other.total if other and not other.missing and not lineups[my_id].missing else None
            upcoming.append({"Week": week, "Opponent": names.get(rid, str(rid)), "Model gap": gap})
    underdogs = sum(r["Model gap"] is not None and r["Model gap"] < 0 for r in upcoming)
    below_median = sum(r["Actual points"] < r["League median"] for r in weekly)
    risks = depth_risks(active_players(mine), slots, players, scores, excluded)
    pressure = (my_standing["Losses"] > my_standing["Wins"] or underdogs > 0
                or (bool(weekly) and below_median > len(weekly) / 2))
    return {"standings": table, "standing": my_standing, "needs": needs, "weekly": weekly,
            "trend": trend, "upcoming": upcoming, "risks": risks, "underdogs": underdogs,
            "pressure": pressure, "injured": [p for p in (mine.get("players") or []) if unavailable(p, players)],
            "missing": lineups[my_id].missing, "slot_averages": averages, "slots": slots}


def contextualize(ideas, context, snapshot, scores):
    """Rank supported offers by roster gaps; standings change priority, not player value."""
    ranked = []
    for trade in ideas:
        after = slot_averages(trade["my_after"], context["slots"], scores)
        repairs = []
        repair_points = 0.0
        for need in context["needs"]:
            before, typical, value = need["Your model / slot"], need["Peer median / slot"], after[need["Slot group"]]
            if before is not None and typical is not None and value is not None and before < typical and value > before:
                repair_points += min(typical - before, value - before)
                repairs.append(f"{need['Slot group']} rises from {before:.2f} to {value:.2f} per slot (peer median {typical:.2f}).")
        reasons = repairs or [f"Your optimized starter output improves by {trade['my_gain']:.2f} model points."]
        rank = context["standing"]["Table rank"]
        reasons.append(f"Current table position {rank}/{len(context['standings'])}, record {context['standing']['Record']}; not an official playoff seed.")
        if context["trend"] is not None:
            reasons.append(f"Recent finalized team scoring changed {context['trend']:+.2f} points between consecutive windows.")
        if context["underdogs"]:
            reasons.append(f"{context['underdogs']} upcoming fantasy matchup scenario(s) currently have a negative model gap; starter improvement takes priority.")
        if len(trade["give"]) > len(trade["receive"]):
            reasons.append("Consolidation costs bench depth and leaves an open spot; no future waiver replacement is assumed.")
        partner_before = context["slot_averages"].get(trade["roster_id"], {})
        partner_after = slot_averages(trade["their_after"], context["slots"], scores)
        helped = [s for s, value in partner_after.items() if value is not None and partner_before.get(s) is not None and value > partner_before[s] + 0.01]
        reasons.append("Partner fit: " + ("improves " + ", ".join(helped) + " slots." if helped else f"depth-adjusted utility changes {trade['their_utility']:+.2f}; starter improvement is not assured."))
        priority = trade["my_utility"] + repair_points + (trade["my_gain"] if context["pressure"] else 0)
        ranked.append({**trade, "reasons": reasons, "priority": priority})
    return sorted(ranked, key=lambda t: (t["priority"], t["their_utility"]), reverse=True)