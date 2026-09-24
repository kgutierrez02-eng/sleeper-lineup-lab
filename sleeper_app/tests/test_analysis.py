from itertools import permutations
import random

import pytest

from sleeper_app.analysis import (ModelSettings, active_players, build_metrics, eligible,
                                  evaluate_trade, history_points, opponents, optimize_lineup,
                                  starter_slots, suggest_trades, unavailable)


def player(pos, **kwargs):
    return {"position": pos, "fantasy_positions": [pos], **kwargs}


def test_exact_assignment_handles_flex_and_duplicate_slots():
    players = {"a": player("RB"), "b": player("RB"), "c": player("WR"), "d": player("TE")}
    result = optimize_lineup(list(players), ["FLEX", "RB", "RB"], players,
                             {"a": 20, "b": 19, "c": 18, "d": 10})
    assert result.total == 57
    assert result.assignments[0] == "c"
    assert not result.missing


def test_assignment_matches_brute_force():
    rng = random.Random(17)
    for _ in range(20):
        players = {str(i): player(pos) for i, pos in enumerate(["QB", "RB", "RB", "WR", "WR", "TE"])}
        scores = {pid: rng.uniform(-10, 40) for pid in players}
        slots = ["RB", "WR", "FLEX", "SUPER_FLEX"]
        expected = max(sum(scores[p] for p in combo) for combo in permutations(players, 4)
                       if all(eligible(p, s, players) for p, s in zip(combo, slots)))
        actual = optimize_lineup(list(players), slots, players, scores)
        assert actual.total == pytest.approx(expected)


def test_negative_scores_still_fill_required_slots():
    result = optimize_lineup(["a"], ["DEF"], {"a": player("DEF")}, {"a": -7})
    assert result.assignments == ["a"]
    assert result.total == -7


def test_missing_metrics_not_zero_filled():
    metrics = build_metrics({"a": player("RB"), "b": player("RB")}, ["a", "b"],
                            {1: [{"players_points": {"a": 0}}]}, ModelSettings())
    assert metrics["a"]["weeks"] == 1
    assert metrics["a"]["score"] == 0
    assert metrics["b"]["score"] is None
    result = optimize_lineup(["b"], ["RB"], {"b": player("RB")}, {"b": None})
    assert result.missing == ["1. RB"]


def test_history_preserves_zero_negative_and_ignores_invalid():
    history = {1: [{"players_points": {"a": 0, "b": -2, "c": None, "d": float("nan"), "e": True}}, {}],
               2: [{"players_points": {"a": 12}}]}
    assert history_points(history) == {"a": {1: 0.0, 2: 12.0}, "b": {1: -2.0}}


def test_weighted_mean_and_no_target_inputs():
    metrics = build_metrics({"a": player("QB")}, ["a"],
                            {1: [{"players_points": {"a": 10}}], 2: [{"players_points": {"a": 20}}]},
                            ModelSettings(decay=0.5, prior_weeks=0))
    assert metrics["a"]["score"] == pytest.approx(50 / 3)
    assert metrics["a"]["stdev"] == 5


def test_one_week_cannot_claim_volatility():
    m = build_metrics({"a": player("RB")}, ["a"], {1: [{"players_points": {"a": 20}}]}, ModelSettings(risk=1))["a"]
    assert m["stdev"] is None
    assert m["score"] == 20
    assert "1 week" in m["evidence"]


def test_injuries_reserve_taxi_and_exclusions():
    roster = {"players": ["a", "b", "c", "d"], "reserve": ["b"], "taxi": ["c"]}
    assert active_players(roster) == ["a", "d"]
    players = {"a": player("RB", injury_status="Out"), "d": player("RB")}
    assert unavailable("a", players)
    result = optimize_lineup(active_players(roster), ["RB"], players, {"a": 100, "d": 4}, {"a"})
    assert result.assignments == ["d"]


def test_exact_slot_locks_and_conflicts():
    players = {"a": player("RB"), "b": player("RB"), "c": player("WR")}
    scores = {"a": 1, "b": 20, "c": 30}
    result = optimize_lineup(list(players), ["RB", "FLEX"], players, scores, locks={1: "a"})
    assert result.assignments == ["b", "a"]
    with pytest.raises(ValueError, match="two slots"):
        optimize_lineup(list(players), ["RB", "FLEX"], players, scores, locks={0: "a", 1: "a"})
    with pytest.raises(ValueError, match="excluded"):
        optimize_lineup(list(players), ["RB"], players, scores, {"a"}, {0: "a"})
    with pytest.raises(ValueError, match="cannot fill"):
        optimize_lineup(list(players), ["RB"], players, scores, locks={0: "c"})
    with pytest.raises(ValueError, match="no estimate"):
        optimize_lineup(["a"], ["RB"], players, {"a": None}, locks={0: "a"})


