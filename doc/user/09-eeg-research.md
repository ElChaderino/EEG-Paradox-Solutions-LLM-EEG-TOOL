# User Manual 09 — EEG Research & Clinical Visualizations

## Objective

Describe how Paradox handles EEG recordings end-to-end: upload paths, automated jobs, generated artifacts, and how the results relate to the agent tools. This document **shall** be read after [User 04 — Web console](04-web-console.md) if you use the EEG Data panel.

## What you get

Paradox combines three lanes:

1. **Agent-driven analysis** — The model can call `run_eeg_pipeline` (24-step MNE preprocessing and spectral/connectivity pipeline) and `run_python_analysis` (custom MNE scripts with automatic retry on common errors). Outputs land under the EEG workspace.
2. **One-click processing jobs** — The **EEG Data** panel uploads a file and runs a background job: generated pipeline script, Clinical Q (Swingle-style) script, band-power script, then the **visualization orchestrator** (`hexnode/eeg/viz/run_visualizations.py`) in a subprocess. That step produces HTML dashboards, PNG topomaps, 3D scalp views, microstate reports, and the **NetOps / traceroute** bundle when the standalone pipeline is available.
3. **Read-only browsing** — List prior global outputs (`GET /eeg/outputs`) or open artifacts from a specific job (`GET /eeg/jobs/{id}/files/...`).

## Web UI: EEG Data panel

The Next.js **EEG Data** panel (`web/src/components/EegDataPanel.tsx`) **shall**:

- Upload supported clinical/research formats (same extension set as the API: `.edf`, `.bdf`, `.set`, `.fif`, `.vhdr`, `.cnt`, etc.).
- Optionally set **condition** (e.g. EC/EO), **output mode**, and **remontage** hints passed through to the generated pipeline configuration.
- Poll **job status** until completion; show progress messages and a file list.
- Open HTML outputs in-app (iframe) or download files; link to open the job output folder on disk (`POST /workspace/open` opens Explorer/Finder on the output directory).

Operators **shall** keep the API running while jobs execute; jobs are threaded and persist state under `data/eeg_workspace/output/<job_id>/`.

## REST endpoints (summary)

| Method | Path | Role |
|--------|------|------|
| `POST` | `/eeg/process` | Multipart upload + start background job. Form fields: `condition`, `output_mode`, `remontage_ref`. Returns `job_id`. |
| `GET` | `/eeg/jobs` | List jobs (`id`, `filename`, `status`, `progress`, `condition`, `output_mode`, `started`, `output_count`, `error`, etc.). |
| `GET` | `/eeg/jobs/{job_id}` | Job detail: messages, `output_files`, optional `metrics` JSON. |
| `GET` | `/eeg/jobs/{job_id}/files/{filename}` | Serve a single artifact (HTML served with iframe-friendly headers). |
| `POST` | `/eeg/jobs/{job_id}/delete` | Remove job directory. |
| `GET` | `/eeg/outputs` | List files in the shared global output folder (legacy / non-job outputs). |
| `GET` | `/eeg/outputs/{filename}` | Download one file from global output. |
| `POST` | `/workspace/open` | Open EEG workspace output folder in the OS file manager. |

Full field-level detail: [Reference — REST API](../reference/rest-api.md).

## Generated artifacts (typical job)

Exact filenames depend on recording stem and condition; a complete run may include:

- **Preprocessing:** cleaned `.fif`, epochs, quality / metrics JSON, band-power tables.
- **Topography:** per-band PNG/HTML topomaps, topo sheets (absolute/relative power).
- **3D scalp:** interactive HTML surfaces per band.
- **Microstates:** segmentation maps, statistics, transition views (`hexnode/eeg/viz/microstate_visualizer.py`).
- **Traceroute + NetOps:** interactive 3D traceroute explorer with a **dashboard dropdown** linking standalone HTML reports: clinician summary (multi-methodology tabs), latency SLA, packet-loss heatmaps, microstate–propagation coupling, pattern–condition evidence, PEM, topology/path analytics, TBI/PD summaries, vigilance timeline, runbooks, and other NetOps-themed panels produced by `hexnode/eeg/netops_standalone` when the bundle runs successfully.

If the full NetOps pipeline cannot run (missing bundle or environment), a **synthetic traceroute** fallback may still render from band-power–derived graphs.

