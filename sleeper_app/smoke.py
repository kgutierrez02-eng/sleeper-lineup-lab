"""Offline runtime check shipped with the EXE; contains no private league data."""

from unittest.mock import patch


def run_smoke_tests(root):
    from streamlit.testing.v1 import AppTest
    from sleeper_app import data
    from sleeper_app.analysis import optimize_lineup
    players = {p: {"position": pos, "fantasy_positions": [pos], "full_name": p} for p, pos in
               {"r1": "RB", "r2": "RB", "w1": "WR", "r3": "RB", "w2": "WR", "w3": "WR"}.items()}
    scores = {"r1": 20., "r2": 18., "w1": 4., "r3": 4., "w2": 20., "w3": 18.}
    assert optimize_lineup(["r1", "r2", "w1"], ["RB", "FLEX"], players, scores).total == 38
    snapshot = {
        "league": {"league_id": "123", "name": "Offline test", "season": "2026", "status": "in_season",
                   "roster_positions": ["RB", "WR", "BN"], "settings": {}, "scoring_settings": {"rec": 1}},
        "selected": 1, "users": [], "names": {1: "My team", 2: "Opponent"},
        "state": {"season": "2026", "season_type": "regular", "week": 2},
        "rosters": [{"roster_id": 1, "owner_id": "a", "players": ["r1", "r2", "w1"], "starters": ["r1", "w1"]},
                    {"roster_id": 2, "owner_id": "b", "players": ["r3", "w2", "w3"], "starters": ["r3", "w2"]}],
        "matchups": [], "players": players, "history": {1: [{"players_points": scores}]},
        "sources": [], "warnings": [], "schedule": {}}
    with patch.object(data, "load_preferences", return_value={"league": "", "team": "", "week": 3}):
        welcome = AppTest.from_file(str(root / "sleeper_app/app.py"), default_timeout=60).run()
        assert not welcome.exception, str(welcome.exception)
        assert any("Welcome!" in message.value for message in welcome.info)
    with patch.object(data, "load_preferences", return_value={"league": "123", "team": "user", "week": 3}), \
         patch.object(data, "load_snapshot", return_value=snapshot):
        app = AppTest.from_file(str(root / "sleeper_app/app.py"), default_timeout=60).run()
        assert not app.exception, str(app.exception)
        next(s for s in app.slider if s.label == "Minimum observed weeks per trade player").set_value(1).run()
        next(s for s in app.selectbox if s.label == "My player to shop").set_value("r2").run()
        next(b for b in app.button if b.label == "Find targets for my player").click().run()
        assert not app.exception, str(app.exception)
        assert app.session_state["shop_results"][2]
        next(b for b in app.button if b.label == "Develop weekly trade ideas").click().run()
        assert not app.exception, str(app.exception)
    return {"optimizer": "passed", "onboarding": "passed", "dashboard": "passed", "trade_search": "passed", "weekly_ideas": "passed"}