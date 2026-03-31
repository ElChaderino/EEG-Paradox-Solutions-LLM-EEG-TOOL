# Changelog

All notable changes to Paradox Solutions LLM are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [0.3.2] - 2026-03-29

### Removed

- **Product licensing runtime:** no `/license/*` routes, no activation/vendor admin UI, no tool or EEG gating by license tier. Optional vendor scripts may remain in the tree but are not wired into the shipped API.

### Fixed (EEG / frozen worker — interactive HTML generation)

- **`orjson` + Plotly `to_html()`:** Plotly 6.x calls `orjson.OPT_NON_STR_KEYS` when serializing figures for HTML export. The API bundle exposed `orjson` as a directory with only a `.pyd` and no proper package layout; when the EEG worker prepended that path, Python imported an empty namespace and every `fig.to_html()` failed with `AttributeError`. **Fix:** bundle a full **`orjson`** copy inside **`paradox-eeg-worker`** via `collect_all("orjson")` in `paradox-eeg-worker.spec` (plus explicit `hiddenimports`). Restores interactive traceroute, Granger HTML, 3D scalp Plotly, LORETA HTML, Coben-style overlays, microstate HTML, and other Plotly-based dashboards in the installed app.
- **Trace viewer on Windows:** `trace_viewer_generator.py` used emoji in `print()`; the frozen worker console defaulted to **cp1252**, causing **`UnicodeEncodeError`** before HTML was written. **Fix:** `eeg_subprocess_launcher.py` now sets **`PYTHONIOENCODING=utf-8`** and reconfigures stdout/stderr when possible before running any script.
- **Microstate outputs empty:** `_compute_microstates()` in `run_visualizations.py` returned **`channel_names`** and **`maps`** as a dict of per-state objects; `microstate_visualizer` expects **`ch_names`** and **`maps`** as a **list of vectors**, plus **`labels_downsampled`** / **`gfp_downsampled`** for the interactive explorer. **Fix:** align the returned structure (including transition matrix and per-state stats for the UI).

### Added (packaging)

- **`paradox-eeg-worker.spec`:** collect hooks for **`nibabel`** and **`nilearn`** (explicit hidden imports for LORETA/Coben anatomical paths). Note: PyInstaller may still omit full nibabel/nilearn trees on some builds; LORETA continues to fall back to sphere / voxel viewers when surface readers are unavailable.

### Documentation

- User and developer docs updated for v0.3.2: root cause summary (not license gating), symptoms, and fixes for “missing interactive HTML” on the desktop build. See `doc/user/07-troubleshooting.md`, `doc/user/09-eeg-research.md`, `doc/developer/03-architecture.md`, `doc/README.md`.

## [0.3.1] - 2026-03-29

### Added
- **Bundled EEG worker** (`paradox-eeg-worker.exe`): MNE, plotly, scipy, matplotlib, scikit-learn, networkx, statsmodels are now shipped inside the installer. The packaged app no longer requires a system Python with science packages.
- `paradox-eeg-worker.spec` PyInstaller spec for the dedicated science worker.
- `eeg_subprocess_launcher.py` entry point with `--eeg-probe` self-test and `PYTHONPATH` injection for frozen environments.
- `build_backend.ps1` now builds both API and worker, copies worker into `dist/paradox-api/eeg-worker/`, and validates the full bundle before continuing.
- `/health` endpoint reports `bundled_worker: true/false` so you can confirm the worker is in use.
- `GET /eeg/jobs` now returns `condition` and `output_mode` fields (frontend badges).
- Upfront dependency check in viz orchestrator: warns clearly if mne/scipy/matplotlib/plotly are missing.
- Version tracking: `VERSION` file (single source of truth), `CHANGELOG.md`, `scripts/bump_version.ps1`.
- **5 missing NetOps analysis modules** now wired into the pipeline: Service Health, QoS, Health Check, SIEM, VLAN Segmentation.
- **Coben-style Granger brain overlays** (3D brain, slices, time-resolved, spectral matrix) now generated when Granger results are available.
- **LORETA source localization** visualizations now generated when raw MNE data is available.
- **Mahalanobis distance 3D** phenotype visualization now generated when z-score metrics exist.
- **Trace Viewer** (EDF browser-style scrollable trace) now generated when raw data is available.

