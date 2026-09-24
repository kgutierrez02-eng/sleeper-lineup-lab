# Sleeper Lineup Lab — Standalone Windows App

**No Python installation. No virtual environment. No pip or dependency setup.**
The required runtime and libraries are included with the app.

## Open it

1. Extract the **entire ZIP** into a folder on your Windows 10/11 x64 computer.
2. Double-click **Sleeper Lineup Lab.exe**.
3. A desktop control window appears. Once ready, your default browser opens the
   complete lineup and trade dashboard. You can also select **Open dashboard**.
4. Enter your own Sleeper league ID and username. No password or API key is needed.
5. Keep the desktop control window open. Close it to stop this copy of the app.
   Closing just the browser tab does not stop the server.

Keep the **_internal** folder beside the EXE. This is a portable application
folder, not an installer or a single-file executable. Do not move only the EXE.
You can create a desktop shortcut to it. No administrator access is normally needed.

The dashboard uses your existing browser; it is not embedded in the control window.
The local server listens only on **127.0.0.1**, not your network. It picks a free
port automatically. Internet is needed only for fresh Sleeper league data, not
to install software. Runtime telemetry is disabled.

## Your saved data

Settings, cached API data and logs are stored separately at:

**%LOCALAPPDATA%\SleeperLineupLab**

The **Open logs & settings** button opens that folder. Preferences survive app
updates. To reset the app, close it first, then remove only that app-data folder.
Different Windows users have separate data. No personal league settings are
included in this release. The development/source copy's settings are not imported
automatically; enter your league once and save it in the dashboard.

## Features

- Matchup viewer, two-decimal model scores and exact lineup-slot optimization.
- Shop a player, optional teammate add-ons for two-for-one packages, required
  roster-cut accounting and manual package comparisons.
- Weekly trade ideas informed by standings, finalized performance, positional
  gaps, depth risks and published upcoming fantasy opponents.

## Limits and safety

All Sleeper access is read-only. No lineups, drops or trades are submitted.
Historical model scores are not official projections or market values. Check NFL
byes, injuries, kickoff locks, roster limits and trade rules in Sleeper before acting.
No NFL schedule/bye forecasts or rest-of-season values are invented. Safe trade
defaults need two observed weeks per traded player; early-season results can be sparse.

## Sharing and updates

Share the complete ZIP or zip this entire application folder. Personal settings
remain outside it. Do not include the LocalAppData folder. Dependencies and their
notices are bundled; keep the license files with the app. The checksum manifest
is an integrity aid, not a digital signature.

This build is **unsigned**. Windows SmartScreen or organization policy may require
approval. Only run a copy from a source you trust; do not disable security software.
For broader distribution, arrange code signing and any required IT approval.

The app is not affiliated with Sleeper. Sleeper documents free API access for
non-commercial use; contact Sleeper regarding commercial licensing.

## Troubleshooting

- **Startup error:** use Open logs & settings and inspect the latest runtime/server log.
- **Dashboard closed:** choose Open dashboard; no restart or reinstall is needed.
- **Server stopped:** choose Restart in the desktop window.
- **Missing DLL/resource:** re-extract the whole ZIP; preserve _internal and its contents.
- **Blocked by policy/security:** ask IT to review the build. Do not bypass protections.
- **No trade suggestions:** review the history minimum, Keep/exclusion and draft filters.
- **Fresh data unavailable:** check internet access; stale cached data is clearly labeled.

This release targets Windows x64. A native ARM64, macOS or Linux build is not included.