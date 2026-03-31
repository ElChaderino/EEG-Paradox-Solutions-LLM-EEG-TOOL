# Paradox Solutions LLM â€” Local AI Research Assistant

**GitHub:** [github.com/ElChaderino/EEG-Paradox-Solutions-LLM-EEG-TOOL](https://github.com/ElChaderino/EEG-Paradox-Solutions-LLM-EEG-TOOL)

**Closed testing / access:** If you are in the private program, the organizer link is in the repo file [`Request Access`](Request%20Access).

**Full documentation:** see the [`doc/`](doc/README.md) folder (user manuals, developer guides, technical reference, layer matrix).

**Interactive technical reference:** open [`doc/technical-reference.html`](doc/technical-reference.html) in any browser.

Fully local stack: **Ollama** (LLM + embeddings), **ChromaDB** (scored memory), **FastAPI** agent loop with modular tools, **Next.js** console (dark cyan / matrix palette, Geist fonts, Tailwind v4). Packaged as a native **Tauri v2** desktop application with auto-setup, or run from source for development.

**No cloud LLM APIs.** Optional: SearXNG, Skye (remote Ollama), Discord bridge.

**Python package:** `hexnode` (import path). **Features:** weighted memory ranking (similarity + importance + **recency decay** + manual boost), **YAML neuro-symbolic routing hints** (`hexnode/symbolic/`, optional `data/rules.yaml`), **ReAct v2** agent steps (`parse_ok`, `tool_ok`, final-step nudge), **reflection intelligence**, **file upload/management** (EEG, documents, general), **GPU optimizations** (flash attention, KV cache quantization, embedding quantization).

## Desktop Application (Recommended)

The easiest way to use Paradox is via the native desktop installer:

1. Run `Paradox Solutions LLM_0.3.2_x64-setup.exe` (NSIS) or the MSI installer.
2. Launch from the Start Menu or desktop shortcut.
3. First-run setup automatically downloads and configures Ollama, pulls required models, enables GPU optimizations, and starts the backend.

The desktop app wraps the full stack in a **Tauri v2** shell with system tray integration, automatic sidecar management, and first-run bootstrapping.

### Building the Desktop App

Requires: **Windows** (for MSI/NSIS here), **Rust** (`rustup`), **Node.js 18+**, **Python 3.11+** venv with project deps + `pip install pyinstaller`, and **Tauri CLI v2** (`cargo install "tauri-cli@^2"`). NSIS / WiX are pulled or expected by Tauri for bundling (install [NSIS](https://nsis.sourceforge.io/) via `winget install NSIS.NSIS` if the build asks for it).

The `src-tauri/` tree matches the **Super Bot / unified Paradox** desktop shell (system tray, API sidecar from `dist/paradox-api/`, first-run setup).

```powershell
# Full release build (frontend + PyInstaller API + EEG worker + Tauri MSI/NSIS)
powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1

# Or step-by-step:
cd web && npm run build && cd ..                    # Static frontend export
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_backend.ps1  # paradox-eeg-worker + paradox-api (worker copied into dist/paradox-api/eeg-worker/)
# Tauri npm hook needs repo root (paths with spaces). Prefer build_release.ps1, or from repo root:
$env:PARADOX_REPO_ROOT = (Get-Location).Path; Set-Location src-tauri; cargo tauri build --ci; Set-Location ..
```

Installers land under `src-tauri/target/release/bundle/nsis/` and `bundle/msi/` (filenames include the semver from `VERSION` / `tauri.conf.json`, e.g. `Paradox Solutions LLM_0.3.2_x64-setup.exe`).

**Release notes:** see root `CHANGELOG.md`. **Bump version:** edit `VERSION`, then run `scripts\bump_version.ps1`.

## Prerequisites (Development from Source)

- Windows 10/11, Python 3.11+, [Ollama for Windows](https://ollama.com) running (`ollama serve`).
- Pull models. **Run each line separately** in cmd or PowerShell:

  ```text
  ollama pull qwen3:8b
  ollama pull nomic-embed-text
  ```

  Optional fast model for simple queries: `ollama pull phi4-mini`

- **Strongly recommended:** a dedicated virtual environment (`python -m venv .venv`).

## GPU Optimizations

Paradox automatically configures Ollama for optimal VRAM usage:

| Optimization | Setting | Effect |
|---|---|---|
| Flash Attention | `OLLAMA_FLASH_ATTENTION=1` | Faster attention, lower VRAM for long contexts |
| KV Cache Quantization | `OLLAMA_KV_CACHE_TYPE=q8_0` | ~50% KV cache VRAM reduction (q4_0 = ~75%) |
| Embedding Quantization | `embed_quantize_bits=8` | ~4x compression of stored vectors (TurboQuant-inspired) |

These are applied automatically in the desktop app. For development, set them in `.env` or as environment variables before running `ollama serve`.

Configurable in `.env`:

```
OLLAMA_FLASH_ATTENTION=true
OLLAMA_KV_CACHE_TYPE=q8_0
EMBED_QUANTIZE_BITS=8
```

## Clone this repository

```powershell
git clone https://github.com/ElChaderino/EEG-Paradox-Solutions-LLM-EEG-TOOL.git
cd EEG-Paradox-Solutions-LLM-EEG-TOOL
```

If you cloned into a folder with a different name, `cd` into that folder before running `scripts\setup.ps1`.

## Setup (Development)

**Automated (Windows):** from the repo root run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

That creates `.venv`, installs **`pip install -e ".[all]"`** (Discord bot + **eeg**: MNE, Plotly, mne-connectivity, etc.), copies `.env` from `.env.example` if missing, creates `data\` folders (including `data\eeg_workspace\output`), runs `npm install` in `web/`, and adds `web/.env.local` with `NEXT_PUBLIC_PARADOX_API`.

**Manual equivalent:**

```powershell
cd "<repo-root>"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[all]"
copy .env.example .env
```

Edit `.env` â€” set `CHAT_MODEL` / `EMBED_MODEL` to what you pulled. Optionally set `SEARXNG_URL`, `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` (web search), `SKYE_URL`, Discord IDs.

## Launcher (Windows â€” API + UI)

Double-click **`launch.bat`**, **`Launch Paradox.bat`**, or **`Launch HEX.bat`** (same script), or run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\launch.ps1
```

Optional: **`-Reinstall`** (re-run `pip install -e ".[all]"` and `npm install` in `web/`), **`-NoBrowser`**, **`-SkipOllama`** (starts API + web without installing or starting Ollama).

That opens two windows (FastAPI on **8765**, Next.js on **3000**) and your browser to the UI.

If a `.bat` window looks â€œstuckâ€ at the PowerShell banner, ensure you are using the repoâ€™s launchers (they use `cd "%~dp0."` so paths with spaces like `EEG Paradox Solutions LLM` work under `cmd`).

**API only:** **`launch-api-only.bat`** runs `run_server.py` in one console (no Ollama check, no Next.js).

## Run API

```powershell
cd "<repo-root>"
.\.venv\Scripts\python.exe .\run_server.py
```

Or double-click **`launch-api-only.bat`**. Or: `uvicorn hexnode.api.main:app --host 0.0.0.0 --port 8765`

## Run UI

```powershell
cd web
npm install
npm run dev
```

Open `http://localhost:3000`.

## REST API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Status, Ollama connectivity, optimization info |
| POST | `/agent` | Main agent â€” send message, receive answer |
| POST | `/memory/query` | Semantic search across memory collections |
| GET | `/system/stats` | CPU, RAM, disk, GPU metrics |
| GET | `/focus` | Current reflection focus document |
| GET | `/tools` | List registered tools and parameters |
| POST | `/ingest/path` | Ingest a file by filesystem path |
| POST | `/files/upload` | Upload files (EEG, documents, general) |
| GET | `/files?category=all` | List uploaded files |
| DELETE | `/files/{category}/{filename}` | Delete an uploaded file |

## Data Layout

Under `data/` (created at runtime):

- `chroma/` â€” vector store
- `vault/reflections/` â€” reflection markdown
- `vault/current_focus.md` â€” injected into the agent system prompt
- `ingest_queue/` â€” drop `.pdf`, `.md`, `.txt`, `.csv`, `.json`, `.yaml`, `.docx`; the watcher ingests periodically
- `eeg_workspace/` â€” EEG files (`.edf`, `.bdf`, `.fif`, `.set`, `.vhdr`)

## Licensing

This repository build does **not** ship product licensing: no `/license/*` API routes, no activation UI, and no runtime feature gating by license tier. Tools and EEG flows are available without a key.

## File Upload

The web UI includes a file management panel for uploading:

- **EEG files** (`.edf`, `.bdf`, `.set`, `.fif`, `.vhdr`, `.cnt`) â€” routed to `eeg_workspace/`
- **Documents** (`.pdf`, `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.docx`) â€” routed to `ingest_queue/`, auto-ingested into memory
- **General files** â€” stored in `vault/uploads/`

Drag-and-drop or click to upload. Files are listed with category filtering and delete support.

## Reflection (Nightly)

Schedule `python scripts\reflect.py` with Windows Task Scheduler (e.g. 03:30 daily), with the venv activated.

## Discord (Optional)

1. `pip install discord.py` (included in `[discord]` extra).
2. Set `DISCORD_TOKEN`, `DISCORD_CHANNEL_ID` in `.env`.
3. Run `python scripts\discord_bot.py`.

## EEG Research Mode

Paradox includes a full EEG research stack for QEEG, ERP, spectral, connectivity, microstates, and **interactive clinical / NetOps-style dashboards** (traceroute explorer, multi-tab clinician summary, latency SLA, packet-loss views, patternâ€“condition evidence, vigilance, TBI/PD-oriented reports, and related HTML panels when the NetOps bundle runs).

**Development / source runs:** install EEG dependencies so the same interpreter can run pipelines and tools:

```powershell
pip install -e ".[eeg]"
```

This adds MNE-Python, pyedflib, NumPy, SciPy, matplotlib, pandas, statsmodels, and related libraries. **Desktop installers** bundle a separate **`paradox-eeg-worker.exe`** for visualization and NetOps subprocesses; you still use `[eeg]` when hacking from a venv or when overriding `PARADOX_EEG_PYTHON` to a full Python.

**Supported EEG software / formats:**

| Software | Format | Notes |
|----------|--------|-------|
| NeuroGuide | EDF | QEEG, z-scores, sLORETA |
| BrainMaster | EDF/BDF | Discovery, Atlantis, BrainAvatar |
| BioExplorer | EDF, CSV | Visual NFB design |
| BioEra | EDF | Custom biofeedback protocols |
| Cygnet | EDF | Z-score NFB with NeuroGuide norms |
| OpenBCI | CSV, BDF | Cyton, Ganglion, via BrainFlow |
| EEGLAB | .set/.fdt | MATLAB ecosystem |
| Brain Products | .vhdr | actiCHamp, BrainVision |
| Elekta/MEGIN | .fif | MEG + EEG |

**Workflows:**

1. **Web UI â€” EEG Data panel** â€” Upload a recording; the API runs a **background job** (24-step-style pipeline generation + clinical scripts + `run_visualizations.py`). Open HTML/PNG results in the browser or from `data/eeg_workspace/output/<job_id>/`. See **`doc/user/09-eeg-research.md`**.
2. **Chat / agent** â€” Ask Paradox to analyze files: `run_eeg_pipeline` runs the full automated script; `run_python_analysis` runs custom MNE code with retries. Outputs go to the EEG workspace output tree.
3. **Manual drop-in** â€” Place files under `data/eeg_workspace/` and reference them from scripts or the agent.

**Operator docs:** `doc/user/09-eeg-research.md` (jobs, REST routes, artifact types). **Technical deep dive:** open `doc/technical-reference.html` in a browser (24-step pipeline math + interactive outputs section).

**Reference docs:** `data/eeg_reference/` contains `eeg_fundamentals.md` and `eeg_software_guide.md`.

## Tools (16+)

Includes: `query_memory`, `web_search`, `fetch_url`, `get_system_stats`, `get_realtime_stats`, `get_datetime`, `ingest_document`, `run_shell_command` (allowlisted), `run_python_analysis` (auto-retry), `run_eeg_pipeline` (24-step automated), `boost_memory`, `run_reflection`, `skye_infer`, `send_discord_message`, `lora_send` (stub), `deep_research` (multi-source with caching).

## Architecture Stack

| Layer | Technology | Responsibility |
|-------|-----------|----------------|
| Desktop | Tauri v2 (Rust) | Native window, system tray, sidecar management, installer |
| Frontend | Next.js, React, Tailwind | Chat UI, file upload, system monitoring |
| API | FastAPI, Pydantic | HTTP endpoints, CORS, file management |
| Agent | Python (ReAct v2) | Think / Act / Observe / Answer loop |
| Symbolic | YAML + regex | Deterministic tool routing hints |
| LLM | Ollama (Qwen3:8B, phi4-mini) | Reasoning, generation, classification |
| Memory | ChromaDB + nomic-embed-text | Persistent vector storage with weighted scoring |
| Optimization | Flash Attention, KV quant, embed quant | VRAM efficiency, inference speed |
| Tools | Python modules | Web search, EEG analysis, research, system info |

## License

Paradox Solutions LLM is **free software** under the **GNU General Public License v3.0 or later**. See the [`LICENSE`](LICENSE) file in the repository root for the full license text. SPDX: `GPL-3.0-or-later`.

To (re)apply the standard per-file copyright + GPL notice to Python, TypeScript, Rust, and PowerShell sources after adding new files, run: `python scripts/apply_gpl_headers.py` from the repo root (use `python scripts/apply_gpl_headers.py --dedupe` if a merge ever duplicated a header block).