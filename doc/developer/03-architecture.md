# Developer Guide 03 — Architecture

## Objective

Describe control flow, process boundaries, and coupling between subsystems.

## Process model

```
┌─────────────────┐     HTTP      ┌──────────────────┐
│  Next.js (web)  │ ──────────────► │  FastAPI (hexnode) │
└─────────────────┘                 └────────┬─────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         │                         │
                    ▼                         ▼                         ▼
            ┌───────────────┐         ┌───────────────┐         ┌───────────────┐
            │ OllamaClient  │         │ MemoryStore   │         │ Async tasks   │
            │  (httpx)      │         │  (Chroma)     │         │ ingest_watcher│
            └───────┬───────┘         └───────────────┘         └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │ Ollama daemon │
            └───────────────┘
```

**EEG jobs:** the API process does not load the full MNE/science stack in-process for visualization. Pipeline and `run_visualizations.py` run in a **synchronous child process** resolved by `python_for_eeg()`: **`paradox-eeg-worker.exe`** when frozen next to the API bundle, otherwise venv / `PARADOX_EEG_PYTHON`. See `eeg_subprocess_launcher.py`, `hexnode/config.py`, and `user/09-eeg-research.md`.

**Frozen worker details (v0.3.2+):** The worker’s own `_internal` tree **shall** include a valid **`orjson`** package (PyInstaller `collect_all("orjson")` in `paradox-eeg-worker.spec`). Plotly 6.x uses `orjson` when exporting `Figure.to_html()`; relying only on the API bundle’s `orjson` directory on `PYTHONPATH` could yield a namespace package with no `OPT_*` flags, silently breaking every Plotly HTML step. **`eeg_subprocess_launcher.py`** also sets UTF-8 stdio defaults so Windows subprocesses do not fail on Unicode in `print()` (trace viewer). **`hexnode/eeg/viz/run_visualizations.py`** `_compute_microstates()` output must match `microstate_visualizer`’s expected keys and `maps` layout.

## Lifespan (FastAPI)

**Startup:**

1. Construct `OllamaClient`.
2. Construct `MemoryStore(ollama)` — initializes or opens Chroma persistent path.
3. Ensure ingest queue directory exists.
4. Start `ingest_watcher_loop` as `asyncio.Task`.

**Shutdown:**

1. Cancel watcher task; await cancellation.
2. Close httpx client on `OllamaClient`.

## Agent execution path

1. Route handler validates `AgentRequest`.
2. `run_agent(message, memory, ollama, interface)` executes.
3. Registry builds tool specification list for system prompt.
4. Loop: `ollama.chat` with `format_json=True` until stop conditions.
5. On each tool call: `registry.run(name, ctx, params)` with filtered kwargs matching `run` signature.
6. Final answer persisted via `memory.add_text` to `chat_history`.
7. Optional Skye: synchronous httpx POST to remote `/api/generate` if URL configured and confidence low.

The **`POST /agent` route** catches **`httpx.ReadTimeout`** from Ollama and returns **504** (see `hexnode/api/main.py`).

## Coupling rules

| From | To | Coupling |
|------|-----|----------|
| API | Agent | Direct function call. |
| Agent | Tools | Registry only; tools **shall not** import agent. |
| Tools | Memory | Via `ToolContext.memory`. |
| Tools | Ollama | Via `ToolContext.ollama` where needed. |
| Reflection | Memory, Ollama | Direct; **shall not** import tools (avoids cycles). |

## Concurrency

- FastAPI handles concurrent requests; a single global `_memory` and `_ollama` are shared. **Implication:** heavy concurrent writes to Chroma may contend; scale-out is not a design goal for this version.
- Watcher and request handlers share `MemoryStore`; Chroma client is assumed thread-safe per upstream library contract.

## Related

- `developer/05-agent-and-prompts.md` — loop detail.
- `reference/rest-api.md` — external contract.
