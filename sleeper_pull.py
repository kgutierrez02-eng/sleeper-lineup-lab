
#!/usr/bin/env python3
"""
Sleeper league roster viewer

Pulls:
- league metadata            GET /league/{league_id}
- league users               GET /league/{league_id}/users
- league rosters             GET /league/{league_id}/rosters
- NFL state (current week)   GET /state/nfl
- (optional) matchups        GET /league/{league_id}/matchups/{week}
- Player directory           GET /players/nfl  (cached locally)

Finds your roster by team name and prints starters/bench with positions.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

# Launch the optional app before importing the CLI's dependencies, so the
# launcher can set up its private environment on a fresh computer.
if __name__ == "__main__" and "--app" in sys.argv:
    from launch_sleeper import main as launch_app
    sys.exit(launch_app())

import requests


BASE = "https://api.sleeper.app/v1"


def get_json(url: str) -> Any:
    r = requests.get(url, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} for {url}: {r.text[:200]}")
    return r.json()


def fetch_league(league_id: str) -> dict:
    return get_json(f"{BASE}/league/{league_id}")


def fetch_users(league_id: str) -> List[dict]:
    return get_json(f"{BASE}/league/{league_id}/users")


def fetch_rosters(league_id: str) -> List[dict]:
    return get_json(f"{BASE}/league/{league_id}/rosters")


def fetch_nfl_state() -> dict:
    return get_json(f"{BASE}/state/nfl")


def fetch_matchups(league_id: str, week: int) -> List[dict]:
    return get_json(f"{BASE}/league/{league_id}/matchups/{week}")


def load_players(cache_path: Optional[str] = None) -> Dict[str, dict]:
    """
    Loads the NFL players directory (~5–10MB). Cache to disk to avoid repeated downloads.
    """
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    players = get_json(f"{BASE}/players/nfl")
    if cache_path:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(players, f)
    return players


def name_for_player(pid: str, players: Dict[str, dict]) -> str:
    p = players.get(pid, {})
    first = p.get("first_name") or ""
    last = p.get("last_name") or ""
    full = (first + " " + last).strip() or p.get("full_name") or str(pid)
    return full


def pos_for_player(pid: str, players: Dict[str, dict]) -> str:
    p = players.get(pid, {})
    # Sleeper fields can be: position, fantasy_positions (list)
    pos = p.get("position") or (p.get("fantasy_positions") or [None])[0]
    return pos or "UNK"


def team_for_player(pid: str, players: Dict[str, dict]) -> str:
    p = players.get(pid, {})
    return p.get("team") or p.get("active_team") or ""


def injury_for_player(pid: str, players: Dict[str, dict]) -> str:
    p = players.get(pid, {})
    status = p.get("injury_status") or ""
    notes = p.get("injury_notes") or ""
    return status + (f" – {notes}" if status and notes else "")


def map_ownerid_to_teamname(users: List[dict]) -> Dict[str, str]:
    """
    users[].metadata.team_name typically holds the custom team name.
    Fallback to display_name if not present.
    """
    mapping = {}
    for u in users:
        uid = u.get("user_id")
        meta = u.get("metadata") or {}
        team_name = meta.get("team_name") or u.get("display_name") or uid
        mapping[uid] = team_name
    return mapping


def find_owner_id_for_team(users: List[dict], target_team: str) -> Optional[str]:
    for u in users:
        meta = u.get("metadata") or {}
        names = [meta.get("team_name"), u.get("display_name"), u.get("username"), u.get("user_id")]
        if target_team.strip().casefold() in {str(name).strip().casefold() for name in names if name}:
            return u.get("user_id")
    return None


def find_roster_for_owner(rosters: List[dict], owner_id: str) -> Optional[dict]:
    for r in rosters:
        if r.get("owner_id") == owner_id:
            return r
    return None


def print_roster(roster: dict, players: Dict[str, dict], league: dict) -> None:
    print("\n===== YOUR ROSTER =====")
    rp = league.get("roster_positions") or []
    print(f"League roster slots: {rp}\n")

    starters = roster.get("starters") or []
    bench = [pid for pid in (roster.get("players") or []) if pid not in starters]

    def fmt(pid: str) -> str:
        return f"{name_for_player(pid, players)}  [{pos_for_player(pid, players)}  {team_for_player(pid, players)}]  {injury_for_player(pid, players)}"

    print("** Starters (as currently set in Sleeper) **")
    for i, pid in enumerate(starters, 1):
        print(f"{i:>2}. {fmt(pid)}")

    print("\n** Bench **")
    for i, pid in enumerate(bench, 1):
        print(f"{i:>2}. {fmt(pid)}")


def print_matchups(league_id: str, week: int, users: List[dict], rosters: List[dict]) -> None:
    print(f"\n===== WEEK {week} MATCHUPS =====")
    matchups = fetch_matchups(league_id, week)

    # Build helpers
    uid_to_team = map_ownerid_to_teamname(users)
    rosterid_to_ownerid = {r["roster_id"]: r["owner_id"] for r in rosters}

    # Each matchup has a roster_id and points. Pair by 'matchup_id'.
    by_matchup = {}
    for m in matchups:
        mid = m.get("matchup_id")
        by_matchup.setdefault(mid, []).append(m)

    for mid, games in sorted(by_matchup.items(), key=lambda x: x[0] if x[0] is not None else 0):
        row = []
        for g in games:
            rid = g.get("roster_id")
            oid = rosterid_to_ownerid.get(rid, "")
            team = uid_to_team.get(oid, f"Roster {rid}")
            pts = g.get("points")
            row.append((team, pts))
        if len(row) == 2:
            left, right = row
            print(f"{left[0]} ({left[1]:.2f})  vs  {right[0]} ({right[1]:.2f})")
        else:
            # Some leagues can have odd entries – print raw
            print(f"Matchup {mid}: {row}")


def main():
    ap = argparse.ArgumentParser(description="Sleeper league roster viewer")
    ap.add_argument("--app", action="store_true", help="Open the local lineup and trade app (no other arguments required)")
    ap.add_argument("--league", required=True, help="Sleeper league ID")
    ap.add_argument("--team", required=True, help="Your team name as shown in the league")
    ap.add_argument("--players-cache", default="players_nfl.json", help="Cache path for players directory JSON")
    ap.add_argument("--show-matchups", action="store_true", help="Also show current-week league matchups")
    ap.add_argument("--week", type=int, choices=range(1, 19), help="Specific matchup week instead of the current week")
    args = ap.parse_args()

    league = fetch_league(args.league)
    users = fetch_users(args.league)
    rosters = fetch_rosters(args.league)
    players = load_players(args.players_cache)

    owner_id = find_owner_id_for_team(users, args.team)
    if not owner_id:
        print(f"Could not find a team named '{args.team}'. "
              f"Check spelling or run without quotes if your shell is escaping them.")
        print("Teams I see:")
        for u in users:
            meta = u.get("metadata") or {}
            tname = meta.get("team_name") or u.get("display_name")
            print(" -", tname)
        sys.exit(1)

    my_roster = find_roster_for_owner(rosters, owner_id)
    if not my_roster:
        print(f"Found owner_id {owner_id} for '{args.team}', but no roster matched.")
        sys.exit(1)

    # Print roster detail
    print(f"\nLeague: {league.get('name')} (season {league.get('season')})")
    print(f"Team:   {args.team}")
    print_roster(my_roster, players, league)

    # Optional: show current-week matchups
    if args.show_matchups:
        state = fetch_nfl_state()
        week = args.week if args.week is not None else state.get("week")
        if not isinstance(week, int):
            print("\nCould not determine current NFL week from /state/nfl.")
        else:
            print_matchups(args.league, week, users, rosters)



if __name__ == "__main__":
    main()