def test_multi_position_and_idp():
    players = {"x": {"fantasy_positions": ["WR", "RB"]}, "d": player("DE")}
    assert eligible("x", "RB", players)
    assert eligible("x", "REC_FLEX", players)
    assert eligible("d", "DL", players)
    assert eligible("d", "IDP_FLEX", players)
    assert not eligible("x", "QB", players)
    assert not eligible("unknown", "FLEX", players)
    assert starter_slots({"roster_positions": ["QB", "FLEX", "BN", "IR", "TAXI"]}) == ["QB", "FLEX"]


def test_null_matchups_are_not_opponents():
    matches = [{"roster_id": 1, "matchup_id": None}, {"roster_id": 2, "matchup_id": None}]
    assert opponents(matches, 1)[1] == []
    matches += [{"roster_id": 3, "matchup_id": 5}, {"roster_id": 4, "matchup_id": 5}]
    assert opponents(matches, 3)[1] == [matches[-1]]
    assert opponents(matches, 99) == (None, [])


@pytest.fixture
def trade_data():
    players = {p: player(pos) for p, pos in {"r1": "RB", "r2": "RB", "w1": "WR", "r3": "RB", "w2": "WR", "w3": "WR"}.items()}
    scores = {"r1": 20, "r2": 18, "w1": 4, "r3": 4, "w2": 20, "w3": 18}
    rosters = [{"roster_id": 1, "owner_id": "a", "players": ["r1", "r2", "w1"]},
               {"roster_id": 2, "owner_id": "b", "players": ["r3", "w2", "w3"]}]
    return players, scores, rosters


def test_trade_reoptimizes_both_rosters(trade_data):
    players, scores, rosters = trade_data
    trade = evaluate_trade(rosters[0]["players"], rosters[1]["players"], ["r2"], ["w3"], ["RB", "WR"], players, scores)
    assert trade["my_gain"] == trade["their_gain"] == 14
    assert trade["my_utility"] == pytest.approx(11.9)
    assert trade["value_gap"] == 0


def test_trade_filters_and_untouchable(trade_data):
    players, scores, rosters = trade_data
    ideas = suggest_trades(rosters, 1, ["RB", "WR"], players, scores, set(), {"r1"}, targets={"w3"})
    assert len(ideas) == 1
    assert ideas[0]["give"] == ["r2"]
    assert ideas[0]["receive"] == ["w3"]
    assert suggest_trades(rosters, 1, ["RB", "WR"], players, scores, set(), {"r1", "r2"}) == []


@pytest.mark.parametrize("give,receive", [([], []), (["r2"], ["w2", "w3"]), (["r2", "r2"], ["w2", "w3"]), (["w3"], ["r2"])])
def test_invalid_trades_rejected(trade_data, give, receive):
    players, scores, rosters = trade_data
    with pytest.raises(ValueError):
        evaluate_trade(rosters[0]["players"], rosters[1]["players"], give, receive, ["RB", "WR"], players, scores)


def test_incomplete_trade_not_claimed_as_improvement(trade_data):
    players, scores, rosters = trade_data
    with pytest.raises(ValueError, match="Insufficient"):
        evaluate_trade(rosters[0]["players"], rosters[1]["players"], ["r2"], ["w3"], ["QB", "RB", "WR"], players, scores)


def test_questionable_penalty_never_improves_negative_score():
    players = {"x": player("QB", injury_status="Questionable")}
    m = build_metrics(players, ["x"], {1: [{"players_points": {"x": -10}}]}, ModelSettings())["x"]
    assert m["score"] == -11


def test_draft_guard_rejects_lopsided_and_unknown_costs(trade_data):
    players, scores, rosters = trade_data
    kwargs = {"targets": {"w3"}, "draft_rounds": {"r1": 1, "r2": 2, "w3": 9}}
    assert suggest_trades(rosters, 1, ["RB", "WR"], players, scores, set(), set(), **kwargs) == []
    kwargs["draft_rounds"] = {"r2": 8, "w3": 9}
    result = suggest_trades(rosters, 1, ["RB", "WR"], players, scores, set(), set(), **kwargs)
    assert len(result) == 1
    assert result[0]["give"] == ["r2"]
    assert suggest_trades(rosters, 1, ["RB", "WR"], players, scores, set(), set(), draft_rounds={}) == []