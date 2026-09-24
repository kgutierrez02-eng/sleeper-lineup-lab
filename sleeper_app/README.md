# Sleeper Lineup Lab 1.2

## Standalone Windows app (recommended)

The **Sleeper Lineup Lab Desktop** distribution includes a native launcher, an
EXE and all required runtime libraries. **No installed Python, virtual environment,
pip or dependency setup is required.** Extract the complete ZIP and open the EXE.
Keep its _internal folder beside it. The launcher opens the dashboard in your
existing browser; closing the launcher stops its local server.

Standalone settings/cache/logs live in **%LOCALAPPDATA%\SleeperLineupLab**, separate
from the distributable. See [STANDALONE.md](STANDALONE.md) for recipient instructions.
It is an unsigned Windows x64 build; organization/security policy may require review.

A local browser app for your Sleeper roster, weekly opponent, lineup experiments,
and two-sided trade analysis. Uses **only Sleeper's documented public API**.
It never changes lineups, submits trades, or asks for a Sleeper password.

## Run the development/source copy

1. In File Explorer, double-click [Open Sleeper App.bat](../Open%20Sleeper%20App.bat)
  in the parent app folder. A browser window opens automatically when ready.
2. Leave its console window open while using the app. Press **Ctrl+C** in that
   console to stop the server. Closing the browser alone does not stop it.
3. Optionally right-click the launcher and use **Send to → Desktop (create shortcut)**.

The launcher binds only to **127.0.0.1**, with usage telemetry disabled. It chooses
the first free port from **8501–8521**, prints the URL, and opens the browser.
Do not start a second copy if one is already running; reopen the printed URL instead.
Internet access is needed for fresh league data.
Only the source copy needs Python **3.11 or newer** with dependencies already
available. Its launcher uses the existing interpreter and never creates an
environment or installs packages. If dependencies are missing, use the standalone
EXE instead. The parent batch launcher prefers the built desktop EXE when present.

The original [sleeper_pull.py](../sleeper_pull.py) CLI still works; its new `--app`
option opens the app and `--week` selects a week when `--show-matchups` is used.
When using `--app`, change league/team/week inside the app, not via other CLI flags.

## Your connection

On a clean installation, enter your own Sleeper league ID and username, then
choose a week and select **Load league**. No account credentials are required.
Your existing local saved connection is preserved when using the development copy;
personal preferences and downloaded data are never included by the distribution builder.

The current roster is fetched each time the connection refreshes; players are
not hardcoded. The **season comes from the league ID**. To switch seasons, use
**Find a different season / league**, copy the resulting ID into the connection
form, and choose **Load league**.

**Save connection as startup default** saves league, username and week locally.
Model settings, manual score overrides, exclusions, and locks are session-only;
changing league/team/week resets the associated player controls. The Sources tab
can export analysis settings for reference (settings import is not implemented).

## Screens

- **Matchup:** recorded starters and actual/live Sleeper scores for both teams;
  optional opponent optimized-current-roster scenario.
- **Lineup optimizer:** currently set lineup vs. exact best legal assignment
  under your model assumptions. Includes promotions/bench changes and CSV export.
- **Player metrics:** league-scored weekly history, mean, recency-weighted mean,
  standard deviation, injury/status, practice, depth order, age, experience,
  and original draft pick/round wherever the API supplies them.
- **Trade lab → Shop a player:** choose one of your players and search for targets.
  Every offer includes that player. Optionally add another teammate for 2-for-1
  packages; the search counts lost depth and any necessary partner roster cut.
- **Trade lab → Potential weekly ideas:** current standings, finalized weekly
  performances, positional weaknesses, depth stress tests and published upcoming
  fantasy opponents. Develop explained trade ideas using that context.
- **Trade lab → Manual package:** up to three players per side, including unequal
  packages. Both rosters are re-optimized, with required cuts explicitly shown.
- **Sources & model:** endpoint URLs, download times, live/cache/stale status,
  league scoring rules, model definitions and limitations.

## Useful controls

