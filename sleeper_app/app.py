"""Streamlit UI. Start through ../Open Sleeper App.bat or sleeper_pull.py --app."""

from dataclasses import asdict
import html
import json
from pathlib import Path
import sys
import time

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sleeper_app.analysis import (ModelSettings, active_players, build_metrics,
                                  opponents, optimize_lineup, player_name, starter_slots,
                                  unavailable)
from sleeper_app.data import (SleeperClient, SleeperError, load_preferences, load_snapshot,
                              save_preferences)
from sleeper_app.presentation import score_table
from sleeper_app.trade_ui import render_trade_lab


st.set_page_config(page_title="Sleeper • Lineup Lab", page_icon="🏈", layout="wide")
st.markdown("""
<style>
.stApp {background: radial-gradient(ellipse at top right, #172844 0%, #0b1120 60%); color:#e8eef8;}
[data-testid="stSidebar"] {background:#101a2d;}
.block-container {padding-top:2rem; max-width:1550px;}
.hero {padding:1.6rem 2rem; border:1px solid #314668; border-radius:20px;
       background:linear-gradient(115deg,#162b4b,#222242); margin-bottom:1.4rem;}
.hero h1 {font-size:2.4rem; margin:0; color:#fff;}
.hero p {color:#bdcce4; margin-bottom:0;}
.eyebrow {font-size:.76rem; letter-spacing:.18em; color:#75e7ce; font-weight:700;}
[data-testid="stMetric"] {background:#152239; border:1px solid #2a405f; padding:1rem; border-radius:14px;}
.stButton>button[kind="primary"] {background:#3e68ec; border:0;}
</style>
""", unsafe_allow_html=True)


def label(pid: str, players: dict) -> str:
    p = players.get(pid, {})
    return f"{player_name(pid, players)} · {p.get('position', '?')} · {p.get('team') or 'FA'} [{pid}]"


def display_lineup(ids, slots, players, metrics, scores, actual=None) -> pd.DataFrame:
    rows = []
    for i, slot in enumerate(slots):
        pid = ids[i] if i < len(ids) else None
        m = metrics.get(pid, {})
        row = {"Slot": f"{i + 1} · {slot}", "Player": player_name(pid, players) if pid and pid != "0" else "EMPTY",
               "Team": m.get("team", "—"), "Status now": m.get("status", "—"),
               "Model score": scores.get(pid), "Observed weeks": m.get("weeks", 0)}
        if actual is not None:
            row["Week actual"] = actual.get(pid)
        rows.append(row)
    return pd.DataFrame(rows)


def show_lineup(lineup, slots, players, metrics, scores):
    score_table(display_lineup(lineup.assignments, slots, players, metrics, scores))
    if lineup.missing:
        st.error("Incomplete lineup — no eligible player with an estimate for: " + ", ".join(lineup.missing))


def show_trade(trade, names, players, slots, metrics, scores):
    partner = names.get(trade.get("roster_id"), "Trade partner")
    give = ", ".join(player_name(p, players) for p in trade["give"])
    receive = ", ".join(player_name(p, players) for p in trade["receive"])
    st.markdown(f"**Send:** {give}  \n**Receive from {partner}:** {receive}")
    score_table(pd.DataFrame([{"Side": side, "Player": player_name(p, players), "Model score": scores.get(p),
                              "Observed weeks": metrics.get(p, {}).get("weeks", 0)}
                             for side, package in [("Send", trade["give"]), ("Receive", trade["receive"])] for p in package]))
    for key, owner in [("my_cuts", "You"), ("their_cuts", partner)]:
        if trade.get(key):
            st.warning(f"Required hypothetical roster cut — {owner}: " + ", ".join(player_name(p, players) for p in trade[key]) + ". This loss is included in the evaluation; no drop is submitted.")
    if "my_open_slots" in trade:
        st.caption(f"Active-roster openings after trade/cuts: you {trade['my_open_slots']}, partner {trade['their_open_slots']}. Open spots have no assumed replacement-player value.")
    cols = st.columns(4)
    cols[0].metric("Your lineup change", f"{trade['my_gain']:+.2f}")
    cols[1].metric("Their lineup change", f"{trade['their_gain']:+.2f}")
    cols[2].metric("Your depth-adjusted change", f"{trade['my_utility']:+.2f}")
    cols[3].metric("Their depth-adjusted change", f"{trade['their_utility']:+.2f}")
    if trade["their_gain"] >= 0 and trade["their_utility"] >= 0:
        st.caption("Potential fit: both teams retain or improve modeled starter output and depth-adjusted value. This does not predict trade acceptance.")
    else:
        st.warning("The other team loses modeled lineup output or depth value. A numerical match is not necessarily an attractive offer.")
    st.caption(f"Player-score magnitude gap: {trade['value_gap']:.0%}. This is a heuristic, NOT a market-value or fairness rating.")
    with st.expander("Before / after lineups for both teams"):
        left, right = st.columns(2)
        for col, title, before, after in [(left, "Your team", "my_before", "my_after"), (right, partner, "their_before", "their_after")]:
            with col:
                st.markdown(f"**{title} · before ({trade[before].total:.2f})**")
                show_lineup(trade[before], slots, players, metrics, scores)
                st.markdown(f"**After ({trade[after].total:.2f})**")
                show_lineup(trade[after], slots, players, metrics, scores)


