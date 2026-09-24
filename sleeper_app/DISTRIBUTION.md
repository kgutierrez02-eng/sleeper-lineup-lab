# Sleeper Lineup Lab — Source edition

**For no-install use, distribute the standalone Windows desktop build instead.**
That EXE includes its runtime; recipients do not need Python, pip or a new environment.
The instructions below apply only to developers using the optional source edition.

## Windows setup

1. **Extract the entire ZIP** into a writable folder. Do not run inside the ZIP.
2. Install **64-bit Python 3.11 or newer** from [python.org](https://www.python.org/downloads/windows/)
   if it is not already installed. Include the Python launcher (`py`) during installation.
3. Double-click **Open Sleeper App.bat** in this folder.
4. The source launcher uses your existing interpreter and dependencies. It never
  creates an environment or installs packages. Missing dependencies are reported;
  use the standalone EXE if you do not want source dependency setup.
5. Your browser opens the local app. Enter **your Sleeper league ID and username**,
   select a week, then **Load league**. No password or API key is needed.
6. Use **Save connection as startup default** if desired. Data/settings are stored
   only in this extracted folder. Do not place it in a read-only location.

The app binds only to `127.0.0.1`, choosing a free port between 8501 and 8521.
The console prints the URL. Leave that console running; **Ctrl+C** stops the app.
If the browser does not open, paste the printed URL into a browser.
This is a **source distribution, not a standalone EXE**. Python is not bundled.

## What is new

- Scores display and export to **two decimal places**; internal calculations keep full precision.
- **Trade lab → Shop a player:** select one of your players. Search 1-for-1 offers
  and optional 2-for-1 packages with a teammate added. Any required partner roster
  cut is explicitly shown and included in the value calculation.
- **Potential weekly ideas:** current standings, finalized weekly scoring,
  positional weaknesses, depth stress tests and upcoming fantasy opponents.
  Select **Develop weekly trade ideas** to generate and explain candidate packages.
- **Manual package:** inspect up to three players per side, including unequal deals.

Safe trade defaults require **two observed weeks per traded player**. Early in the
season, no offers may qualify. Lower that threshold only to explore speculative
scenarios. Draft-cost and other filters are adjustable.

## Important limitations

Uses only [Sleeper's documented public API](https://docs.sleeper.com/). All access
is read-only. The app cannot set lineups or submit trades. Historical model scores
are **not official projections or market values**. Confirm injury status, NFL byes,
game locks, roster limits, trade deadlines and all actions in Sleeper.

Future comparisons are against **fantasy opponents' current rosters**, not NFL
opponents. No bye-week, kickoff, weather, injury or rest-of-season forecasts are
invented. Standings tables are descriptive, not official playoff seeds.

Full documentation is in the **sleeper_app** subfolder's README.

## Sharing, privacy and maintenance

- Share the **clean folder produced by the builder**, before running it. Zip the
  complete folder; recipients extract all files together.
- No league ID, username, API responses, saved settings, account credentials,
  virtual environments or unrelated workspace files are shipped.
- After you use the app, do not share its generated preferences, cache or .venv.
  The included build script can create another clean folder using an allowlist.
- The checksum manifest lists the original distribution files. It is an integrity
  aid, not a digital signature or a security guarantee.
- To update, extract a new release into a new folder. Do not redistribute
  environment-specific or personal data files from your working copy.
- Third-party dependencies retain their own licenses and are downloaded, not
  bundled. Sleeper documents its free API for **non-commercial** use; contact
  Sleeper about commercial licensing. This app is not affiliated with Sleeper.

## Troubleshooting

- **Python not found:** install Python 3.11+ with the `py` launcher, then retry.
- **Install/download blocked:** check internet/proxy policy. Do not disable TLS
  verification; ask IT if managed-device policies prevent package installation.
- **Dependencies missing:** use the standalone desktop release instead; the source
  launcher does not install or repair Python environments.
- **No trade ideas:** check history threshold, untouchables, exclusions, draft
  guard and eligible roster coverage. Missing evidence is not treated as zero.
- **Stale data:** refresh league scores; player metadata is cached for 24 hours
  per Sleeper guidance. Offline fallback is explicitly labeled.

Optional developer tests are included; test dependencies are separate from the
runtime requirements. No network calls are needed for the offline regression suite.