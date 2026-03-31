# Glossary

Terms are defined as used in this codebase. Capitalized proper nouns (Ollama, ChromaDB, FastAPI, Tauri) refer to external products.

| Term | Definition |
|------|------------|
| **Agent loop** | The iterative procedure that calls the chat model, parses a JSON decision object, optionally invokes a tool, appends observations, and repeats until stop conditions or step limit. |
| **Paradox** | The name of this local node implementation (Python package `hexnode`). |
| **Chroma collection** | A named partition inside the Chroma persistent store (`chat_history`, `documents`, `library`). |
| **Confidence** | A scalar in \([0, 1]\) emitted by the model in its JSON response; compared to `confidence_threshold` for satisfaction and Skye escalation logic. |
| **Embedding** | A dense vector produced by `embed_model` for a text string, used for similarity search in Chroma. |
| **Embedding quantization** | TurboQuant-inspired compression of embeddings: random rotation to spread information uniformly, followed by scalar quantization (default int8). Reduces storage with minimal search quality loss. |
| **Feature flag** | Historical label for tool groups; **not** enforced at runtime in this build (no license gating). |
| **Flash attention** | GPU-optimized attention algorithm (`OLLAMA_FLASH_ATTENTION=1`) that reduces VRAM usage for long context windows. |
| **Ingest queue** | Directory `data/ingest_queue` polled by the background watcher; accepted suffixes include `.pdf`, `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.docx`, `.edf`, `.bdf`. |
| **KV cache** | Key-value cache storing attention states during LLM inference. Quantization (`q8_0` or `q4_0`) reduces VRAM usage by 50-75%. |
| **License key** | Not used in this build. (Legacy designs used RSA-signed JSON verified with an embedded public key.) |
| **License Manager GUI** | Optional vendor tooling (`tools/license_manager_gui.py`) if present in the tree; **not** wired into the shipped API/UI in this build. |
| **Machine ID** | SHA-256-style host fingerprint; not used for product activation in this build. |
| **Ollama base URL** | HTTP origin for Ollama APIs (`/api/generate`, `/api/chat`, `/api/embeddings`, `/api/tags`). |
| **PyInstaller** | Bundles the Python FastAPI backend into `dist/paradox-api/` and, separately, the **EEG worker** into `dist/paradox-eeg-worker/` (then merged under `dist/paradox-api/eeg-worker/` for Tauri). |
| **Reflection** | A batch job that samples memory collections, asks the chat model for structured JSON insights, writes markdown under `vault/reflections/`, updates `current_focus.md`, and stores a summary in `documents`. |
| **Rotation matrix** | Deterministic random orthogonal matrix (via QR decomposition with seed 42) used in embedding quantization to spread information uniformly before scalar quantization. Data-oblivious: works on any input without calibration. |
| **Sidecar** | The PyInstaller-bundled backend executable (`paradox-api.exe`) managed by the Tauri desktop shell as a child process. |
| **EEG worker** | `paradox-eeg-worker.exe`: second frozen binary with scientific dependencies; runs `run_visualizations.py` and similar scripts with `PYTHONPATH` pointing at the API bundle’s `hexnode` tree. |
| **Skye** | Optional remote Ollama instance used for a second-pass generate when local confidence is below threshold and `SKYE_URL` is set. Not a separate product binary in this repo. |
| **Tauri** | Rust-based desktop application framework (v2) that wraps the static Next.js frontend and manages the backend sidecar. Produces MSI and NSIS installers. |
| **Tier** | Legacy license tier names; **not** enforced in this build. |
| **Tool** | Python class subclassing `Tool` with `name`, `description`, and async `run(ctx, **params)`. |
| **ToolContext** | Object carrying `memory`, `ollama`, `settings`, and `trace_id` for one agent run. |
| **TurboQuant** | Google Research algorithm for data-oblivious vector quantization. The embedding quantization module (`embed_quantize.py`) implements a simplified version of this approach. |
| **Vault** | Directory tree under `data/vault` for operator-readable files (reflections, current focus, uploads). |
| **Watcher** | Async task started at API lifespan: scans ingest queue on an interval and processes new files. |
| **EEG job** | Background thread started by `POST /eeg/process`: writes uploaded file under `eeg_workspace/`, runs generated pipeline + clinical scripts + `run_visualizations.py` into `eeg_workspace/output/<job_id>/`. |
| **NetOps (EEG)** | Network-analogy dashboards (traceroute, SLA, packet loss, path diversity, etc.) built on Granger connectivity and synthetic “routing” over standard 10–20 graphs; implemented in `hexnode/eeg/netops_standalone`. |
| **Clinician summary** | Standalone multi-tab HTML (`clinician_summary_session.html`) linking methodology-specific interpretations (e.g. Gunkelman, Swingle) to pipeline metrics and pattern–condition output. |
| **Vigilance (EEG)** | Windowed spectral stage classification (VIGALL-inspired) plus optional slow-wave proxy; populates `results["vigilance"]` for reports and artifact guards. |
| **Pattern–condition** | `hexnode.eeg.netops_standalone.cracker.pattern_condition`: maps quantitative markers to narrative patterns and conditions with registry-driven rules. |
| **Traceroute interactive** | Primary HTML explorer embedding 3D packet/routing visualization and a dropdown of linked NetOps/clinical dashboard iframes. |