def main():
    prefs = load_preferences()
    with st.sidebar:
        st.markdown("## 🏈 Lineup Lab")
        st.caption("PERSONAL • SLEEPER ONLY • READ ONLY")
        with st.form("connection_form"):
            league_input = st.text_input("League ID or URL", prefs["league"])
            team_input = st.text_input("Username or team name", prefs["team"])
            week_input = st.number_input("Target week", 1, 18, int(prefs["week"]))
            connect = st.form_submit_button("Load league", type="primary", use_container_width=True)
        if "connection" not in st.session_state or connect:
            st.session_state.connection = (league_input, team_input, int(week_input))
        lid, target, week = st.session_state.connection
        if st.button("Save connection as startup default", use_container_width=True):
            try:
                save_preferences(lid, target, week)
                st.success("Saved locally.")
            except (OSError, SleeperError) as exc:
                st.error(str(exc))
        with st.expander("Find a different season / league"):
            st.caption("A Sleeper league ID belongs to one season. Find the correct ID here; the app never mixes seasons.")
            season = st.number_input("League season to find", 2017, 2100, 2026)
            if st.button("Find leagues for username"):
                try:
                    from urllib.parse import quote
                    client = SleeperClient()
                    user = client.get(f"/user/{quote(target.strip(), safe='')}", dict)
                    leagues = client.get(f"/user/{user['user_id']}/leagues/nfl/{season}", list)
                    st.dataframe(pd.DataFrame([{"Name": l.get("name"), "ID": l.get("league_id"), "Season": l.get("season")} for l in leagues]), hide_index=True)
                    st.caption("Copy an ID into the connection form and select Load league.")
                except (SleeperError, KeyError) as exc:
                    st.error(str(exc))
        st.divider()
        st.markdown("### Model controls")
        lookback = st.slider("Completed weeks to use", 1, 12, 6)
        decay = st.slider("Older-week weight multiplier", 0.3, 1.0, 0.8, 0.05,
                          help="1 treats every observed week equally. 0.8 gives the preceding week 80% of the latest week's weight.")
        prior = st.slider("Position-mean shrinkage (pseudo-weeks)", 0.0, 6.0, 2.0, 0.5,
                          help="Pull small samples toward the league-observed position mean. This is a modeling assumption, not a Sleeper projection.")
        risk = st.slider("Consistency ← risk preference → upside", -1.0, 1.0, 0.0, 0.1,
                         help="Adds this multiple of observed standard deviation. Neither floor nor ceiling is guaranteed.")
        q_discount = st.slider("Questionable status penalty (%)", 0, 75, 10, 5)
        exclude_injury = st.checkbox("Exclude Out / IR / PUP / Suspended / Doubtful", True)
        refresh = st.button("↻ Refresh league & scores", use_container_width=True)
        st.caption("League data cached 5 min; player directory 24 hours per Sleeper guidance. Status fields may lag; confirm them in Sleeper.")

    key = (lid, target, week, lookback)
    if not lid.strip():
        st.info("Welcome! Enter your Sleeper league ID and username in the sidebar, then select Load league. No password or API key is needed.")
        st.stop()
    try:
        if refresh or connect or st.session_state.get("snapshot_key") != key or time.monotonic() - st.session_state.get("snapshot_at", 0) > 300:
            with st.spinner("Reading league, rosters, matchups and finalized scores from Sleeper…"):
                snapshot = load_snapshot(lid, target, week, lookback, refresh=refresh)
            st.session_state.snapshot = snapshot
            st.session_state.snapshot_key = key
            st.session_state.snapshot_at = time.monotonic()
        snapshot = st.session_state.snapshot
    except (SleeperError, ValueError) as exc:
        st.error(str(exc))
        st.info("Check your league ID, username and internet connection, then select Load league.")
        st.stop()

    league, players, rosters = snapshot["league"], snapshot["players"], snapshot["rosters"]
    names, history, state = snapshot["names"], snapshot["history"], snapshot["state"]
    roster_ids = [r["roster_id"] for r in rosters]
    selected = snapshot["selected"]
    with st.sidebar:
        if selected is None:
            st.warning("Username/team not found in this league. Select your roster below.")
        my_id = st.selectbox("Analyze roster", roster_ids, index=roster_ids.index(selected) if selected in roster_ids else 0,
                             format_func=lambda r: names[r], key=f"roster_{league['league_id']}_{target}")
        st.caption(f"Season: {league['season']} · {league.get('status')} · {len(rosters)} teams")
    mine = next(r for r in rosters if r["roster_id"] == my_id)
    active = active_players(mine)
    slots = starter_slots(league)
    if not slots:
        st.error("No starting roster slots are configured for this league.")
        st.stop()
    my_matchup, rivals = opponents(snapshot["matchups"], my_id)
    rival_names = " / ".join(names.get(m["roster_id"], str(m["roster_id"])) for m in rivals) or "No opponent assigned"
    st.markdown(f"""<div class="hero"><div class="eyebrow">SLEEPER LINEUP LAB · WEEK {week} · {html.escape(str(league['season']))}</div>
    <h1>{html.escape(names[my_id])} <span style="color:#7792bb">vs</span> {html.escape(rival_names)}</h1>
    <p>{html.escape(league.get('name', 'League'))} · League-scored results, lineup experiments & two-sided trade fit.</p></div>""", unsafe_allow_html=True)
    for warning in snapshot["warnings"]:
        st.warning(warning)
    st.info("Historical model scores — not official projections. NFL opponents, byes, kickoff locks, targets, snaps, weather and rest-of-season rankings are not available from these documented endpoints. Check Sleeper before acting.")
    if len(history) < 3:
        st.warning(f"Only {len(history)} finalized week(s) available before Week {week}. Lineup and trade estimates are very uncertain; do not treat a one-week spike as trade value.")
    current_season = str(state.get("season"))
    if str(league["season"]) != current_season or week < int(state.get("week") or 1):
        st.warning("Historical view: matchup rosters/scores are recorded for that week, but optimization/trades use the league's CURRENT roster and TODAY'S player statuses. This is not an as-of-date backtest.")
    st.caption(f"Sleeper NFL state: {state.get('season')} / {state.get('season_type')} / Week {state.get('week')} · History included: {', '.join('W' + str(w) for w in history) or 'none'}. In-progress and target-week scores never train the model.")

    ids = sorted({str(p) for r in rosters for p in (r.get("players") or [])} |
                 {str(p) for m in snapshot["matchups"] for p in (m.get("players") or [])})
    settings = ModelSettings(decay, prior, risk, q_discount / 100)
    metrics = build_metrics(players, ids, history, settings)
    scores = {pid: m["score"] for pid, m in metrics.items()}
    draft_picks = {str(p["player_id"]): p for p in snapshot.get("draft_picks", []) if p.get("player_id")}
    owners = {p: names[r["roster_id"]] for r in rosters for p in (r.get("players") or [])}

    with st.expander("Player overrides, exclusions & untouchables", expanded=False):
        st.caption("Override is your assumed model score, not API data. Exclude is GLOBAL: it removes that player from all lineup and trade scenarios (use for byes/inactives). Keep prevents your player from appearing in automated offers. IR/taxi players never enter the optimizer. Compare API-based model scores on the Player metrics tab.")
        edits = pd.DataFrame([{"ID": pid, "Player": label(pid, players), "Owner": owners.get(pid, "Not currently rostered"),
                       "Override": None, "Exclude": False, "Keep": False} for pid in ids])
        edits["Override"] = pd.Series([float("nan")] * len(edits), dtype="float64")
        edited = st.data_editor(edits, hide_index=True, width="stretch", disabled=["ID", "Player", "Owner"],
                                column_config={"Override": st.column_config.NumberColumn("Manual score", min_value=-100.0, max_value=150.0, step=0.01, format="%.2f"), "ID": None},
                                key=f"edit_{league['league_id']}_{my_id}_{week}")
    overrides = {row["ID"]: float(row["Override"]) for _, row in edited.iterrows() if pd.notna(row["Override"])}
    scores.update(overrides)
    manual_excluded = set(edited.loc[edited["Exclude"], "ID"])
    excluded = manual_excluded | ({pid for pid in ids if unavailable(pid, players)} if exclude_injury else set())
    untouchable = set(edited.loc[edited["Keep"], "ID"]) & set(active)
    current = mine.get("starters") or []
    with st.sidebar:
        st.divider()
        lockable = [i for i, pid in enumerate(current[:len(slots)]) if pid in active]
        lock_slots = st.multiselect("Lock current starters in exact slots", lockable,
                                   format_func=lambda i: f"{i + 1} {slots[i]} · {player_name(current[i], players)}",
                                   key=f"locks_{league['league_id']}_{my_id}_{week}")
        st.caption("Lock players whose games started. Exclude already-started bench players separately. The public API does not enforce kickoff locks here.")
    locks = {i: current[i] for i in lock_slots}
    try:
        optimal = optimize_lineup(active, slots, players, scores, excluded, locks)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    known_current = [scores.get(p) for p in current[:len(slots)]]
    current_complete = len(known_current) == len(slots) and all(v is not None for v in known_current)
    current_total = sum(v for v in known_current if v is not None)
    columns = st.columns(4)
    columns[0].metric("Current starters · model", f"{current_total:.2f}" if current_complete else "Incomplete")
    columns[1].metric("Optimized · model", f"{optimal.total:.2f}" if not optimal.missing else "Incomplete",
                      f"{optimal.total - current_total:+.2f}" if current_complete and not optimal.missing else None)
    columns[2].metric("Roster with history", f"{sum(metrics[p]['weeks'] > 0 for p in active)} / {len(active)}")
    columns[3].metric("Finalized weeks used", str(len(history)))

    matchup_tab, lineup_tab, metrics_tab, trade_tab, data_tab = st.tabs(["⚔ Matchup", "✓ Lineup optimizer", "▥ Player metrics", "⇄ Trade lab", "ⓘ Sources & model"])
    with matchup_tab:
        st.subheader(f"Week {week} recorded matchup")
        if not my_matchup:
            st.warning("Sleeper has not published your matchup for this week.")
        elif not rivals:
            st.info("No paired opponent: this may be a bye or an unpublished schedule. Null matchup IDs are never grouped together.")
        for matchup in ([my_matchup] if my_matchup else []) + rivals:
            rid = matchup["roster_id"]
            st.markdown(f"### {names.get(rid, f'Roster {rid}')}")
            points = matchup.get("custom_points")
            if points is None:
                points = matchup.get("points")
            st.caption(f"Sleeper actual points: {format(points, '.2f') if points is not None else 'not provided'} · These are actual/live scores, not predictions.")
            score_table(display_lineup(matchup.get("starters") or [], slots, players, metrics, scores, matchup.get("players_points") or {}))
            if rid != my_id:
                rival_roster = next((r for r in rosters if r["roster_id"] == rid), None)
                if rival_roster:
                    rival_opt = optimize_lineup(active_players(rival_roster), slots, players, scores, excluded)
                    with st.expander("Opponent's optimized current-roster scenario"):
                        show_lineup(rival_opt, slots, players, metrics, scores)
                        if not optimal.missing and not rival_opt.missing:
                            st.metric("Your optimized score minus their optimized score", f"{optimal.total - rival_opt.total:+.2f}")
                        st.caption("A historical-score comparison, not a win probability. Opponent lineup locks are unknown.")

    with lineup_tab:
        left, right = st.columns(2)
        with left:
            st.subheader("Currently set in Sleeper")
            score_table(display_lineup(current, slots, players, metrics, scores))
        with right:
            st.subheader("Recommended under your assumptions")
            show_lineup(optimal, slots, players, metrics, scores)
        promote = set(p for p in optimal.assignments if p) - set(current)
        bench = set(p for p in current if p and p != "0") - set(optimal.assignments)
        if promote:
            st.success("Move into lineup: " + ", ".join(player_name(p, players) for p in sorted(promote)))
            st.write("Move out: " + ", ".join(player_name(p, players) for p in sorted(bench)))
        elif not optimal.missing:
            st.success("Your current starter set is already optimal under these assumptions.")
        for pid in sorted(promote):
            m = metrics[pid]
            source = "manual override" if pid in overrides else f"{m['weeks']} observed week(s), position-mean shrinkage and selected risk/status adjustments"
            st.caption(f"{m['name']}: model score {scores[pid]:.2f} from {source}; assigned subject to legal positions and your locks/exclusions.")
        st.warning("Recommendations do not change your Sleeper lineup. Verify injury news, bye weeks and game start times, then make changes manually in Sleeper.")
        export = display_lineup(optimal.assignments, slots, players, metrics, scores).to_csv(index=False, float_format="%.2f")
        st.download_button("Download recommended lineup CSV", export, f"sleeper_{league['season']}_week{week}_lineup.csv", "text/csv")

    with metrics_tab:
        st.subheader("What the API actually tells us")
        scope = st.radio("Players to show", ["My roster", "Opponent", "Entire league"], horizontal=True)
        visible = set(mine.get("players") or []) if scope == "My roster" else {p for m in rivals for p in (m.get("players") or [])} if scope == "Opponent" else set(ids)
        rows = []
        for pid in sorted(visible):
            m = metrics.get(pid)
            if not m:
                continue
            rows.append({"Player": m["name"], "Position": m["position"], "NFL team": m["team"], "Owner": owners.get(pid),
                         "Status now": m["status"], "Practice": m["practice"], "Depth order": m["depth"],
                         "Age": m["age"], "Experience": m["experience"], "Observed weeks": m["weeks"],
                         "Draft pick": draft_picks.get(pid, {}).get("pick_no"), "Draft round": draft_picks.get(pid, {}).get("round"),
                         "Mean points": m["mean"], "Latest points": m["recent"], "Weighted points": m["weighted"],
                         "Std deviation": m["stdev"], "Shrunk baseline": m["baseline"], "Model score": scores[pid],
                         "Manual override": pid in overrides, "Evidence": m["evidence"],
                         **{f"W{w} actual": m["history"].get(w) for w in history}})
        frame = pd.DataFrame(rows)
        score_table(frame)
        st.download_button("Download player metrics CSV", frame.to_csv(index=False, float_format="%.2f"), "sleeper_metrics.csv", "text/csv")
        if visible:
            chart_pid = st.selectbox("Player scoring history", sorted(visible), format_func=lambda p: label(p, players))
            weekly = metrics.get(chart_pid, {}).get("history", {})
            if weekly:
                st.bar_chart(pd.DataFrame({"Week": list(weekly), "League points": list(weekly.values())}).set_index("Week"))
            else:
                st.info("No recorded scores in the completed weeks selected. Missing data is not treated as zero.")

    with trade_tab:
        render_trade_lab(snapshot, my_id, scores, metrics, excluded, untouchable, show_trade)

    with data_tab:
        st.subheader("Data provenance & honest limits")
        st.dataframe(pd.DataFrame(snapshot["sources"]), hide_index=True, width="stretch")
        st.markdown("""
**Source:** [Sleeper's documented read-only API](https://docs.sleeper.com/). No API key, third-party stats, paid feeds, or writes to your league.

**Scoring:** `players_points` from finalized league matchups already reflects your league's scoring rules. It includes bench players who were rostered then. It is not a complete NFL statistics feed. Commissioner team-score overrides are shown in actual matchup totals, not distributed among players.

**Estimator:** A recency-weighted mean is blended with the league-observed position mean using your selected pseudo-week weight. Your risk preference adds a multiple of observed standard deviation (only with 2+ observations). Questionable players get your chosen penalty. These are explicit assumptions, not trained projections. Position pools include only players observed in this league, not the full NFL.

**Missingness:** Missing player-week records are excluded, not zero-filled. Reported zeros are retained; the API cannot tell this model whether they were byes, DNPs, or zero-point games. Players with no history remain unscored unless you manually override them. Age, practice and depth-chart information are displayed where available, not silently converted into model points.

**Optimization:** Exact maximum-weight player-to-slot assignment honors multi-position eligibility, FLEX/superflex, duplicate slots, reserve/taxi exclusions, manually excluded players and exact-slot locks. Incomplete legal lineups are flagged; negative model scores are not silently replaced by empty slots. "Optimal" means optimal for these estimates and constraints, not a guarantee of future results. FLEX kickoff timing is not optimized.

**Trades:** Each team's utility is optimized starter score plus your selected weight × positive bench scores. Automatic suggestions require a starter improvement for you, a positive utility change for you, your partner's selected loss limit, and a player-score magnitude-gap limit. That gap is NOT market fairness. Shopping includes 1-for-1 and optional 2-for-1 offers containing your chosen player. Manual packages allow 1–3 players per side. Required active-roster cuts are explicitly shown and valued; incoming players cannot be immediately cut. Open spots have no invented replacement value. No advice is automatically submitted.

**Trade safeguards:** Two observed weeks per traded player are required by default. Kickers, defenses and IDP are excluded from automated offers unless enabled. For redraft snake/linear drafts, an optional guard compares each side's earliest known non-keeper draft round within your chosen gap (default 2 rounds). This cannot establish current package value. Manual packages can bypass these guards and are scenarios, not endorsed offers.

**Weekly ideas:** Current W/L/T standings, finalized weekly scoring, peer-median slot gaps, one-starter absence stress tests, and up to four published fantasy matchup weeks inform the outlook. Standings are not official playoff seeding. Future comparisons reuse today's roster estimates, not NFL matchup/bye forecasts. Ideas are ranked by depth-adjusted gain and repairs to positional gaps, with extra weight on starter improvement when the current record, recent scoring or upcoming model gaps signal pressure.

**Time:** Only finalized weeks strictly before the target week feed the estimator. The season comes from the league ID. Current player statuses are cached for 24 hours, and even a fresh API status can lag. Historical comparisons use today's roster/status context for what-if optimization, not an as-of-date roster reconstruction.

**Safety checks before setting a lineup:** Verify game start times, bye weeks, active/inactive status, news, league rules and trade deadline in Sleeper. This app has no kickoff schedule, full injury feed, snap/target counts, NFL defensive-matchup ratings or reliable rest-of-season values. No win/acceptance probabilities are invented.
""")
        with st.expander("League scoring & roster settings"):
            st.json({"scoring_settings": league.get("scoring_settings"), "roster_positions": league.get("roster_positions"),
                     "league_settings": league.get("settings"), "model": asdict(settings)})
        st.download_button("Download analysis settings", json.dumps({"league": league["league_id"], "season": league["season"],
                            "roster_id": my_id, "week": week, "history_weeks": list(history), "model": asdict(settings),
                            "exclude_unavailable": exclude_injury, "excluded": sorted(excluded), "locks": locks,
                            "untouchables": sorted(untouchable), "overrides": overrides, "sources": snapshot["sources"]}, indent=2),
                           "sleeper_analysis_settings.json", "application/json")


if __name__ == "__main__":
    main()