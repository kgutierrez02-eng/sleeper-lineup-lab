# Sleeper Lineup Lab — Standalone macOS App

**No Python installation. No virtual environment. No pip or dependency setup.**
The required runtime and libraries are included with the app.

## Open it

1. Unzip the downloaded ZIP; you get **Sleeper Lineup Lab.app**.
2. Move it to **Applications** (or anywhere) and double-click it.
3. This build is **unsigned/not notarized**, so macOS Gatekeeper will refuse
   the first launch ("cannot be opened because the developer cannot be
   verified"). **Right-click (or Control-click) the app > Open**, then
   confirm **Open** in the dialog. You only need to do this once.
   Alternatively, run `xattr -cr "Sleeper Lineup Lab.app"` in Terminal first.
4. A desktop control window appears. Once ready, your default browser opens
   the complete lineup and trade dashboard. You can also select **Open dashboard**.
5. Enter your own Sleeper league ID and username. No password or API key is needed.
6. Keep the desktop control window open. Close it to stop this copy of the app.
   Closing just the browser tab does not stop the server.

## Your saved data

Settings, cached API data and logs are stored separately at:

**~/Library/Application Support/SleeperLineupLab**

The **Open logs & settings** button opens that folder in Finder. Preferences
survive app updates. To reset the app, close it first, then remove only that
app-data folder.

## Limits and safety

All Sleeper access is read-only. No lineups, drops or trades are submitted.
The local server listens only on **127.0.0.1**, not your network. Internet is
needed only for fresh Sleeper league data, not to install software.

This release targets macOS (Apple Silicon or Intel, matching the build you
downloaded). The app is not affiliated with Sleeper.

## Troubleshooting

- **"App is damaged" / refuses to open:** run `xattr -cr "Sleeper Lineup Lab.app"`
  in Terminal, then try again.
- **Startup error:** use Open logs & settings and inspect the latest runtime/server log.
- **Server stopped:** choose Restart in the desktop window.
- **Blocked by policy/security:** ask your IT/MDM admin to allow the app.
