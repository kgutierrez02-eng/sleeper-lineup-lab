from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from sleeper_app import data


APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture(autouse=True)
def connection_defaults(monkeypatch):
    monkeypatch.setattr(data, "load_preferences", lambda: {"league": "123", "team": "user", "week": 3})


def fake_snapshot(*args, **kwargs):
    return {
        "league": {"league_id": "123", "name": "Test League", "season": "2026", "status": "in_season",
                   "roster_positions": ["RB", "WR", "BN"], "settings": {}, "scoring_settings": {"rec": 1}},
        "users": [], "selected": 1, "names": {1: "My team", 2: "Opponent"},
        "state": {"season": "2026", "season_type": "regular", "week": 2},
        "rosters": [{"roster_id": 1, "owner_id": "a", "players": ["r1", "r2", "w1"], "starters": ["r1", "w1"]},
                    {"roster_id": 2, "owner_id": "b", "players": ["r3", "w2", "w3"], "starters": ["r3", "w2"]}],
        "matchups": [{"roster_id": 1, "matchup_id": 1, "points": 0, "players": ["r1", "r2", "w1"], "starters": ["r1", "w1"]},
                     {"roster_id": 2, "matchup_id": 1, "points": 0, "players": ["r3", "w2", "w3"], "starters": ["r3", "w2"]}],
        "players": {p: {"full_name": p, "position": pos, "fantasy_positions": [pos], "team": "PHI", "status": "Active"}
                    for p, pos in {"r1": "RB", "r2": "RB", "w1": "WR", "r3": "RB", "w2": "WR", "w3": "WR"}.items()},
        "history": {1: [{"players_points": {"r1": 20, "r2": 18, "w1": 4, "r3": 4, "w2": 20, "w3": 18}}]},
        "warnings": [], "sources": [{"Endpoint": "fixture", "Fetched (UTC)": "test", "Source": "fixture"}],
    }


def test_app_renders_and_trade_button_works(monkeypatch):
    monkeypatch.setattr(data, "load_snapshot", fake_snapshot)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert len(app.tabs) == 8
    next(b for b in app.button if b.label == "Find one-for-one trade ideas").click().run()
    assert app.session_state["trade_search"][1] == []
    next(s for s in app.slider if s.label == "Minimum observed weeks per trade player").set_value(1).run()
    button = next(b for b in app.button if b.label == "Find one-for-one trade ideas")
    button.click().run()
    assert not app.exception
    assert app.session_state["trade_search"][1]
    slider = next(s for s in app.slider if s.label == "Consistency ← risk preference → upside")
    slider.set_value(0.5).run()
    assert not app.exception


def test_shop_and_weekly_ideas_and_formatting(monkeypatch):
    import json

    monkeypatch.setattr(data, "load_snapshot", fake_snapshot)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    next(s for s in app.slider if s.label == "Minimum observed weeks per trade player").set_value(1).run()
    next(s for s in app.selectbox if s.label == "My player to shop").set_value("r2").run()
    next(b for b in app.button if b.label == "Find targets for my player").click().run()
    assert not app.exception
    ideas = app.session_state["shop_results"][2]
    assert ideas and all("r2" in t["give"] for t in ideas)
    next(b for b in app.button if b.label == "Develop weekly trade ideas").click().run()
    assert not app.exception
    assert app.session_state["weekly_ideas"][2]
    formatted = [f for f in app.dataframe if "Model score" in f.value.columns]
    assert formatted
    for frame in formatted:
        assert json.loads(frame.proto.columns)["Model score"]["type_config"]["format"] == "%.2f"


def test_app_empty_history_is_not_a_prediction(monkeypatch):
    def empty(*args, **kwargs):
        snapshot = fake_snapshot()
        snapshot["history"] = {}
        return snapshot

    monkeypatch.setattr(data, "load_snapshot", empty)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert any("Incomplete lineup" in error.value for error in app.error)


def test_app_connection_failure_is_displayed(monkeypatch):
    def fail(*args, **kwargs):
        raise data.SleeperError("Connection failed")

    monkeypatch.setattr(data, "load_snapshot", fail)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert any("Connection failed" in error.value for error in app.error)


def test_clean_distribution_onboarding_has_no_network_call(monkeypatch):
    monkeypatch.setattr(data, "load_preferences", lambda: {"league": "", "team": "", "week": 3})
    def no_network(*args, **kwargs):
        pytest.fail("Blank first-run connection must not fetch league data")
    monkeypatch.setattr(data, "load_snapshot", no_network)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert any("Welcome!" in message.value for message in app.info)