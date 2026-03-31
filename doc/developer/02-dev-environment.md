# Developer Guide 02 — Development Environment

## Objective

Standardize local development so builds are repeatable.

## Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[discord]"
```

**Shall:** Not commit `.venv/` or `.env` (secrets).

## Running the API with reload

```powershell
python run_server.py
```

Uses uvicorn import string `hexnode.api.main:app` with `reload=True` for development.

**Production note:** Use explicit `uvicorn` or a process manager; disable reload.

## Running the web client

```powershell
cd web
npm install
npm run dev
```

**Build verification:**

```powershell
npm run build
```

## Import path

The package **shall** be installed editable (`pip install -e .`) so `import hexnode` resolves from any working directory when the venv is active.

Scripts under `scripts/` prepend the repository root to `sys.path` when executed as files; **shall** be run with project root as cwd for consistency.

## Static checks

No project-enforced linter is mandatory in v0.1.0. Contributors **may** add `ruff` or `mypy` in a follow-on change; if added, document commands here.

## Debugging tips

- Set `LOG_LEVEL` via standard logging configuration if extended (not default).
- Use `GET /tools` to verify registry after adding a tool module.
- Use `GET /health` before `/agent` during integration tests.

## Tauri desktop shell

The `src-tauri/` crate builds the **Paradox Solutions LLM** Windows app. Prerequisites: **Rust** (stable), same **Node** / **web** setup as above, and the FastAPI API running (or bundled per your release pipeline).

**Development** (starts `npm run dev` for the webview via `beforeDevCommand`):

```powershell
cd src-tauri
cargo tauri dev
```

**Production build** — from repo root, prefer the full pipeline so the API bundle includes the EEG worker:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1
```

That builds `web/out`, runs `scripts/build_backend.ps1` (worker + API), then `cargo tauri build --ci`. To build installers only after a successful backend freeze: `cd src-tauri` and `cargo tauri build --ci`.

**EEG worker build:** the venv used for PyInstaller **shall** satisfy `requirements.txt` / `pip install -e ".[eeg]"` so `paradox-eeg-worker.spec` collects MNE, statsmodels, etc.

Operator-oriented notes: `user/08-desktop-tauri.md`.

## Related

- `user/02-installation.md` — operator-oriented install.
- `reference/configuration.md` — env vars.
