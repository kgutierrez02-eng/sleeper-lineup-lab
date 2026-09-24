"""Trade screens isolated from the main app so package search is testable."""

from dataclasses import asdict
import hashlib
import json

import pandas as pd
import streamlit as st

from sleeper_app.analysis import active_players, player_name, starter_slots
from sleeper_app.presentation import score_table
from sleeper_app.trades import (PackageEvaluator, TradeFilters, contextualize, league_context,
                                roster_capacity, search_packages)


def render_trade_lab(snapshot, my_id, scores, metrics, excluded, untouchable, show_trade):
    league, players, rosters, names = (snapshot[k] for k in ("league", "players", "rosters", "names"))
    mine = next(r for r in rosters if r["roster_id"] == my_id)
    active, slots = active_players(mine), starter_slots(league)
    state = snapshot["state"]
    settings = league.get("settings") or {}
    label = lambda p: f"{player_name(p, players)} · {players.get(p, {}).get('position', '?')} [{p}]"
    st.subheader("Trade lab · shop, plan, compare")
    st.caption("Read-only scenarios using current rosters. Both teams are re-optimized. Global exclusions and Keep players apply; weekly lineup locks do not. No picks, FAAB, IR/taxi promotions or invented waiver replacements.")
    st.warning("Historical scoring is not rest-of-season or market value. A suggested package is a conversation starter, not an endorsement or acceptance prediction.")
    if settings.get("disable_trades") or (settings.get("trade_deadline") and int(state.get("week") or 0) > int(settings["trade_deadline"]) and str(league["season"]) == str(state.get("season"))):
        st.warning("Trades may be disabled or past the league deadline. All ideas are hypothetical.")
    with st.expander("Trade search controls", expanded=True):
        columns = st.columns(3)
        depth = columns[0].slider("Bench depth weight", 0.0, 0.5, 0.15, 0.05)
        gap = columns[1].slider("Max player-score magnitude gap (%)", 0, 100, 35, 5)
        partner_loss = columns[2].slider("Allow partner utility loss", 0.0, 10.0, 0.0, 0.5)
        min_gain = st.slider("Minimum improvement to your starting lineup", 0.1, 10.0, 0.5, 0.1)
        min_history = st.slider("Minimum observed weeks per trade player", 1, 8, 2,
                                help="Manual scores do not bypass this evidence filter. One-week offers are speculative.")
        packages = st.checkbox("Allow adding a second player of mine (2-for-1)", True)
        specialists = st.checkbox("Include kickers, defenses and IDP in automatic trade ideas", False)
        draft_rounds = {str(p["player_id"]): int(p["round"]) for p in snapshot.get("draft_picks", [])
                        if p.get("player_id") and p.get("round") and not p.get("is_keeper")}
        guard_supported = bool(draft_rounds) and (snapshot.get("draft") or {}).get("type") in {"snake", "linear"} and settings.get("type", 0) == 0
        guard = st.checkbox("Require comparable original draft rounds", value=guard_supported, disabled=not guard_supported)
        draft_gap = st.slider("Maximum original draft-round gap", 0, 10, 2, disabled=not guard)
        st.caption("Package draft guard compares the earliest drafted player on each side, not a sum of rounds. Unknown/keeper costs are omitted when enabled. Original draft cost is not today's market value.")
        target_options = sorted({p for r in rosters if r["roster_id"] != my_id for p in active_players(r)})
        targets = st.multiselect("Optional target players (empty = all eligible teams)", target_options, format_func=label)
    filters = TradeFilters(min_history, min_gain, gap / 100, partner_loss, depth, packages, specialists, draft_gap)
    if len(snapshot["history"]) < min_history:
        st.info(f"Only {len(snapshot['history'])} finalized week(s) loaded; the search requires {min_history} observations per traded player. Wait for more data or lower the threshold for speculative ideas.")
    fingerprint = hashlib.sha256(json.dumps({"league": league, "rosters": rosters, "my_id": my_id, "scores": scores,
        "weeks": {p: m["weeks"] for p, m in metrics.items()}, "excluded": sorted(excluded), "keep": sorted(untouchable),
        "filters": asdict(filters), "targets": targets, "draft": draft_rounds if guard else None,
        "history": snapshot["history"], "schedule": snapshot.get("schedule", {})}, sort_keys=True).encode()).hexdigest()

    def find(anchor=None, one_for_one=False):
        chosen = TradeFilters(**{**asdict(filters), "include_packages": False}) if one_for_one else filters
        return search_packages(rosters, my_id, league, players, scores, metrics, excluded, untouchable, chosen,
                               anchor, set(targets) if targets else None, draft_rounds if guard else None)

    def render_results(ideas, prefix):
        if not ideas:
            st.info("No supported offers meet these filters. Check history, Keep/exclusions, draft guard and positional coverage. No trade is better than forcing an unsupported deal.")
            return
        st.caption(f"{len(ideas)} qualifying scenarios; showing the top 12. Cuts are hypothetical and must be agreed to by the other manager.")
        for i, trade in enumerate(ideas[:12], 1):
            outgoing = " + ".join(player_name(p, players) for p in trade["give"])
            incoming = " + ".join(player_name(p, players) for p in trade["receive"])
            with st.expander(f"{prefix} {i} · {outgoing} → {incoming} · lineup {trade['my_gain']:+.2f}"):
                for reason in trade.get("reasons", []):
                    st.write("• " + reason)
                st.caption("Original draft rounds: " + " / ".join(f"{player_name(p, players)}: {draft_rounds.get(p, 'unknown')}" for p in trade["give"] + trade["receive"]))
                show_trade(trade, names, players, slots, metrics, scores)

    shop, weekly, manual = st.tabs(["Shop a player", "Potential weekly ideas", "Manual package"])
    with shop:
        st.markdown("### Who would you move?")
        anchor = st.selectbox("My player to shop", active, index=None, placeholder="Select a player from your active roster", format_func=label,
                              key=f"shop_anchor_{league['league_id']}_{my_id}")
        st.caption("Every result includes this player. With packages enabled, the search also tests each eligible teammate as an add-on, weighs lost depth, and accounts for the partner's required roster cut.")
        if anchor in untouchable:
            st.warning("This player is marked Keep. Remove that mark before shopping them.")
        if anchor in excluded:
            st.warning("This player is excluded. Resolve the exclusion before shopping them.")
        if st.button("Find targets for my player", type="primary", disabled=anchor is None):
            with st.spinner("Testing single-player offers and teammate add-ons…"):
                st.session_state.shop_results = (fingerprint, anchor, find(anchor))
        saved = st.session_state.get("shop_results")
        if saved and saved[:2] == (fingerprint, anchor):
            render_results(saved[2], "Target")
        elif saved:
            st.caption("Player or assumptions changed. Search again for current results.")
        # Retain the quick league-wide 1:1 screen from the original release.
        if st.button("Find one-for-one trade ideas"):
            with st.spinner("Comparing one-for-one swaps…"):
                st.session_state.trade_search = (fingerprint, find(one_for_one=True))
        saved = st.session_state.get("trade_search")
        if saved and saved[0] == fingerprint:
            render_results(saved[1], "Swap")

    with weekly:
        st.markdown("### Weekly team outlook & potential trade ideas")
        horizon = st.slider("Planning horizon (fantasy matchup weeks)", 1, 4, 3)
        context = league_context(snapshot, my_id, scores, excluded, horizon)
        standing = context["standing"]
        cols = st.columns(3)
        cols[0].metric("Current record", standing["Record"])
        cols[1].metric("Table position", f"{standing['Table rank']} / {len(rosters)}")
        cols[2].metric("Recent team scoring change", "Not enough history" if context["trend"] is None else f"{context['trend']:+.2f}")
        st.caption("Table sorted by current win percentage, then points for; tied rows share rank. NOT official playoff seeding (divisions/tiebreak rules may differ). Standings are current, even when analyzing a past week.")
        score_table(pd.DataFrame(context["standings"]).drop(columns=["roster_id", "Wins", "Losses"]))
        st.markdown("#### Where your lineup trails the league")
        score_table(pd.DataFrame(context["needs"]))
        weak = [r["Slot group"] for r in context["needs"] if r["Gap / slot"] is not None and r["Gap / slot"] < -0.01]
        st.write("Potential upgrade priorities: " + (", ".join(weak) if weak else "no scored slot group below the peer median"))
        if context["injured"]:
            st.warning("Unavailable-status exposure: " + ", ".join(player_name(p, players) for p in context["injured"]))
        if context["missing"]:
            st.warning("Unfilled model slots: " + ", ".join(context["missing"]))
        a, b = st.columns(2)
        with a:
            st.markdown("#### Finalized weekly performance")
            score_table(pd.DataFrame(context["weekly"]))
            st.caption("Scoring ranks within each observed week, not reconstructed weekly win/loss standings. Trend compares the latest two vs prior two weeks, or latest one vs prior one with 2–3 observations.")
        with b:
            st.markdown("#### Selected week & upcoming fantasy opponents")
            score_table(pd.DataFrame(context["upcoming"]))
            st.caption("Static current-roster model gap (yours minus opponent). Reuses current estimates each week; no NFL bye, kickoff or injury forecasts. Unpublished matchups and playoffs are not guessed.")
        with st.expander("Depth stress test: what if a starter is unavailable?"):
            score_table(pd.DataFrame(context["risks"]).drop(columns=["id"], errors="ignore"))
            st.caption("Removes one starter at a time and re-optimizes. This is vulnerability analysis, not an injury forecast. Empty results mean insufficient scored coverage.")
        if context["pressure"]:
            st.info("Current results or upcoming model gaps favor prioritizing immediate starter improvement. Do not sacrifice essential depth based on a small sample.")
        else:
            st.info("No current pressure signal from the available results/schedule. Rank offers by depth-adjusted value and repairing below-median slot groups.")
        if st.button("Develop weekly trade ideas", type="primary"):
            with st.spinner("Finding roster-fit trades, then ranking them against your weekly outlook…"):
                st.session_state.weekly_ideas = (fingerprint, horizon, contextualize(find(), context, snapshot, scores))
        saved = st.session_state.get("weekly_ideas")
        if saved and saved[:2] == (fingerprint, horizon):
            render_results(saved[2], "Idea")
        elif saved:
            st.caption("Outlook inputs changed. Develop ideas again to refresh the recommendations.")
        st.caption("Ranking = your depth-adjusted gain + repair of below-median slot gaps; add starter gain when losing record, mostly below-median weekly scoring, or negative upcoming model gaps signal pressure. No manager motives are inferred.")

    with manual:
        st.markdown("### Compare your own package (up to 3 per side)")
        partners = [r for r in rosters if r["roster_id"] != my_id]
        if partners:
            partner_id = st.selectbox("Trade partner", [r["roster_id"] for r in partners], format_func=lambda r: names[r])
            partner = next(r for r in partners if r["roster_id"] == partner_id)
            a, b = st.columns(2)
            give = a.multiselect("You send (up to 3)", active, format_func=label, max_selections=3)
            receive = b.multiselect("You receive (up to 3)", active_players(partner), format_func=label, max_selections=3,
                                    key=f"receive_{partner_id}_{league['league_id']}")
            if st.button("Evaluate this package"):
                try:
                    trade = PackageEvaluator(slots, players, scores, roster_capacity(league), excluded, depth).evaluate(
                        active, active_players(partner), give, receive, untouchable)
                    trade["roster_id"] = partner_id
                    st.warning("Manual scenarios bypass automatic evidence, draft-cost, target, gain and Keep-offer filters. Necessary cuts and global exclusions still apply.")
                    show_trade(trade, names, players, slots, metrics, scores)
                except ValueError as exc:
                    st.error(str(exc))