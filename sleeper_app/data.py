"""Documented Sleeper endpoints only. All requests are read-only GETs."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def _default_frozen_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SleeperLineupLab"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "SleeperLineupLab"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "SleeperLineupLab"


BASE = "https://api.sleeper.app/v1"
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = (Path(os.environ["SLEEPER_APP_DATA_DIR"]) if os.environ.get("SLEEPER_APP_DATA_DIR")
            else _default_frozen_data_dir() if getattr(sys, "frozen", False) else APP_DIR)
DEFAULTS = {"league": "", "team": "", "week": 3}


class SleeperError(RuntimeError):
    """A recoverable API, cache, or input problem."""


def league_id(value: str) -> str:
    """Accept an ID or a standard Sleeper league URL, not arbitrary URLs."""
    value = value.strip().rstrip("/")
    if value.isdigit():
        return value
    match = re.fullmatch(r"https?://(?:www\.)?sleeper\.(?:app|com)/leagues?/(\d+)(?:/[^?]*)?", value)
    if match:
        return match.group(1)
    raise SleeperError("Enter a numeric league ID or a Sleeper league URL.")


def load_preferences() -> dict:
    try:
        data = json.loads((DATA_DIR / "preferences.json").read_text(encoding="utf-8"))
        return {**DEFAULTS, "league": league_id(str(data["league"])),
                "team": str(data["team"]), "week": max(1, min(18, int(data["week"])))}
    except (OSError, ValueError, KeyError, TypeError):
        return dict(DEFAULTS)


def save_preferences(league: str, team: str, week: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "preferences.json").write_text(
        json.dumps({"league": league_id(league), "team": team, "week": week}, indent=2),
        encoding="utf-8",
    )


class SleeperClient:
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or DATA_DIR / ".cache"
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "SleeperLocalWorkbench/1.0 (personal read-only app)"
        retries = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504],
                        allowed_methods=["GET"], respect_retry_after_header=False)
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.sources: list[dict] = []
        self.warnings: list[str] = []

    def get(self, path: str, expected: type, ttl: int = 300, refresh: bool = False):
        url = BASE + path
        cache = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        payload = None
        try:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            if not isinstance(payload.get("data"), expected):
                payload = None
        except (OSError, ValueError, AttributeError):
            pass
        fresh = payload is not None and 0 <= time.time() - payload.get("at", 0) < ttl
        # Players directory is deliberately never force-refreshed within 24 hours.
        cached = fresh and (not refresh or path == "/players/nfl")
        stale = False
        if not cached:
            try:
                response = self.session.get(url, timeout=(10, 35))
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, expected) or (expected is dict and not data):
                    raise SleeperError(f"No usable data at {path}; check the league or username.")
                payload = {"at": time.time(), "data": data}
                try:
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    temporary = cache.with_suffix(".tmp")
                    temporary.write_text(json.dumps(payload), encoding="utf-8")
                    temporary.replace(cache)
                except OSError as exc:
                    self.warnings.append(f"Could not save cache: {exc}")
            except (requests.RequestException, ValueError, SleeperError) as exc:
                if payload is None:
                    raise SleeperError(f"Could not load {path}: {exc}") from exc
                stale = True
                self.warnings.append(f"OFFLINE/STALE: {path} uses its last successful download. {exc}")
        assert payload is not None
        self.sources.append({"Endpoint": url,
                             "Fetched (UTC)": datetime.fromtimestamp(payload["at"], timezone.utc).isoformat(timespec="seconds"),
                             "Source": "STALE cache" if stale else "Cache" if cached else "Live"})
        return payload["data"]


def team_names(users: list[dict], rosters: list[dict]) -> dict[int, str]:
    owners = {u.get("user_id"): (u.get("metadata") or {}).get("team_name")
              or u.get("display_name") or str(u.get("user_id")) for u in users}
    return {r["roster_id"]: owners.get(r.get("owner_id"), f"Roster {r['roster_id']}") for r in rosters}


def resolve_roster(client: SleeperClient, users: list[dict], rosters: list[dict], target: str) -> int | None:
    wanted = target.strip().casefold()
    if not wanted:
        return None
    owner = next((u.get("user_id") for u in users if wanted in {
        str(u.get("user_id", "")).casefold(), str(u.get("display_name", "")).casefold(),
        str(u.get("username", "")).casefold(),
        str((u.get("metadata") or {}).get("team_name", "")).casefold()}), None)
    if owner is None and wanted:
        try:
            owner = client.get(f"/user/{quote(target.strip(), safe='')}", dict).get("user_id")
        except SleeperError:
            return None
    return next((r["roster_id"] for r in rosters if owner is not None and
                 (r.get("owner_id") == owner or owner in (r.get("co_owners") or []))), None)


def completed_week_limit(league: dict, state: dict, target_week: int) -> int:
    """Exclude the target week, in-progress weeks, and not-yet-finalized league scores."""
    season = int(league["season"])
    current_season = int(state.get("season") or season)
    if season > current_season:
        return 0
    if season < current_season:
        calendar_limit = 18
    elif state.get("season_type") == "post":
        calendar_limit = 18
    elif state.get("season_type") != "regular":
        calendar_limit = 0
    else:
        calendar_limit = max(0, int(state.get("week") or 1) - 1)
    finalized = (league.get("settings") or {}).get("last_scored_leg")
    if finalized is not None:
        calendar_limit = min(calendar_limit, int(finalized))
    return max(0, min(target_week - 1, calendar_limit, 18))


def load_snapshot(league: str, target: str, week: int, lookback: int, refresh: bool = False) -> dict:
    lid = league_id(league)
    client = SleeperClient()
    info = client.get(f"/league/{lid}", dict, refresh=refresh)
    if info.get("sport") != "nfl" or info.get("season_type", "regular") != "regular":
        raise SleeperError("This version supports regular-season NFL leagues only.")
    users = client.get(f"/league/{lid}/users", list, refresh=refresh)
    rosters = client.get(f"/league/{lid}/rosters", list, refresh=refresh)
    if not rosters:
        raise SleeperError("This league has no rosters yet.")
    state = client.get("/state/nfl", dict, refresh=refresh)
    matchups = client.get(f"/league/{lid}/matchups/{week}", list, refresh=refresh)
    players = client.get("/players/nfl", dict, ttl=86400)
    draft = {}
    draft_picks = []
    if info.get("draft_id"):
        try:
            draft = client.get(f"/draft/{info['draft_id']}", dict, ttl=86400)
            draft_picks = client.get(f"/draft/{info['draft_id']}/picks", list, ttl=86400)
        except SleeperError as exc:
            client.warnings.append(f"Draft-cost guard unavailable: {exc}")
    selected = resolve_roster(client, users, rosters, target)
    last_week = completed_week_limit(info, state, week)
    start = max(int((info.get("settings") or {}).get("start_week") or 1), last_week - lookback + 1)
    history = {}
    for previous in range(start, last_week + 1):
        try:
            history[previous] = client.get(f"/league/{lid}/matchups/{previous}", list, refresh=refresh)
        except SleeperError as exc:
            client.warnings.append(f"Missing history for week {previous}: {exc}")
    # Future *fantasy* pairings only. Their point fields never feed the estimator.
    playoff_start = int((info.get("settings") or {}).get("playoff_week_start") or 19)
    schedule = {week: matchups} if week < playoff_start else {}
    for future in range(week + 1, min(week + 4, playoff_start, 19)):
        try:
            schedule[future] = client.get(f"/league/{lid}/matchups/{future}", list, refresh=refresh)
        except SleeperError as exc:
            client.warnings.append(f"No planning schedule for week {future}: {exc}")
    return {"league": info, "users": users, "rosters": rosters, "state": state,
            "draft": draft, "draft_picks": draft_picks,
            "schedule": schedule,
            "matchups": matchups, "players": players, "history": history, "selected": selected,
            "names": team_names(users, rosters), "sources": client.sources, "warnings": client.warnings}