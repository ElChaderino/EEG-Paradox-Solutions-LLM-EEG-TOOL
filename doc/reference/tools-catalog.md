# Technical Reference — Tools Catalog

## Objective

List each tool’s name, purpose, and parameters as wired through `ToolContext` and registry filtering.

**Convention:** Parameters listed are accepted kwargs after filtering; omitted keys use Python defaults in `run`.

---

### `query_memory`

**Description:** Semantic search across Chroma; touches hit ids for scoring.

| Parameter | Type | Notes |
|-----------|------|-------|
| `query` | string | Required. |
| `collection` | string \| null | Optional subset. |
| `top_k` | int \| null | Optional; defaults to settings. |

---

### `get_system_stats`

**Parameters:** none.

**Returns:** Dict with CPU, RAM, disk, optional GPU fields from `nvidia-smi`.

---

### `get_datetime`

| Parameter | Type | Notes |
|-----------|------|-------|
| `timezone` | string | Optional IANA zone name. |

---

### `get_realtime_stats`

| Parameter | Type | Notes |
|-----------|------|-------|
| `limit` | int | Process list length clamped 3–40. |

---

### `web_search`

| Parameter | Type | Notes |
|-----------|------|-------|
| `query` | string | Needs one of: `SEARXNG_URL`, or `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX`, or `WEB_SEARCH_FALLBACK_DDG=true` (DuckDuckGo). |

---

### `fetch_url`

| Parameter | Type | Notes |
|-----------|------|-------|
| `url` | string | HTTP(S); trafilatura extract; capped length. |

---

### `ingest_document`

| Parameter | Type | Notes |
|-----------|------|-------|
| `path_or_url` | string | File path or URL. |

---

### `run_shell_command`

| Parameter | Type | Notes |
|-----------|------|-------|
| `preset` | string | Allowlisted: `nvidia_smi`, `netstat_listening`. |

---

### `boost_memory`

| Parameter | Type | Notes |
|-----------|------|-------|
| `memory_id` | string | Chroma id. |
| `collection` | string | Default `chat_history`. |
| `amount` | float | Default `0.15`. |

---

### `run_reflection`

**Parameters:** none.

**Side effect:** Reflection pass; vault files updated.

---

### `skye_infer`

| Parameter | Type | Notes |
|-----------|------|-------|
| `prompt` | string | Remote Ollama generate; requires `SKYE_URL`. |

---

### `send_discord_message`

| Parameter | Type | Notes |
|-----------|------|-------|
| `text` | string | Bot token + channel required in settings. |

---

### `lora_send`

| Parameter | Type | Notes |
|-----------|------|-------|
| `payload` | string | Stub; always returns not implemented error. |

---

### `run_python_analysis`

**Description:** Executes the given script string in a subprocess with cwd = EEG workspace, Matplotlib `Agg`, timeout (~300s), and up to **2 automatic retries** on common MNE/ICLabel-style errors. New files under `eeg_workspace/output/` are listed in the tool result.

| Parameter | Type | Notes |
|-----------|------|-------|
| `script` | string | Required. Full Python source (preamble forces Agg + warning filter). |

**Feature:** Typically `python_analysis` license flag (e.g. Pro+).

---

### `run_eeg_pipeline`

**Description:** Builds `PipelineConfig`, writes a generated 24-step script via `hexnode.eeg.pipeline`, executes it in the venv interpreter, returns metrics / step status / output paths.

| Parameter | Type | Default | Notes |
|-----------|------|---------|--------|
| `filename` | string | — | Required. File in `eeg_workspace/` (or resolvable path). |
| `hp_freq` | float | 0.5 | High-pass (Hz). |
| `lp_freq` | float | 40 | Low-pass (Hz). |
| `notch_freq` | float | 60 | Line frequency. |
| `ica_method` | string | `fastica` | ICA backend. |
| `icalabel_threshold` | float | 0.80 | Non-brain component cutoff. |
| `connectivity_method` | string | `coh` | Spectral connectivity method token. |

**Feature:** `eeg`.

---

### `get_eeg_results`

**Description:** Reads pre-computed JSON / reports from `eeg_workspace/output/` for a completed job (or lists jobs when `job_id` is `list`).

| Parameter | Type | Notes |
|-----------|------|-------|
| `job_id` | string | Optional; default = latest job; `"list"` enumerates. |
| `include` | string | `all` (default), `metrics`, `clinical`, `bandpower`. |

**Feature:** `eeg`.

---

### `list_eeg_scripts`

**Description:** Lists or returns source of bundled templates under `data/eeg_scripts` (or frozen-app copy under LocalAppData when packaged).

| Parameter | Type | Notes |
|-----------|------|-------|
| `name` | string | Optional; if set, return that `.py` template body. |

**Feature:** `eeg`.

---

### `deep_research`

**Description:** Multi-source research with caching (SearXNG and fetched pages). Separate from EEG.

**Feature:** `deep_research`.

---

## Related

- `developer/04-tools-and-registry.md` — implementation rules.
- `reference/security.md` — shell allowlist rationale.
- `user/09-eeg-research.md` — EEG jobs and UI.
