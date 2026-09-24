import pytest

from sleeper_app.trades import (PackageEvaluator, TradeFilters, contextualize, depth_risks,
                                draft_compatible, league_context, roster_capacity,
                                search_packages, standings)


@pytest.fixture
def setup():
    scores = {"r1": 20.0, "r2": 14.0, "w1": 5.0, "w2": 10.0,
              "r3": 2.0, "w3": 25.0, "w4": 18.0, "w5": 1.0}
    players = {p: {"position": "RB" if p.startswith("r") else "WR",
                   "full_name": p, "fantasy_positions": ["RB" if p.startswith("r") else "WR"]} for p in scores}
    rosters = [{"roster_id": 1, "owner_id": "a", "players": ["r1", "r2", "w1", "w2"],
                "settings": {"wins": 0, "losses": 2, "fpts": 45, "fpts_decimal": 50}},
               {"roster_id": 2, "owner_id": "b", "players": ["r3", "w3", "w4", "w5"],
                "settings": {"wins": 2, "losses": 0, "fpts": 100}}]
    league = {"roster_positions": ["RB", "WR", "BN", "BN", "IR"], "settings": {}}
    return players, scores, rosters, league, {p: {"weeks": 2} for p in scores}


def test_anchored_search_adds_player_and_accounts_for_cut(setup):
    players, scores, rosters, league, metrics = setup
    results = search_packages(rosters, 1, league, players, scores, metrics, set(), set(), anchor="r2", targets={"w3"})
    assert results
    assert all("r2" in t["give"] for t in results)
    trade = next(t for t in results if set(t["give"]) == {"r2", "w2"})
    assert trade["their_cuts"] == ["w5"]
    assert trade["my_cuts"] == []
    assert trade["my_open_slots"] == 1
    assert trade["their_open_slots"] == 0
    assert trade["my_gain"] == 15
    assert trade["their_gain"] == 5
    assert trade["my_utility"] == pytest.approx(12.9)
    assert trade["their_utility"] == pytest.approx(3.95)


def test_all_search_constraints_and_no_anchor_bypass(setup):
    players, scores, rosters, league, metrics = setup
    args = (rosters, 1, league, players, scores, metrics)
    assert search_packages(*args, set(), {"r2"}, anchor="r2") == []
    assert search_packages(*args, {"r2"}, set(), anchor="r2") == []
    assert search_packages(*args, set(), set(), anchor="not_rostered") == []
    assert search_packages(*args, set(), set(), targets=set()) == []
    assert search_packages(*args, set(), set(), TradeFilters(min_weeks=3)) == []
    assert search_packages(*args, set(), set(), TradeFilters(include_packages=False), anchor="r2", targets={"w3"}) == []
    metrics["w2"]["weeks"] = 0
    ideas = search_packages(*args, set(), {"r1"}, anchor="r2", targets={"w3"})
    assert all("w2" not in t["give"] for t in ideas)


def test_draft_guard_uses_earliest_pick_not_round_sum():
    rounds = {"a": 2, "b": 12, "c": 3}
    assert draft_compatible(["a", "b"], ["c"], rounds, 2)
    assert not draft_compatible(["b"], ["c"], rounds, 2)
    assert not draft_compatible(["a", "missing"], ["c"], rounds, 2)


def test_cut_avoids_breaking_positional_coverage(setup):
    players, scores, rosters, league, _ = setup
    # A low-scoring only RB must be retained over a surplus WR.
    ev = PackageEvaluator(["RB", "WR"], players, scores, 3)
    _, kept, lineup, cuts = ev.trim(["r3", "w1", "w2", "w3"], {"w3"})
    assert "r3" in kept and not lineup.missing
    assert cuts == ["w1"]
    with pytest.raises(ValueError, match="No full legal"):
        ev.trim(["r3", "w1", "w2", "w3"], {"w1", "w2", "w3"})


