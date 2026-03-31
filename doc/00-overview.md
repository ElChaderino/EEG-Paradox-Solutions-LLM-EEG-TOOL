# 00 — System Overview

## Purpose

Paradox Solutions LLM (this repository) is a **local AI node**: a single deployable unit that runs a language model through **Ollama**, stores retrievable state in **ChromaDB**, and executes a **bounded multi-step agent loop** with **modular tools**. The design constraint is explicit: **no third-party cloud LLM APIs** for core inference. Optional components (SearXNG, remote Ollama "Skye," Discord) are network-adjacent services under operator control, not mandatory cloud dependencies.

The system ships as a **native desktop application** (Tauri v2 + PyInstaller) with automatic first-run setup, or can be run from source for development.

## Architectural layers (bottom to top)

1. **Host layer** — Physical machine or VM (this document targets Windows 10/11); GPU drivers; file system; optional Docker for auxiliary services.
2. **Inference layer** — Ollama process exposing HTTP on `OLLAMA_BASE` (default `http://127.0.0.1:11434`). Holds chat and embedding models. Configured with flash attention and KV cache quantization for VRAM efficiency.
3. **Optimization layer** — Flash attention (`OLLAMA_FLASH_ATTENTION=1`), KV cache quantization (`OLLAMA_KV_CACHE_TYPE=q8_0`), and TurboQuant-inspired embedding quantization (rotation + scalar quantize) for storage compression.
4. **Runtime layer** — Python 3.11+ interpreter; application package `hexnode`; optional virtual environment isolation. When frozen via PyInstaller, the **API** runs as `paradox-api.exe`; heavy EEG visualization **may** run in a second frozen executable, `paradox-eeg-worker.exe`, spawned with `PYTHONPATH` set to the API bundle so both share the same `hexnode` sources.
5. **Persistence layer** — Chroma persistent directory (quantized embeddings via `embed_quantize.py`); vault directory for human-readable artifacts (`reflections/`, `current_focus.md`); ingest queue directory.
6. **Orchestration layer** — FastAPI application (`hexnode.api.main`): lifespan hooks, background ingest watcher, route handlers, file upload/management endpoints.
7. **Agent layer** — `run_agent`: iterative LLM calls with JSON-structured decisions, tool dispatch, optional Skye escalation.
8. **Tool layer** — Registered callables with declared names; each tool receives a `ToolContext` (memory, ollama client, settings). This build does not gate tools by product license.
9. **Presentation layer** — Next.js web UI (`web/`) calling the REST API; file upload panel; GPU optimization status display; optional Discord script bridging channel messages to `/agent`.
10. **Desktop layer** — Tauri v2 (Rust) wrapping the static Next.js export and managing the PyInstaller backend as a sidecar process. Handles first-run bootstrapping (Ollama download, model pulling, GPU optimization setup), system tray, and installer generation (MSI, NSIS).

## Data flow (simplified)

```
User message (UI / HTTP / Discord)
    → POST /agent
    → Agent loop (≤ N steps)
    → Ollama (chat, JSON mode, flash attention + quantized KV cache)
    → Tools (optional each step)
    → Final answer (and optional Skye pass)
    → Persist turn in chat_history (Chroma, quantized embeddings)
```

## File management flow

```
User uploads file (drag-and-drop or file picker)
    → POST /files/upload
    → Route by extension: EEG → eeg_workspace/, documents → ingest_queue/, other → vault/uploads/
    → EEG/document files auto-ingested into memory
    → Optional: POST /eeg/process runs a background job (pipeline + viz + NetOps HTML) into eeg_workspace/output/<job_id>/
    → GET /files lists all managed files
    → DELETE /files/{category}/{filename} removes files
```

## Desktop application flow

```
User launches Paradox Solutions LLM.exe
    → Tauri window opens → /setup page
    → check_ollama → download_ollama (if missing) → ensure_ollama_serving (with FA + KV quant env vars)
    → get_ollama_models → pull_model (any missing: qwen3:8b, nomic-embed-text)
    → start_api_sidecar (spawns paradox-api.exe from bundled resources; EEG jobs use paradox-eeg-worker.exe from eeg-worker/ when present)
    → Health check passes → redirect to main UI
    → Close button minimizes to system tray
    → "Quit Paradox" from tray menu kills sidecar and exits
```

## Invariants

- The agent loop **shall** terminate after at most `agent_max_steps` iterations unless implementation is changed.
- Tool execution **shall** be mediated by the registry; ad-hoc subprocess calls from the model are **not** permitted except inside explicitly allowlisted tools.
- Embeddings for stored vectors **shall** use the configured `embed_model` consistently; mixing embedding models without re-indexing **shall** be treated as a data migration problem.
- Embedding quantization **shall** use a deterministic rotation matrix (seeded RNG) so that quantize operations are consistent across restarts without storing calibration data.
- The desktop application **shall** set `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0` when spawning Ollama to ensure GPU optimizations are active.

## Out of scope (current version)

- Multi-tenant authentication for the API (assumes trusted LAN or localhost).
- Encrypted storage at rest for Chroma (relies on host disk controls).
- Production-grade high availability (single-process API design).

## Related reading

- Operators: `user/01-prerequisites.md` onward.
- Implementers: `developer/01-repository-structure.md` onward.
- Integrators: `reference/rest-api.md`, `reference/tools-catalog.md`.
- Interactive reference: `technical-reference.html` (open in browser).
