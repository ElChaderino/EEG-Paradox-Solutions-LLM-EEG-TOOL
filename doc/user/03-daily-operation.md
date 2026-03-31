# User Manual 03 — Daily Operation

## Objective

Describe the standard operating cycle: start services, use interfaces, stop cleanly.

## Starting the inference layer

1. Ensure Ollama is running.
2. Confirm models are present: `ollama list`.

## Starting everything (Windows launcher)

From project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\launch.ps1
```

Or double-click **`launch.bat`** or **`Launch Paradox.bat`** in the project root (same launcher). Two console windows start (API + web); the default script also opens `http://localhost:3000`. Close those windows to stop.

## Starting the API (Paradox core) only

From project root, venv active:

```powershell
python run_server.py
```

**Default:** HTTP server on `HOST`:`PORT` from `.env` (`0.0.0.0:8765`).

**Background behavior:** An ingest watcher task runs for the lifetime of the process. It polls `data/ingest_queue` on a fixed interval (see `hexnode/ingest_watcher.py`).

## Starting the web console

```powershell
cd web
npm run dev
```

Default URL: `http://localhost:3000`.

If the API is not at `http://127.0.0.1:8765`, set in `web/.env.local` or in the shell before `npm run dev` (preferred name first):

```powershell
$env:NEXT_PUBLIC_PARADOX_API="http://127.0.0.1:8765"
# Legacy aliases still work: NEXT_PUBLIC_HEX_API, NEXT_PUBLIC_ANTON_API
```

The **Tauri** desktop build uses `http://127.0.0.1:8765` when running inside the app shell; see `user/08-desktop-tauri.md`. The packaged app starts **`paradox-api.exe`** as a sidecar and, when built with `scripts/build_release.ps1`, includes **`eeg-worker/paradox-eeg-worker.exe`** for EEG visualization jobs—no separate `python run_server.py` step for operators.

**Quick check:** `GET /health` (browser or `curl`) reports Ollama, license summary, norms add-on, and `eeg_subprocess` (bundled worker vs custom interpreter).

## Stopping

1. Stop the Next.js process (Ctrl+C in its terminal).
2. Stop the API process (Ctrl+C). The lifespan handler cancels the watcher and closes the Ollama HTTP client.

**Shall not:** Terminate the API with hard kill during active Chroma writes if avoidable; risk of partial state is low with PersistentClient but not zero under filesystem stress.

## Optional: Discord bridge

With `DISCORD_TOKEN` and `DISCORD_CHANNEL_ID` set:

```powershell
python scripts\discord_bot.py
```

Set `PARADOX_API` if the API is not the local default (legacy: `HEX_API`, `ANTON_API`).

## Optional: scheduled reflection

Use Windows Task Scheduler to run, at desired local time:

```powershell
.\.venv\Scripts\python.exe scripts\reflect.py
```

Working directory **shall** be the project root so imports resolve if the script is invoked relatively.

## Layer summary

| Layer | Process | Port (typical) |
|-------|---------|----------------|
| Ollama | `ollama` | 11434 |
| Paradox API | `uvicorn` / `run_server.py` | 8765 |
| Web UI | `next dev` | 3000 |

Next: `user/04-web-console.md`.
