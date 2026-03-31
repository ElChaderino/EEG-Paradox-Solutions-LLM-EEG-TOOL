# User Manual 08 — Desktop app (Tauri)

## Objective

Explain the **Paradox Solutions LLM** native Windows shell built with [Tauri](https://tauri.app/) v2: what it wraps, which services must still run, and how it differs from opening the site in a browser.

## What the desktop app is

- A window that loads the same **Next.js** UI as `npm run dev` / `npm run build` (static export under `web/out` for release builds).
- The UI talks to the **FastAPI** backend at `http://127.0.0.1:8765` (fixed in the packaged client’s API helper when Tauri is detected).
- The installer **bundles** the packaged Python API under `dist/paradox-api/` (see `src-tauri/tauri.conf.json` `bundle.resources`), including **`eeg-worker/paradox-eeg-worker.exe`** for full EEG visualization and NetOps HTML without a separate Python install.

## What you still need locally

1. **Ollama** running, with models pulled to match your `.env` (same as the browser workflow). See [01-prerequisites](01-prerequisites.md).
2. The **Paradox API process** on port **8765**. The desktop shell does not replace the API; it only hosts the frontend. In development, start `python run_server.py` from the project root (or use the launcher script). In the **released** app, Tauri **starts** `paradox-api.exe` as a sidecar after first-run setup completes.

## Development (source checkout)

Prerequisites: **Rust** toolchain, **Node**, **Python venv** as in [02-installation](02-installation.md).

Typical flow:

1. Terminal A — API: `python run_server.py`  
2. Terminal B — from `src-tauri`: `cargo tauri dev`  

Tauri runs `beforeDevCommand` (`cd ../web && npm run dev`), so the dev server on port 3000 is started for you. The dev window loads that URL.

Details: [Developer 02 — Dev environment](../developer/02-dev-environment.md#tauri-desktop-shell).

## Release build (engineers)

From the **repository root** (recommended — builds frontend, both PyInstaller targets, then Tauri):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1
```

That runs `scripts/build_backend.ps1` (EEG worker first, then API, worker copied into `dist/paradox-api/eeg-worker/`) and `cargo tauri build --ci`. MSI and NSIS outputs are under `src-tauri/target/release/bundle/msi/` and `bundle/nsis/` (version in filenames follows `VERSION` / `tauri.conf.json`).

**Manual shortcut:** after `web/out` and `dist/paradox-api/` exist, `cd src-tauri` and `cargo tauri build --ci`.

## Configuration

- **Frozen / installed app:** API settings are read from `%LOCALAPPDATA%\ParadoxSolutionsLLM\.env` when the Python side runs in PyInstaller mode (`hexnode.config`).
- **Browser vs Tauri:** In the web client, `NEXT_PUBLIC_PARADOX_API` applies when **not** under Tauri; the desktop build uses `127.0.0.1:8765` directly.

## Related

- [03 — Daily operation](03-daily-operation.md) — ports and launcher scripts  
- [04 — Web console](04-web-console.md) — UI behavior (same in the shell)  
