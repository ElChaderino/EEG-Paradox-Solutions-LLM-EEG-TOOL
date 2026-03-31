# Appendix — Layer Matrix (Complete Stack)

## Objective

Enumerate **every operational layer** from physical hardware through operator perception. Use this matrix for impact analysis when changing one component.

| Layer | Constituents | Primary interfaces | Failure signature |
|-------|----------------|-------------------|-------------------|
| L0 Physical | CPU, RAM, GPU, NVMe, NIC, power | Hardware | Thermal throttle, disk SMART errors |
| L1 Firmware / driver | UEFI, NVIDIA driver, storage driver | OS APIs | `nvidia-smi` failure, GPU reset |
| L2 Operating system | Windows kernel, filesystem, firewall | Win32, PowerShell | Permission denied, port bind failure |
| L3 User session | PATH, env vars, working directory | Shell | Wrong cwd, missing venv activation |
| L4 Language runtime | Python interpreter, stdlib | `python` | ImportError, version mismatch |
| L5 Process virtualenv | pip packages, editable install | `pip` | Dependency conflict |
| L6 Inference daemon | Ollama binary, loaded models | `11434/tcp` | Model not found, OOM on load |
| L7 Application package | `hexnode` modules | `import hexnode` | Syntax error, misconfiguration |
| L8 Persistence files | `data/chroma`, `data/vault`, queue | File I/O | Locking, corruption |
| L9 Vector engine | Chroma embedded client | Python API | Query errors, metadata type rejection |
| L10 HTTP server | Uvicorn, FastAPI middleware | `PORT` | 503, CORS rejection |
| L11 Background tasks | Ingest watcher (asyncio); EEG job thread (`POST /eeg/process`) spawning sync subprocesses for pipeline scripts and `run_visualizations.py` | Internal: **`paradox-eeg-worker.exe`** when bundled (v0.3.2+ bundles **`orjson`** for Plotly `to_html`; launcher sets UTF-8 I/O), else venv/`py`/`PARADOX_EEG_PYTHON` | Stalled ingest; EEG job `error` in `_job.json`; `ModuleNotFoundError` for MNE if worker missing or PYTHONPATH wrong; missing Plotly HTML if worker lacks working `orjson` |
| L12 Agent controller | `run_agent`, step loop | Function | Infinite loop prevented by max steps |
| L13 Tool plane | Registry, Tool classes (`run_eeg_pipeline`, `run_python_analysis`, `get_eeg_results`, …) | `ToolContext` | Tool not found, param mismatch; license feature denied |
| L14 External HTTP tools | SearXNG, Skye, Discord API | `httpx` | Timeout, 4xx/5xx |
| L15 Presentation (web) | Next.js, browser; **EEG Data** panel (`EegDataPanel`) calling `/eeg/*` | `3000/tcp`, `8765/tcp` API | Blank UI, fetch errors; job poll stuck if API down |
| L16 Human operator | Procedures in `doc/user/` | Cognition | Misconfiguration |

## Dependency direction (allowed)

Information and control flow **shall** move downward from L16→L15→L10→L12→L6 except where tools explicitly call outward (L14).

**Shall not:** Allow tools to import UI or FastAPI route modules.

## EEG / NetOps adjunct (conceptual)

Not a separate numbered layer: the **visualization subprocess** (L11 child) loads **`hexnode.eeg.viz`** and optionally **`hexnode.eeg.netops_standalone`** — Granger connectivity, traceroute, HTML emitters, clinician summary. Failures here **shall** surface as missing dashboard files or warnings in job `messages`, without necessarily crashing the FastAPI process.

| Concern | Touched layers | Typical failure |
|---------|----------------|-----------------|
| Frozen API + EEG worker | L7, L10 | `paradox-api.exe` stays lean; `paradox-eeg-worker.exe` bundles MNE/Plotly/scipy/etc. for viz subprocesses. Override with `PARADOX_EEG_PYTHON` / dev venv `python` when debugging from source. |
| Job artifacts | L8 | `data/eeg_workspace/output/<job_id>/` growth, AV locks |
| Interactive HTML | L15 | CDN Plotly, iframe preview via `/eeg/jobs/.../files/` |

Operator detail: `user/09-eeg-research.md` and `user/07-troubleshooting.md` §8.

## Related

- `00-overview.md` — narrative stack summary.
- `developer/03-architecture.md` — process diagram.
- `user/09-eeg-research.md` — EEG jobs and outputs.