| Control | Meaning |
| --- | --- |
| Completed weeks to use | Up to the selected number of finalized prior weeks; no future/target-week leakage. |
| Older-week weight multiplier | 1 = equal weights; 0.8 gives each preceding week 80% of the next week's weight. |
| Position-mean shrinkage | Strength of the league-observed position mean used to soften small-sample spikes. |
| Risk preference | Adds/subtracts observed standard deviation; not a guaranteed ceiling/floor. |
| Questionable penalty | Adjustable reduction in the model score; not an injury probability. |
| Exclude unavailable | Excludes current Out/IR/PUP/Suspended/Doubtful designations. |
| Manual score | An explicit user assumption replacing the calculated model score. |
| Exclude player | **Global** exclusion from all lineup and trade scenarios; useful for byes/inactives. |
| Keep player | Prevents your player from appearing in automatic trade offers. Manual inspection still allowed. |
| Lock current starters | Keeps selected players in their exact current slots, including FLEX. |
| Trade history minimum | Default two observed weeks for each offered/received player. Manual overrides do not bypass this. |
| Draft-round guard | Default maximum two-round gap in original draft cost, where supported. |
| Add a second player | Compare 2-for-1 consolidation offers as well as 1-for-1 swaps. |
| Planning horizon | Selected week plus up to three more published regular-season fantasy matchup weeks. |
| Include specialists | Off by default: avoids short-term kicker/defense/IDP swaps in automatic suggestions. |
| Bench depth weight | Weight assigned to positive bench scores in both teams' trade utility. |
| Partner utility loss | Default zero; do not propose a trade that lowers the partner's modeled utility. |
| Player-score magnitude gap | A heuristic filter, **not** market fairness or likelihood of acceptance. |

For an already-started week, manually lock started starters and exclude started
bench players. The app has **no NFL kickoff or bye-week schedule**. Verify eligibility,
status, timing and all changes in Sleeper before acting. Automatic game locks
and FLEX kickoff ordering are not implemented.

## How the model works

Score tables, model metrics, manual score entries and CSV exports use **two
decimal places**. Internal calculations retain full precision; displayed rounded
player scores may not sum exactly to a displayed rounded total.

For each player, prior finalized `players_points` observations are already scored
according to this league's settings. With weekly recency weights `w`, the baseline
is `(sum(w * points) + prior_weight * position_mean) / (sum(w) + prior_weight)`.
The position mean uses one mean per observed player in this league, not the entire NFL.
The risk adjustment adds `risk * observed_standard_deviation` when at least two
observations exist. A Questionable penalty reduces the score by the selected
fraction of its absolute magnitude. Other metadata is shown for judgment, not
secretly converted into fantasy points.

Missing player-week records are not zero-filled. Reported zero scores are retained;
this API cannot distinguish zero-point games from byes/DNPs. A player with no
observations remains **unscored** until you provide a manual assumption. That
includes players who were not on any roster in the selected historical weeks.
There is no complete NFL/free-agent coverage.

The lineup solver performs maximum-weight bipartite assignment, not greedy FLEX
selection. It honors positions, duplicate slots, FLEX/superflex, supported IDP
groups, exclusions and exact-slot locks. Reserve/taxi players never become active
implicitly. Negative-scoring players still fill required slots when eligible;
unfillable slots and incomplete totals are clearly flagged. Players without
position metadata cannot be legally assigned, even with a manual score.

Trade utility = optimized starter total + bench weight × positive eligible bench
scores. Both teams are re-optimized, without one-week starter locks. Automatic
offers must improve your starting lineup and total utility while meeting the
partner-loss, evidence and gap filters. The draft-cost guard uses the league's
non-keeper snake/linear redraft picks; undrafted or missing-cost players are
omitted when it is enabled. It is unavailable by default for auction/keeper/dynasty
formats. Original draft cost is a guard against some extreme offers, **not current
market value**. For packages the guard compares the earliest draft round on each
side; it never sums ordinal rounds or claims to price a package.

Automatic searches cover every eligible 1-for-1 offer and, if enabled, each pair
of your eligible players for one target. A selected player is included in every
shopping result. The UI shows the top twelve qualifying scenarios, not a promise
that a manager would accept them. Unequal packages explicitly account for active
roster capacity (starting slots plus bench). If over capacity after a trade, the
receiving team's hypothetical cut maximizes retained legal lineup/depth value.
Incoming players are not cut immediately; your Keep players cannot be cut. Any
open spot has **zero assumed waiver-replacement value**. Cuts are clearly listed
and require manual agreement/actions in Sleeper. Current over-capacity rosters
must first be corrected. IR/taxi trades, FAAB, future picks, keeper/contract values
and transaction approval are not modeled.

### Weekly context

- Standings use current W/L/T and points for, with tied rows sharing table rank.
  This is not official playoff seeding or a reconstructed historical standings table.