def test_no_invented_waiver_value_and_open_capacity(setup):
    players, scores, rosters, _, _ = setup
    ev = PackageEvaluator(["RB", "WR"], players, scores, 5)
    t = ev.evaluate(rosters[0]["players"], rosters[1]["players"], ["r2", "w2"], ["w3"])
    assert t["their_cuts"] == []
    assert t["my_open_slots"] == 2
    assert t["my_gain"] == 15
    assert len(t["my_players_after"]) == 3


def test_unequal_reverse_package_and_keep_protection(setup):
    players, scores, rosters, _, _ = setup
    ev = PackageEvaluator(["RB", "WR"], players, scores, 4)
    t = ev.evaluate(rosters[0]["players"], rosters[1]["players"], ["r2"], ["w3", "w5"], keep={"w1"})
    assert t["my_cuts"] == ["w2"]  # incoming w5 and Keep w1 may not be cut
    assert "w1" in t["my_players_after"]
    with pytest.raises(ValueError, match="over capacity"):
        PackageEvaluator(["RB", "WR"], players, scores, 3).evaluate(rosters[0]["players"], rosters[1]["players"], ["r2"], ["w3"])


@pytest.mark.parametrize("give,receive", [([], ["w3"]), (["r2"], []), (["r2", "r2"], ["w3"]), (["w3"], ["r2"])])
def test_invalid_packages(setup, give, receive):
    players, scores, rosters, _, _ = setup
    with pytest.raises(ValueError):
        PackageEvaluator(["RB", "WR"], players, scores, 4).evaluate(rosters[0]["players"], rosters[1]["players"], give, receive)


def test_standings_ties_decimals_and_unplayed(setup):
    _, _, rosters, _, _ = setup
    rosters += [{"roster_id": 3, "settings": {"wins": 2, "fpts": 100}}, {"roster_id": 4}]
    rows = standings(rosters, {})
    assert rows[0]["Table rank"] == rows[1]["Table rank"] == 1
    mine = next(r for r in rows if r["roster_id"] == 1)
    assert mine["Points for"] == 45.5
    assert mine["Table rank"] == 3
    assert rows[-1]["Win rate"] is None


def test_context_uses_finalized_scores_not_future_points(setup):
    players, scores, rosters, league, metrics = setup
    snapshot = {"players": players, "rosters": rosters, "league": league, "names": {1: "Mine", 2: "Other"},
                "history": {1: [{"roster_id": 1, "points": 20}, {"roster_id": 2, "points": 50}],
                            2: [{"roster_id": 1, "points": 25, "custom_points": 0}, {"roster_id": 2, "points": 50}]},
                "schedule": {3: [{"roster_id": 1, "matchup_id": 1, "points": 10000}, {"roster_id": 2, "matchup_id": 1}],
                             4: [{"roster_id": 1, "matchup_id": None}, {"roster_id": 2, "matchup_id": None}]}}
    context = league_context(snapshot, 1, scores, set())
    assert context["trend"] == -20
    assert context["weekly"][1]["Actual points"] == 0
    assert context["pressure"]
    assert context["upcoming"][0]["Model gap"] == 3
    assert context["upcoming"][1]["Opponent"] == "Not assigned / bye"
    assert next(r for r in context["needs"] if r["Slot group"] == "WR")["Gap / slot"] == -15
    offers = search_packages(rosters, 1, league, players, scores, metrics, set(), set(), anchor="r2")
    ranked = contextualize(offers, context, snapshot, scores)
    assert ranked and any("WR rises" in reason for reason in ranked[0]["reasons"])


def test_missing_history_and_depth_are_honest(setup):
    players, scores, rosters, league, _ = setup
    snapshot = {"players": players, "rosters": rosters, "league": league, "names": {}, "history": {}}
    context = league_context(snapshot, 1, {p: None for p in scores}, set())
    assert context["trend"] is None and context["weekly"] == []
    assert context["risks"] == [] and context["missing"]
    risks = depth_risks(["r1", "w1"], ["RB", "WR"], players, scores, set())
    assert all(r["Unfilled slots if absent"] for r in risks)
    assert roster_capacity(league) == 4