## Clinical and interpretive layers

- **Clinician summary** (`clinician_summary_session.html`) — Multi-tab dashboard (Easy View, Advanced, Expert, Gunkelman, Swingle, Fisher, Thatcher, Lubar, Peniston, Sterman, Hammond, Budzynski, Fehmi). Band power and session-relative z-scores come from pipeline metrics; EO/EC-nested `metrics_by_site` is flattened for display. **Vigilance** (dominant stage / index) is derived from a windowed classifier when possible, with slow-wave–based fallback so the summary is populated across more recordings.
- **Pattern–condition engine** — Maps markers (band power, asymmetry, connectivity, vigilance, etc.) to condition-style narratives and guard rails for artifact/drowsiness.
- **Screening modules** — TBI- and PD-oriented assessments are computed in the NetOps pipeline path when metrics and adapters are available; outputs surface in dedicated HTML where configured.

**Disclaimer (shall be understood by operators):** All clinical-style text is **decision support and education**, not a diagnosis. Professional interpretation remains required.

## Which Python runs visualizations (dev vs installed app)

The visualization orchestrator (`hexnode/eeg/viz/run_visualizations.py`) always runs in a **separate process** from the FastAPI app (`hexnode/api/main.py`).

- **Installed desktop build:** The API prefers **`paradox-eeg-worker.exe`** next to the API bundle (`dist/paradox-api/eeg-worker/`), a PyInstaller build that includes MNE, SciPy, Matplotlib, Plotly, scikit-learn, networkx, statsmodels, etc. The worker receives **`PYTHONPATH`** pointing at the API’s `_internal` tree so `import hexnode` resolves the same source the API uses.
- **Override:** Set **`PARADOX_EEG_PYTHON`** or **`EEG_PYTHON`** to a full `python.exe` path (or another worker) if you want a custom environment.
- **Development (`run_server.py` + venv):** The resolver typically uses the active venv’s **`python`**; that interpreter **shall** have **`pip install -e ".[eeg]"`** (or equivalent) for full pipeline and NetOps output.

**Health check:** `GET /health` → `eeg_subprocess` reports the chosen executable, `bundled_worker: true/false`, and whether `run_visualizations.py` was found in the bundle.

### License vs “missing” interactive HTML (v0.3.2 note)

If you have **`eeg`** (and typical add-ons like **`eeg_visualization`**, **`traceroute_core`**, **`netops_*`**) on your key, the API **still** only gates **`POST /eeg/process`** on the **`eeg`** feature. The NetOps / traceroute **pipeline does not** call separate license checks per HTML file.

When **most** tab-style NetOps HTML appears but **Plotly-heavy** outputs vanish (interactive traceroute, 3D scalp, Granger connectivity HTML, LORETA, Coben overlays, microstate interactive, trace viewer), the historical cause on Windows installers was **runtime packaging** inside **`paradox-eeg-worker.exe`** (broken **`orjson`** import for Plotly **`to_html()`**, and **cp1252** crashes on emoji **`print()`** in trace viewer), plus a **data-shape mismatch** for microstates—not revocation of your key. **Fix:** use application **v0.3.2+** built from `scripts/build_release.ps1` after `CHANGELOG` 0.3.2 changes, then run a **new** job. See [User 07 — Troubleshooting](07-troubleshooting.md) §8.

### Worker bundle contents (operator-relevant)

Besides MNE / SciPy / Matplotlib / Plotly / scikit-learn / networkx / statsmodels, the worker build **shall** include a working **`orjson`** binary package so Plotly can serialize figures to HTML. Optional **nibabel** / **nilearn** improve LORETA and anatomical overlays when successfully frozen; otherwise the pipeline uses documented fallbacks (e.g. sphere source space, lower-resolution viewers).

## Related documents

- [User 04 — Web console](04-web-console.md) — layout and chat.  
- [Reference — REST API](../reference/rest-api.md) — EEG routes in full.  
- [technical-reference.html](../technical-reference.html) — 24-step pipeline math and interactive EEG deep dive.  
- Repository [README.md](../../README.md) — EEG Research Mode quick start and format table.  
- `data/eeg_reference/` — `eeg_fundamentals.md`, `eeg_software_guide.md`.

Next: return to [User 07 — Troubleshooting](07-troubleshooting.md) if jobs fail or outputs are missing.