### Fixed
- **Frozen worker PYTHONPATH**: PyInstaller exes don't process `PYTHONPATH` env var at startup. Added `_inject_pythonpath()` so the worker can resolve `hexnode.eeg.*` imports from the API's `_internal` directory. This was the root cause of all NetOps/traceroute/decoder outputs being missing in the installed app.
- **Spectrum paths not in manifest**: `generate_power_spectra()` returns a `Path`, but the orchestrator only checked `isinstance(result, dict)`. PSD files were written but invisible to job status. Added `elif result:` branch.
- **Band range inconsistency**: beta, hibeta, gamma ranges differed across `band_definitions.py`, `spectrum_generator.py`, and the orchestrator. Unified to `beta=(13,30)`, `hibeta=(20,30)`, `gamma=(30,40)` everywhere (4 files + netops copies).
- **PYTHONPATH missing from 2 subprocess launchers**: `_run_eeg_job` and `_run_clinical_script` now pass `eeg_subprocess_pythonpath()` like the viz subprocess does.
- **Clinical script timeout too tight**: was 120s (worker startup alone takes ~17s). Now `max(180, python_analysis_timeout)`.
- **MNE probe timeout**: was 25s, borderline on slow systems. Increased to 60s.
- **Silent `except: pass`** in pipeline-generated script (ICA component plot, ERP topomap) and viz orchestrator (3D scalp bands, abs/rel sheets). Now logs the exception.
- **`encodeURIComponent` double-encoding `/`** in frontend file URLs for `{filename:path}` routes.
- **Dead `_eeg_jobs_cache`** in `EegDataPanel.tsx` removed.
- **`build_backend.ps1` Unicode em-dashes** caused PowerShell parse errors.
- **`build_backend.ps1` PermissionError** on `dist\paradox-api`: now renames the old folder before PyInstaller runs, and fails loudly instead of silently continuing with a broken bundle.
- **3 renderer function name mismatches**: pipeline called `generate_service_health_html`, `generate_qos_html`, `generate_health_check_html` but renderers defined `render_*` names. Added `generate_*` aliases and `epoch` parameter to fix silent `getattr` failures.
- **Granger viz `except: pass`** replaced with `logger.warning` so failures are visible.
- **Renderer loop logging** upgraded from `debug` to `warning` so skipped tabs are visible in logs.
- **Propagation map `except: pass`** replaced with `logger.warning`.
- **`POST /agent`**: `httpx.ReadTimeout` from Ollama is caught and returned as **504** with a user-facing message instead of an unhandled 500.
- **`paradox-api.spec`**: removed invalid hidden import `beautifulsoup4` (pip package name); use `bs4` only — eliminates PyInstaller ERROR during Analysis.

### Changed
- `build_release.ps1` step 2 delegates to `build_backend.ps1` (single script for both exe builds).
- `python_for_eeg()` prefers bundled `eeg-worker/paradox-eeg-worker.exe` when frozen, falls back to system Python.
- Pipeline now stores MNE Raw object in results (`_raw_mne`) for use by LORETA, Coben, and Trace Viewer visualizations.
- `requirements.txt` now includes `statsmodels>=0.14.0` (needed by NetOps Granger analysis; was missing from venv).

### Documentation
- Refreshed `doc/` (user, developer, reference, appendix), root `README.md`, and `addons/eeg-norms-dlc/README.md` for v0.3.1: bundled EEG worker, `VERSION`/`CHANGELOG`/`bump_version.ps1`, `GET /health` fields, `PARADOX_EEG_PYTHON`, agent 504, release build via `build_release.ps1` / `build_backend.ps1`.

## [0.3.0] - 2026-03-22

### Added
- Desktop application (Tauri v2 + PyInstaller): native MSI/NSIS installers, first-run setup wizard, system tray.
- GPU optimizations: flash attention, KV cache quantization (q8_0/q4_0), embedding quantization.
- Product licensing: RSA-signed keys, machine binding, feature flags, tiers, plus HTTP routes under `/license/*` *(removed in 0.3.2 — see **Removed** in the 0.3.2 section above)*.
- File management: drag-and-drop upload, auto-routing, auto-ingestion.
- EEG research stack: 24-step MNE pipeline, clinical scripts (Swingle Q, band power), visualization + NetOps pass (topomaps, 3D scalp, microstates, interactive traceroute, linked dashboards).
- EEG norms add-on (DLC): Cuban 2nd Wave normative database, z-score enrichment.
- Background EEG jobs with progress polling and per-job output isolation.
- API endpoints: `/files/upload`, `/eeg/process`, `/eeg/jobs`, `/eeg/jobs/{id}/files/{path}`, `/workspace/open` *(and `/license/*` through 0.3.1; licensing routes removed in 0.3.2)*.

## [0.2.0] - 2026-02-15

### Added
- Memory store with ChromaDB, vault, reflection intelligence.
- Agent loop with ReAct reasoning, tool registry, confidence scoring.
- Web search (SearXNG + DuckDuckGo fallback), document ingestion.
- Neuro-symbolic YAML rules engine.
- Ollama integration with auto-start, model management.
- Discord bot integration.

## [0.1.0] - 2026-01-20

### Added
- Initial release: FastAPI backend, Next.js frontend, Ollama chat.
- Basic memory and embedding pipeline.
