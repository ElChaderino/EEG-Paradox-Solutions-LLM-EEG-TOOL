# Technical Reference — Configuration

## Objective

Enumerate environment variables and defaults as implemented in `hexnode.config.Settings`.

## Loading rules

- **Editable dev / repo checkout:** `.env` in the project root (working directory when starting the API).
- **PyInstaller / frozen build:** `%LOCALAPPDATA%\ParadoxSolutionsLLM\.env` (see `hexnode.config._env_file_path`).
- Names are case-insensitive per pydantic-settings convention.
- Unknown keys are ignored (`extra = "ignore"`).

## Core server

| Variable | Field | Default | Description |
|----------|--------|---------|-------------|
| `HOST` | `host` | `0.0.0.0` | Uvicorn bind host (see `run_server.py`). |
| `PORT` | `port` | `8765` | HTTP port. |
| `CORS_ORIGINS` | `cors_origins` | includes localhost web + **8765** + Tauri origins (`tauri://localhost`, etc.) | Comma-separated list for FastAPI CORS; see `hexnode.config.Settings` for the full default string. |

## Ollama

| Variable | Field | Default |
|----------|--------|---------|
| `OLLAMA_BASE` | `ollama_base` | `http://127.0.0.1:11434` |
| `CHAT_MODEL` | `chat_model` | `qwen3:8b` |
| `FAST_MODEL` | `fast_model` | empty (if set, e.g. `phi4-mini`, used for lighter tasks) |
| `EMBED_MODEL` | `embed_model` | `nomic-embed-text` |

## Skye (remote Ollama)

| Variable | Field | Default |
|----------|--------|---------|
| `SKYE_URL` | `skye_url` | empty (disabled) |
| `SKYE_MODEL` | `skye_model` | `mistral-small:22b` |

## Web search

| Variable | Field | Default | Description |
|----------|--------|---------|-------------|
| `SEARXNG_URL` | `searxng_url` | empty | Self-hosted SearXNG base URL (no trailing slash). When set, `web_search` uses SearXNG only for that path. |
| `GOOGLE_CSE_API_KEY` | `google_cse_api_key` | empty | Google Custom Search JSON API key. |
| `GOOGLE_CSE_CX` | `google_cse_cx` | empty | Programmable Search Engine ID (cx). With API key, `web_search` and `deep_research` web leg use **Google first**, then merge DuckDuckGo when `WEB_SEARCH_FALLBACK_DDG` is true. |
| `WEB_SEARCH_FALLBACK_DDG` | `web_search_fallback_ddg` | `true` | DuckDuckGo as secondary (or sole web source when Google keys are unset and SearXNG is unset). |
| `WEB_SEARCH_AUTO_FETCH` | `web_search_auto_fetch` | `true` | Fetch top result pages inside `web_search`. |
| `WEB_SEARCH_AUTO_FETCH_MAX` | `web_search_auto_fetch_max` | `2` | Extra top HTML pages to pull text from. |
| `WEB_SEARCH_AUTO_FETCH_CHARS` | `web_search_auto_fetch_chars` | `3000` | Character cap per fetched page snippet in tool output. |

## Paths

| Variable | Field | Default |
|----------|--------|---------|
| `CHROMA_PATH` | `chroma_path` | `<repo>/data/chroma` |
| `VAULT_PATH` | `vault_path` | `<repo>/data/vault` |
| `INGEST_QUEUE` | `ingest_queue` | `<repo>/data/ingest_queue` |

**Note:** `reflections_dir` and `current_focus_file` default under `vault_path`; override requires code change unless new env fields are added in a fork.

## Agent parameters

| Variable | Field | Default |
|----------|--------|---------|
| `AGENT_MAX_STEPS` | `agent_max_steps` | `8` |
| `CONFIDENCE_THRESHOLD` | `confidence_threshold` | `0.75` |
| `MEMORY_SEARCH_TOP_K` | `memory_search_top_k` | `8` |

## Memory ranking

Weights are **normalized to sum 1.0** at runtime. Similarity = `1/(1+distance)`; recency = exponential decay from `last_accessed` with half-life in days.

| Variable | Field | Default |
|----------|--------|---------|
| `MEMORY_W_SIM` | `memory_w_sim` | `0.45` |
| `MEMORY_W_IMP` | `memory_w_imp` | `0.20` |
| `MEMORY_W_REC` | `memory_w_rec` | `0.20` |
| `MEMORY_W_BOOST` | `memory_w_boost` | `0.15` |
| `MEMORY_RECENCY_HALF_LIFE_DAYS` | `memory_recency_half_life_days` | `14.0` |

Set `MEMORY_RECENCY_HALF_LIFE_DAYS` to `0` to treat recency as neutral (0.5).

## Neuro-symbolic rules

| Variable | Field | Default |
|----------|--------|---------|
| `SYMBOLIC_ENABLED` | `symbolic_enabled` | `true` |
| `SYMBOLIC_RULES_PATH` | `symbolic_rules_path` | `<repo>/data/rules.yaml` |

Packaged defaults live in `hexnode/symbolic/default_rules.yaml` and merge with `data/rules.yaml` if present. Copy `rules.example.yaml` to `data/rules.yaml` to extend.

## Reflection

| Variable | Field | Default |
|----------|--------|---------|
| `REFLECTION_MIN_CONFIDENCE` | `reflection_min_confidence` | `0.35` |
| `REFLECTION_COMPARE_PREVIOUS` | `reflection_compare_previous` | `true` |

Below-min confidence writes a tentative markdown note and may preserve `current_focus` if the new focus is too short.

## Discord (tool + optional script)

| Variable | Field | Default |
|----------|--------|---------|
| `DISCORD_TOKEN` | `discord_token` | empty |
| `DISCORD_GUILD_ID` | `discord_guild_id` | `0` |
| `DISCORD_CHANNEL_ID` | `discord_channel_id` | `0` |

## Frontend (Next.js)

Not read by Python. Set in shell or `.env.local` in `web/`:

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_PARADOX_API` | Base URL for browser-side fetch (default in code: `http://127.0.0.1:8765`). |
| `NEXT_PUBLIC_HEX_API` | Legacy alias for the same. |
| `NEXT_PUBLIC_ANTON_API` | Legacy alias for the same. |

## Discord script

| Variable | Purpose |
|----------|---------|
| `PARADOX_API` | Base URL for `scripts/discord_bot.py` (default `http://127.0.0.1:8765`). |
| `HEX_API` | Legacy alias. |
| `ANTON_API` | Legacy alias. |

## EEG visualization subprocess

Resolved in `hexnode.config.python_for_eeg()` (not all fields are on `Settings`):

| Variable | Purpose |
|----------|---------|
| `PARADOX_EEG_PYTHON` | Path to `python.exe` **or** to `paradox-eeg-worker.exe` to run `run_visualizations.py` and related scripts. Checked first. |
| `EEG_PYTHON` | Same as `PARADOX_EEG_PYTHON` (second priority). |

When unset, frozen builds prefer the bundled **`eeg-worker/paradox-eeg-worker.exe`** if present and probe-clean; otherwise the code falls back to `py -3` / `python` on `PATH`.

## Related

- `.env.example` in repository root.
- `reference/rest-api.md` for runtime behavior.
