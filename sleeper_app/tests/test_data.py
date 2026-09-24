from unittest.mock import Mock

import pytest
import requests

from sleeper_app.data import (SleeperClient, SleeperError, completed_week_limit, league_id,
                              resolve_roster, load_snapshot)


@pytest.mark.parametrize("season,state_season,state_type,week,target,finalized,expected", [
    (2026, 2026, "regular", 2, 3, 1, 1),
    (2026, 2026, "regular", 3, 3, 2, 2),
    (2026, 2026, "regular", 8, 3, 7, 2),
    (2026, 2026, "regular", 1, 1, 0, 0),
    (2027, 2026, "regular", 8, 3, 0, 0),
    (2025, 2026, "regular", 2, 3, 18, 2),
    (2026, 2026, "pre", 4, 3, 0, 0),
    (2026, 2026, "post", 2, 18, 18, 17),
    (2026, 2026, "regular", 3, 3, 1, 1),
])
def test_finalized_history_cutoff(season, state_season, state_type, week, target, finalized, expected):
    assert completed_week_limit({"season": str(season), "settings": {"last_scored_leg": finalized}},
                                {"season": str(state_season), "season_type": state_type, "week": week}, target) == expected


def test_input_parsing():
    assert league_id(" 12345 ") == "12345"
    assert league_id("https://sleeper.com/leagues/12345/team") == "12345"
    assert league_id("https://sleeper.app/leagues/12345") == "12345"
    with pytest.raises(SleeperError):
        league_id("https://example.com/12345")


def test_username_and_custom_team_and_coowner_resolve():
    client = Mock()
    users = [{"user_id": "1", "display_name": "manager27", "metadata": {"team_name": "New Name"}}]
    rosters = [{"roster_id": 3, "owner_id": "1"}]
    assert resolve_roster(client, users, rosters, "MANAGER27") == 3
    assert resolve_roster(client, users, rosters, " new name ") == 3
    assert resolve_roster(client, users, [{"roster_id": 3, "owner_id": "2", "co_owners": ["1"]}], "manager27") == 3
    assert resolve_roster(client, users, rosters, " ") is None
    client.get.assert_not_called()


def test_cache_ttl_and_player_refresh_limit(tmp_path):
    client = SleeperClient(tmp_path)
    response = Mock()
    response.json.return_value = {"a": {"position": "QB"}}
    client.session.get = Mock(return_value=response)
    assert client.get("/players/nfl", dict, 86400) == response.json.return_value
    client.get("/players/nfl", dict, 86400, refresh=True)
    assert client.session.get.call_count == 1
    assert client.sources[-1]["Source"] == "Cache"


def test_stale_cache_is_explicitly_flagged(tmp_path):
    client = SleeperClient(tmp_path)
    response = Mock()
    response.json.return_value = {"week": 2}
    client.session.get = Mock(return_value=response)
    client.get("/state/nfl", dict)
    client.session.get = Mock(side_effect=requests.ConnectionError("offline"))
    assert client.get("/state/nfl", dict, refresh=True) == {"week": 2}
    assert client.sources[-1]["Source"] == "STALE cache"
    assert client.warnings


def test_no_cache_api_failure_is_actionable(tmp_path):
    client = SleeperClient(tmp_path)
    client.session.get = Mock(side_effect=requests.ConnectionError("offline"))
    with pytest.raises(SleeperError, match="Could not load"):
        client.get("/league/1", dict)


def test_corrupt_cache_and_null_league(tmp_path):
    client = SleeperClient(tmp_path)
    response = Mock()
    response.json.return_value = {"week": 2}
    client.session.get = Mock(return_value=response)
    client.get("/state/nfl", dict)
    next(tmp_path.glob("*.json")).write_text("not JSON")
    assert client.get("/state/nfl", dict) == {"week": 2}
    response.json.return_value = None
    with pytest.raises(SleeperError, match="No usable data"):
        client.get("/league/9999", dict)


def test_snapshot_requests_only_finalized_history(monkeypatch):
    calls = []
    responses = {
        "/league/123": {"sport": "nfl", "season": "2026", "settings": {"last_scored_leg": 1}},
        "/league/123/users": [{"user_id": "a", "display_name": "user"}],
        "/league/123/rosters": [{"roster_id": 1, "owner_id": "a"}],
        "/state/nfl": {"season": "2026", "season_type": "regular", "week": 2},
        "/league/123/matchups/3": [], "/league/123/matchups/1": [], "/players/nfl": {"x": {}},
        "/league/123/matchups/4": [], "/league/123/matchups/5": [], "/league/123/matchups/6": [],
    }

    def get(self, path, *args, **kwargs):
        calls.append(path)
        return responses[path]

    monkeypatch.setattr(SleeperClient, "get", get)
    snapshot = load_snapshot("123", "user", 3, 6)
    assert snapshot["selected"] == 1
    assert list(snapshot["history"]) == [1]
    assert "/league/123/matchups/2" not in calls
    assert list(snapshot["schedule"]) == [3, 4, 5, 6]