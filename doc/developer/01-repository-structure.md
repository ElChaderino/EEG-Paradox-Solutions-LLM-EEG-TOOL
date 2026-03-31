# Developer Guide 01 — Repository Structure

## Objective

Map directories and modules to responsibilities. New contributors **shall** read this before editing.

## Top level

| Path | Role |
|------|------|
| `hexnode/` | Python application package (import name `hexnode`). |
| `web/` | Next.js 16 frontend. |
| `scripts/` | Standalone utilities (reflection, Discord bridge). |
| `data/` | Runtime data (gitignored by default); created at operation. |
| `doc/` | Documentation (this tree). |
| `src-tauri/` | Tauri v2 desktop shell (Windows); bundles or dev-loads the web UI. |
| `dist/paradox-api/` | Packaged Python API tree referenced by Tauri `bundle.resources` (release builds); includes `eeg-worker/paradox-eeg-worker.exe` after `scripts/build_backend.ps1`. |
| `dist/paradox-eeg-worker/` | Intermediate PyInstaller output for the science stack worker (copied into `dist/paradox-api/eeg-worker/`). |
| `paradox-api.spec` | PyInstaller spec for the lean API executable. |
| `paradox-eeg-worker.spec` | PyInstaller spec for MNE / Plotly / scipy / matplotlib / sklearn / networkx / statsmodels worker. |
| `eeg_subprocess_launcher.py` | Worker entry: `runpy` for viz scripts, `--eeg-probe`, `PYTHONPATH` injection when frozen. |
| `run_server.py` | Development entry: uvicorn with reload. |
| `VERSION` | Single-line app semver; `scripts/bump_version.ps1` syncs Tauri, Python, and web `package.json`. |
| `CHANGELOG.md` | Human-readable release history. |
| `pyproject.toml` | Package metadata and dependencies. |
| `requirements.txt` | Flat dependency list (includes packages needed to **build** the EEG worker). |
| `.env.example` | Template for environment configuration. |

## Package `hexnode`

| Module | Responsibility |
|--------|----------------|
| `config.py` | `Settings` singleton via `pydantic-settings`; env loading. |
| `ollama_client.py` | Async HTTP to Ollama (embed, generate, chat, ping). |
| `memory_store.py` | Chroma persistent client; collections; scoring helpers. |
| `ingest_watcher.py` | Background polling of ingest queue. |
| `reflection.py` | Reflection pass implementation. |
| `agent/` | `run_agent`, prompts. |
| `api/main.py` | FastAPI app, routes, lifespan. |
| `tools/` | One module per tool class; `registry.py` discovery. |
| `eeg/` | EEG orchestration: `viz/run_visualizations.py` (figures + NetOps subprocess), `netops_runner.py` / `netops_standalone/` (Granger → traceroute → analyses → HTML emitters), `pipeline.py` (decoder-style script generation). |

## Tool module convention

Each file **shall** define exactly one concrete subclass of `Tool` whose `__module__` matches the file (required for discovery). Class **shall** set `name` and `description` and implement `async def run(self, ctx, **params)`.

## Extension points

- New tools: add module under `hexnode/tools/`.
- New HTTP routes: extend `hexnode/api/main.py` (or refactor to routers if growth demands).
- Agent policy: `hexnode/agent/loop.py` and `hexnode/agent/prompts.py`.

## Related

- `developer/03-architecture.md` — control flow.
- `reference/tools-catalog.md` — current tool list.
