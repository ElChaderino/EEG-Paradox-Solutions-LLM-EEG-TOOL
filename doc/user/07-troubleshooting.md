# User Manual 07 — Troubleshooting

## Objective

Systematic fault isolation from symptoms to corrective action.

## 1. Health endpoint degraded

**Symptom:** `GET /health` returns `"status": "degraded"` or `"ollama": false`.

| Check | Action |
|-------|--------|
| Ollama running | Start Ollama; verify tray or process. |
| Wrong port | Set `OLLAMA_BASE` to actual origin. |
| Firewall | Allow localhost loopback (rarely blocked). |

## 2. Agent returns errors or empty reasoning

**Symptom:** Chat shows `Error:` or nonsense after `/agent`.

| Check | Action |
|-------|--------|
| Model missing | `ollama pull` the configured `CHAT_MODEL`. |
| JSON parse failures | Reduce temperature via code if forked; ensure model supports JSON mode reasonably well. |
| **Read timeout (504)** | Ollama did not finish within the HTTP read window (heavy model load, first token after VRAM eviction, or CPU contention e.g. during a long EEG job). Retry when the machine is idle; ensure Ollama stays resident. The API returns **504** with a short explanation instead of a raw 500. |
| Long generations | Default Ollama client timeout is large (minutes); if you still hit limits, use a smaller/faster model or reduce context. |

## 3. Memory search always empty

| Check | Action |
|-------|--------|
| No data yet | Run a few chats or ingest documents. |
| Wrong collection | Omit `collection` in query to search all, or specify valid name. |
| Embedding model | `EMBED_MODEL` must match vectors already stored; changing model requires re-embed migration. |

## 4. Ingest queue not processing

| Check | Action |
|-------|--------|
| API not running | Watcher is tied to API lifespan. |
| Unsupported extension | Use pdf, txt, md only. |
| File locked | Close editors holding exclusive locks. |

## 5. Chroma or disk errors on Windows

| Check | Action |
|-------|--------|
| Antivirus | Exclude `data/chroma` from aggressive real-time scan if locking occurs. |
| Long paths | Keep project path reasonably short. |
| Permissions | Run from a user-writable directory. |

## 6. Web UI cannot reach API

| Check | Action |
|-------|--------|
| CORS | Add browser origin to `CORS_ORIGINS`. |
| Wrong API URL | Set `NEXT_PUBLIC_HEX_API`. |
| Mixed content | Avoid HTTPS page calling HTTP API without proxy (browser blocks). |

## 7. Skye escalation silent or failing

| Check | Action |
|-------|--------|
| Empty `SKYE_URL` | Escalation disabled by design. |
| Network | Ping/telnet host:11434 from Paradox host. |
| Model name | Remote must have `SKYE_MODEL`. |

## 8. EEG upload or job fails (no outputs, error status, partial files)

**Context:** `POST /eeg/process` copies the file under `data/eeg_workspace/`, then a background thread runs the generated pipeline scripts and **`run_visualizations.py`** in a **separate Python process**. See [User 09 — EEG research](09-eeg-research.md).

**Symptom:** Job ends `error` or `complete_with_warnings`, or `output_files` stays nearly empty.

| Check | Action |
|-------|--------|
| EEG extras not installed (dev) | From source: `pip install -e ".[eeg]"` in the venv used by the API. |
| Installed app missing worker | Confirm `GET /health` → `eeg_subprocess.bundled_worker: true` and `viz_script_found: true`. Reinstall from a build produced by `scripts/build_release.ps1` (includes `eeg-worker/paradox-eeg-worker.exe`). |
| Wrong interpreter for subprocess | The viz step uses **`paradox-eeg-worker.exe`** when bundled, else **`PARADOX_EEG_PYTHON` / `EEG_PYTHON`**, else discovery (`py -3`, `python`). Point the env var at a Python with `[eeg]` if you bypass the worker. |
| Unsupported or non-standard montage | Very short recordings, non–10–20 montages, or bipolar-only exports may cause pipeline or NetOps steps to skip or error. Try a standard 10–20 EDF; check job `messages` in `GET /eeg/jobs/{id}`. |
| NetOps bundle missing | Full traceroute + dashboard pack lives under `hexnode/eeg/netops_standalone`. If import/path fails, you may still get topomaps/microstates but not the extended HTML tabs. Logs show "NetOps … skipped". |
| Disk / permissions | Ensure `data/eeg_workspace/output/<job_id>/` is writable and has free space (figures and HTML add tens to hundreds of MB per run). |
| Timeout | Extremely long EDFs may hit subprocess timeouts in `main.py`; split epochs or shorten file for testing. |
| Antivirus | Same as Chroma: aggressive scanning of `eeg_workspace` can lock temp `.py` or block `python` child processes briefly. |

**Symptom:** Many NetOps **table** HTML files exist, but **interactive traceroute**, **Granger Plotly**, **3D scalp**, **LORETA**, **Coben-style brain**, **microstate interactive**, or **trace viewer** HTML are missing (especially on **MSI/NSIS** builds before **v0.3.2**).

| Check | Action |
|-------|--------|
| Not licensing | This build has **no** product license gating; missing Plotly outputs are **not** caused by license or feature flags in the visualization pipeline. |
| Broken `orjson` in worker (fixed in **0.3.2**) | Plotly 6.x calls **`orjson`** inside **`fig.to_html()`**. An improperly laid-out `orjson` on `PYTHONPATH` produced empty HTML / skipped files. **Reinstall** from a **0.3.2+** build; worker bundles **`orjson`** via `paradox-eeg-worker.spec`. |
| Trace viewer only missing | Windows **cp1252** + emoji in logs could abort trace viewer early. **0.3.2** sets UTF-8 in **`eeg_subprocess_launcher.py`**. |
| Microstate interactive only missing | **0.3.2** fixes **`_compute_microstates()`** output shape (`ch_names`, list **`maps`**, downsampled labels/GFP) for **`microstate_visualizer.py`**. |
| Incomplete API `_internal` | If `hexnode/eeg/` under the API bundle is truncated (e.g. after a partial update), the worker cannot load `run_visualizations.py` / NetOps. **Reinstall** full build or run **`scripts/build_release.ps1`** and deploy the complete `dist/paradox-api` tree. |

**Symptom:** Interactive HTML opens blank or Plotly never loads.

| Check | Action |
|-------|--------|
| Offline / CSP | Some dashboards load Plotly from a CDN; allow network for first paint or use wired internet once. |
| iframe | If embedding in another site, use the API file route that sets iframe-friendly headers (`GET /eeg/jobs/{id}/files/...`), not arbitrary `file://` URLs. |

**Symptom:** Clinician summary or Swingle columns look empty.

| Check | Action |
|-------|--------|
| Metrics shape | EO/EC-nested `metrics_by_site` is flattened in the renderer; if the pipeline produced no per-site band metrics, tables stay sparse. Re-run with a standard recording and confirm `*_metrics.json` in the job folder. |

After changes, start a **new** job (old folders under `output/<job_id>/` are not regenerated automatically).

## Escalation to development

If logs show repeated tracebacks in the `hexnode` logger, capture:

1. Python version and `pip freeze` excerpt.
2. Relevant `.env` keys (redact tokens).
3. Minimal reproduction message for `/agent`.
4. For EEG: `job_id`, last 30 lines of `messages` from `GET /eeg/jobs/{id}`, and the `eeg_subprocess` block from `GET /health` (bundled worker vs custom Python).

File an issue or patch per `developer/05-agent-and-prompts.md` if the agent contract changes are required.