- Finalized weekly team scores include commissioner total overrides (including zero).
  Weekly scoring ranks and recent scoring changes describe observed performance.
  Trend compares latest two vs previous two observations, or one vs one with 2–3 weeks.
- Optimized slot-group averages are compared to the other teams' median. Below-median
  groups are upgrade priorities; missing metrics are not treated as zero.
- The depth stress test removes one starter at a time and re-optimizes, displaying
  score loss or empty slots. It is a vulnerability check, not an injury prediction.
- Future fantasy matchup gaps reuse today's roster/score assumptions for both teams.
  Unpublished pairings and playoffs are not guessed. These are NOT NFL matchup,
  bye-week, kickoff or rest-of-season forecasts.
- Idea ranking adds depth-adjusted gain and repairs to below-median positional gaps.
  Losing record, mostly below-median recent scoring or a negative upcoming matchup
  gap adds an extra starter-gain weight. This intentionally emphasizes immediate
  output under pressure; it does not change player scores or infer manager motives.

## Data freshness and limits

- [Sleeper API documentation](https://docs.sleeper.com/).
- League/state/matchup data uses a five-minute disk cache. A UI interaction after
  five minutes reloads the snapshot; **Refresh league & scores** requests it sooner.
- The large player directory is refreshed at most once per 24 hours, following
  Sleeper's guidance. The refresh button does **not** bypass this limit. Draft data
  is also cached for 24 hours.
- On API failure, a previous cached response can be shown, with prominent **STALE**
  warnings and its original download time. No cached copy means an actionable error.
- Only weeks finalized according to league/NFL state and strictly before the
  target week feed the model. Partial Week 2 scores are not Week 3 projections.
- Historical matchup displays are recorded results; what-if lineup/trade analysis
  uses the league's current roster and today's player metadata. It is not a backtest.
- No official projections, complete injury news, targets, snap counts, weather,
  NFL defensive-matchup strength, rest-of-season values, win probabilities or trade
  acceptance probabilities are fabricated.

**Early in a season there may be too few finalized weeks.** The safe default trade
history filter may therefore produce no offers. Lowering it allows speculative
scenarios, but a one-week point swing is not a sound reason to trade away a
high-value player. More finalized results will become available automatically.

## Validation

The offline suite in [tests/test_analysis.py](tests/test_analysis.py),
[tests/test_data.py](tests/test_data.py), [tests/test_app.py](tests/test_app.py),
[tests/test_trades.py](tests/test_trades.py), [tests/test_distribution.py](tests/test_distribution.py)
and [tests/test_launcher.py](tests/test_launcher.py) covers optimizer optimality
against brute force, FLEX and locks, missing/negative scores, histories, cache
failures, bilateral packages and cuts, anchor/evidence/draft guards, standings and
trends, score formatting, Streamlit interactions, clean distributions and port conflicts.
Native-launcher storage, EXE relaunch, cleanup and safe build replacement are
covered by [tests/test_desktop.py](tests/test_desktop.py).
Install the separate development requirements to run the included pytest suite.

[verify_sleeper_exe.py](../verify_sleeper_exe.py) tests the actual built EXE with
Python environment variables removed and only Windows System32 on PATH. It
validates bundled analysis and app rendering, native-window startup, local HTTP
health and shutdown cleanup. The test controller uses the existing development
interpreter; this is an isolation test, not a claim of testing on a fresh Windows VM.

## Build a clean shareable folder

For the standalone release, [build_sleeper_exe.py](../build_sleeper_exe.py) uses
PyInstaller in the existing interpreter. It does not create an environment. The
spec explicitly collects app modules and dependency resources, not preferences,
caches or unrelated workspace files. The resulting folder includes third-party
notices, build information, a checksum manifest and recipient instructions.
Share the entire desktop folder/ZIP, not just the EXE.

[build_sleeper_distribution.py](../build_sleeper_distribution.py) copies only an
explicit file allowlist into a fresh distribution folder. Existing destinations
are refused rather than overwritten. It includes a first-run guide and SHA-256
manifest, not virtual environments, caches, preferences, secrets or unrelated files.
Zip that clean folder **before launching it**. Rebuild a fresh clean folder to
redistribute after using the app. See [DISTRIBUTION.md](DISTRIBUTION.md) for recipient
setup, troubleshooting and non-commercial Sleeper API usage guidance.