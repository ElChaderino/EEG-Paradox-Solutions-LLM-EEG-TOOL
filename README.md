<!--
  X-Clacks-Overhead: GNU Terry Pratchett
  A man is not dead while his name is still spoken.
-->

<div align="center">

# Paradox Solutions LLM

### **Private testing only** · Windows installer · not a public product

[![Status](https://img.shields.io/badge/testing-private%20closed%20beta-00e5ff?style=for-the-badge&labelColor=0d1117)](#)
[![OS](https://img.shields.io/badge/OS-Windows%2010%2F11-0078D6?style=for-the-badge&logo=windows&logoColor=white&labelColor=0d1117)](#)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-39ff14?style=for-the-badge&labelColor=0d1117)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.4-cyan?style=for-the-badge&labelColor=0d1117)](#)

*Local-first AI research assistant — FastAPI agent, Chroma memory, optional EEG stack, Next.js + Tauri shell.*  
*No cloud LLM required for core inference. Your machine, your data, your threads.*

</div>

---

> [!CAUTION]
> **Private testing program — read this first.**  
> This build is distributed **only** to invited testers (Discord / private GitHub). It is **not** a general release, **not** supported for production clinical use as a standalone diagnostic device, and **must not** be reposted, mirrored, or shared outside the group you were admitted with. **Do not redistribute the installer, license keys, or internal links.** Feedback is welcome; leaks are not. GPL obligations for **source** still apply when binaries are shared — stay inside the agreed channel.


> [!WARNING]
> **Clinical disclaimer.** All EEG-related narratives, dashboards, z-scores, pattern–condition text, and “clinical-style” tabs are **decision support and education**, **not** a diagnosis or a substitute for professional interpretation. **Clinicians** remain responsible for judgment, consent, and standard of care. **End users** should treat outputs as exploratory unless a qualified professional says otherwise.

---

## Table of contents

1. [Private testing scope](#private-testing-scope)
2. [Who this is for](#who-this-is-for)
3. [What you are running](#what-you-are-running)
4. [LLM use cases (why the agent exists)](#llm-use-cases-why-the-agent-exists)
5. [EEG setup, pipelines, and outputs](#eeg-setup-pipelines-and-outputs)
6. [Agent tool layers (catalog by purpose)](#agent-tool-layers-catalog-by-purpose)
7. [Architecture at a glance](#architecture-at-a-glance)
8. [KV cache & TurboQuant-style embeddings (custom optimizations)](#kv-cache--turboquant-style-embeddings-custom-optimizations)
9. [Requirements](#requirements)
10. [Install (private `.exe`)](#install-private-exe)
11. [Machine registration — full activation](#machine-registration--full-activation)
12. [First run](#first-run)
13. [Optional: Discord bridge](#optional-discord-bridge)
14. [Environment cheat sheet](#environment-cheat-sheet)
15. [Troubleshooting](#troubleshooting)
16. [How to report feedback](#how-to-report-feedback)

---

## Private testing scope

| Expectation | Detail |
|-------------|--------|
| **Audience** | Invited testers only. |
| **Purpose** | Exercise the installer, UI, agent, optional EEG jobs, and license flows; report bugs and UX friction. |
| **Stability** | Builds may change daily/weekly. Breaking changes are possible. |
| **Support** | Best-effort through the organizer channel — not a SLA. |
| **Data** | Use de-identified or synthetic data when possible; you are responsible for PHI rules in your jurisdiction. |
| **Future** | A wider or public release would ship its own README, signing, and support story — **this document does not promise that.**

---

## Who this is for

| Role | How Paradox is meant to help |
|------|------------------------------|
| **End user / research participant (non-clinician)** | Chat with a **local** model; upload EEG through a guided **EEG Data** panel; run **one-click jobs**; open HTML dashboards and downloads without touching Python. Get **plain-language** summaries from the agent when you ask questions about outputs — still subject to human judgment for any health meaning. |
| **Clinician / neurofeedback practitioner / qEEG reader** | Use the same UI plus **deep artifacts**: multi-tab summaries (band power, session z-scores, vigilance, methodology-oriented tabs), **pattern–condition** style narratives with guard rails, connectivity / NetOps-style explorers, and **export** of full report folders to **Documents → EEG Paradox Reports**. Treat everything as **adjunct visualization and documentation**, not a labeled medical device output. |
| **Operator / IT (you or your tech)** | Install Ollama, manage `.env`, optional **SearXNG** / **Skye**, run the optional **Discord** bot script, verify **`GET /health`** (including `eeg_subprocess` / bundled worker), and keep the API up while jobs run. |

The **LLM** is the glue: it can **orchestrate** tools (run pipeline, fetch prior job JSON, search the web, read memory) so the **end user** does not need to know file paths, while the **clinician** can still open the **raw HTML/PNG** products for their own reading.

---

## What you are running

**Paradox Solutions LLM** is one deployable unit: **Ollama** (local LLM), **ChromaDB** (vector memory), a **bounded multi-step agent** with a **tool registry**, **FastAPI**, **Next.js** UI, optional **Tauri** shell, and a frozen **EEG worker** (`.exe`) that carries MNE, SciPy, Plotly, and related science stacks so operators are not forced to build a Python environment before the first topomap.

A system that cannot explain what it is doing is not an assistant — it is a liability with a chat box. This README is the short map; **`doc/technical-reference.html`** in the source repo is the long-form atlas (math, layers, formulas).

---

## LLM use cases (why the agent exists)

These are **design intents** for the local agent + tools — not promises that every model size will do equally well on every task.

### Research and knowledge work (no EEG)

- **Literature-style Q&A** over **your** ingested PDFs, notes, and pasted URLs — via **`ingest_document`**, **`fetch_url`**, and **`query_memory`** (semantic search with recency/scoring).
- **Web-augmented answers** when **`SEARXNG_URL`** is set: **`web_search`** feeds the model grounded snippets; **`deep_research`** (when licensed/enabled) does multi-page cached research passes separate from EEG.
- **Session continuity**: chat history and vault-style reflection via **`run_reflection`** and memory tools so long projects do not “forget” the thread.
- **Machine awareness**: **`get_system_stats`**, **`get_realtime_stats`**, **`get_datetime`**, and allowlisted **`run_shell_command`** presets help debug “why is this slow?” without handing the model arbitrary shell.

### Orchestration (you describe intent; tools do the I/O)

- **Multi-step plans**: the loop can chain tools (e.g. ingest → search memory → summarize) with explicit **observe** steps so actions are logged, not hidden.
- **Optional second opinion**: **`skye_infer`** calls a **remote Ollama** you control (`SKYE_URL`) for heavier generation when local confidence is low — still **your** infrastructure if you enable it.

### EEG-adjacent conversational layer

- After a job completes, **`get_eeg_results`** can pull **metrics / clinical JSON / bandpower** from `eeg_workspace/output/` so the model can **narrate** what landed on disk — useful for **end users** who do not want to open every HTML file.
- **`list_eeg_scripts`** exposes bundled **template scripts** so power users (and the agent) can reason about what *could* be run with **`run_python_analysis`** (custom MNE code in a sandboxed subprocess with retries).

### What the LLM is *not* trying to be

- **Not** a cloud API product (core path is **local** Ollama).
- **Not** a replacement for a credentialed clinician’s interpretation of EEG.
- **Not** guaranteed “always correct” on tool args — that is why tools return structured errors and the UI shows job status.

---

## EEG setup, pipelines, and outputs

### Three lanes (how work gets done)

1. **Agent-driven** — The model may call **`run_eeg_pipeline`** (generated **24-step** MNE preprocessing + spectral/connectivity script) and **`run_python_analysis`** (arbitrary MNE script string; **Agg** backend; timeout and **automatic retries** on common MNE/ICLabel-style failures). Outputs land under the **EEG workspace** (`data/eeg_workspace/...` in dev; packaged paths differ but the same structure).
2. **One-click UI jobs** — **EEG Data** panel: upload **`.edf`**, **`.bdf`**, **`.set`**, **`.fif`**, **`.vhdr`**, **`.cnt`**, etc.; optional **condition** (e.g. EC/EO), **output mode**, **remontage** hints. Background job runs generated pipeline + Clinical Q–style script + band-power script + **`run_visualizations.py`** orchestrator → **HTML**, **PNG**, **3D scalp**, **microstates**, and when available the **NetOps / traceroute** bundle.
3. **Read-only browsing** — **`GET /eeg/jobs`**, job detail, per-file serve for iframe preview, **`GET /eeg/outputs`** for legacy global outputs, **`POST /workspace/open`** to open the output folder in Explorer.

### What typically lands on disk (high level)

- **Preprocessing**: cleaned **FIF**, epochs, quality/metrics **JSON**, band-power tables.
- **Topography**: per-band **topomaps**, topo sheets (absolute/relative).
- **3D scalp**: interactive **HTML** surfaces.
- **Microstates**: maps, stats, transition views.
- **NetOps / traceroute**: interactive explorer plus linked dashboards (clinician summary, latency/SLA views, packet-loss style panels, microstate–propagation, pattern–condition evidence, PEM, topology/path analytics, TBI/PD-oriented summaries when adapters run, vigilance timeline, runbooks, etc.). If the full bundle cannot run, a **synthetic traceroute fallback** may still render from band-power graphs.

### Clinician-oriented layers (how it is *meant* to be useful)

- **Clinician summary** HTML: multi-tab views (e.g. Easy / Advanced / Expert plus methodology-oriented tabs) with band power and session-relative **z-scores**, **vigilance** when classifiers run, EO/EC-aware metrics where available.
- **Pattern–condition engine**: maps markers (power, asymmetry, connectivity, vigilance, …) to **condition-style narratives** with language tuned for **screening / education**, not diagnosis.
- **Export**: copy full artifact sets to **Documents → EEG Paradox Reports → `<recording_stem>_<job_id>`** for charting, second reads, or archival (subject to your HIPAA/IRB practice).

### End-user-oriented layers

- **Single panel** upload and progress polling — no CLI.
- **In-app HTML** preview (iframe) and downloads.
- **Agent** can answer “what did this job produce?” by reading structured results — simpler than parsing folders manually.

### Which Python runs the heavy EEG process

- **Packaged app**: prefers **`paradox-eeg-worker.exe`** beside the API bundle; **`PYTHONPATH`** points at the API internals so `import hexnode` matches the server.
- **Override**: **`PARADOX_EEG_PYTHON`** or **`EEG_PYTHON`** → path to **`python.exe`** or another worker.
- **Dev**: active venv with **`pip install -e ".[eeg]"`** for full NetOps output.

Check **`GET /health`** → **`eeg_subprocess`** for the resolved executable and whether the bundled worker was found.

---

## Agent tool layers (catalog by purpose)

Tools are registered and **license-filtered** in the product build (e.g. **`eeg`**, **`deep_research`**, **`python_analysis`** tiers). If a tool “does nothing,” check activation tier and `.env`, not just the model.

### Memory & documents

| Tool | What it does | Clinician / user angle |
|------|----------------|-------------------------|
| **`query_memory`** | Semantic search over Chroma collections; touches ids for scoring. | “What did we decide last week about this patient protocol?” (with proper de-identification practices). |
| **`ingest_document`** | Ingest file path or URL into memory pipeline. | Build a **private** knowledge base (papers, SOPs, client education sheets). |
| **`boost_memory`** | Adjust strength of a stored memory id. | Curate what the assistant should preferentially recall. |
| **`run_reflection`** | Reflection pass; vault markdown updated. | Longitudinal projects — compress and file “what mattered” without losing thread. |

### System & environment

| Tool | What it does | Clinician / user angle |
|------|----------------|-------------------------|
| **`get_system_stats`** | CPU, RAM, disk, optional GPU via `nvidia-smi`. | “Do I have VRAM left before I run another job?” |
| **`get_realtime_stats`** | Top processes snapshot. | Find hogging apps without Task Manager gymnastics. |
| **`get_datetime`** | Wall clock with optional IANA timezone. | Timestamping notes and reports consistently. |
| **`run_shell_command`** | **Allowlisted** presets only (e.g. `nvidia_smi`, `netstat_listening`). | Safe operator diagnostics — not arbitrary shell. |

### Web & external content

| Tool | What it does | Clinician / user angle |
|------|----------------|-------------------------|
| **`web_search`** | SearXNG JSON search; requires **`SEARXNG_URL`**. | Pull current guidelines or device manuals into a **local** reasoning pass (mind privacy of query text). |
| **`fetch_url`** | Fetch + extract readable text (trafilatura); capped. | Stable link ingestion for literature updates. |
| **`deep_research`** | Multi-source cached research (feature-gated). | Deeper “survey this topic” passes than a single search. |

### Remote inference (optional)

| Tool | What it does | Clinician / user angle |
|------|----------------|-------------------------|
| **`skye_infer`** | Remote Ollama generate; requires **`SKYE_URL`**. | Offload a heavy rewrite/second pass to a **LAN** GPU you own; still not a public API. |

### Notifications

| Tool | What it does | Clinician / user angle |
|------|----------------|-------------------------|
| **`send_discord_message`** | Post to configured bot channel via REST. | Ping yourself or a team room when a long job finishes (token in `.env`). |
| **`lora_send`** | Stub — returns not implemented. | Placeholder for future hardware bridge fantasies. |

### EEG & analysis

| Tool | What it does | Clinician / user angle |
|------|----------------|-------------------------|
| **`run_eeg_pipeline`** | Full **24-step** pipeline script generation + execution from workspace file; params for filters, ICA, connectivity method, etc. | **Batch-style** standardized preprocessing + metrics without clicking each step. |
| **`run_python_analysis`** | Run arbitrary **Python** (MNE) in subprocess under EEG workspace; **Agg**; retries; lists new outputs. | **Custom** metrics, prototypes, or lab-specific scripts — clinician with analyst support. |
| **`get_eeg_results`** | Read job JSON / clinical / bandpower from output dir, or **`list`** jobs. | Agent summarizes **latest** or **named** run for chat. |
| **`list_eeg_scripts`** | List or return bundled **`data/eeg_scripts`** templates. | Discover what shipped; scaffold **`run_python_analysis`**. |

---

## Architecture at a glance

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Tauri shell │ ─► │  Next.js UI │ ─► │   FastAPI   │ ─► │ Agent loop  │
└─────────────┘    └─────────────┘    └─────────────┘    └──────┬──────┘
                                                                  │
                    ┌─────────────────────────────────────────────┼─────────────────────────┐
                    ▼                     ▼                       ▼                         ▼
             ┌─────────────┐     ┌─────────────┐         ┌───────────┐           ┌─────────────┐
             │   Ollama    │     │  ChromaDB   │         │  Tools    │           │ EEG worker  │
             │   (LLM)     │     │  (memory)   │         │ registry  │           │  (.exe)     │
             └─────────────┘     └─────────────┘         └───────────┘           └─────────────┘
```

| Piece | Role |
|--------|------|
| **API** | HTTP: chat, agent, files, license, EEG jobs, workspace open. |
| **Agent** | Think → act → observe → answer; tools are explicit. |
| **Memory** | Chroma + ingest + reflection. |
| **EEG worker** | Frozen subprocess for MNE / Plotly / NetOps when packaged. |
| **Discord (optional)** | `scripts/discord_bot.py` → `POST /agent` with `interface: discord`. |

---

## KV cache & TurboQuant-style embeddings (custom optimizations)

Paradox ships **two** complementary optimizations that are easy to miss because they sit **below** the chat UI: one shrinks **GPU KV cache** for **Ollama**, the other shrinks **vector memory** footprint for **Chroma** using a **TurboQuant-inspired** recipe. Defaults are tuned so typical testers get the benefit without editing `.env`.

### KV cache quantization (Ollama / VRAM)

**What it is:** During autoregressive generation, the model stores **key/value tensors** for past tokens (the **KV cache**). In full **`f16`**, that cache dominates VRAM on long contexts or concurrent sessions.

**What Paradox does:** On startup the API calls `apply_ollama_env()` (`hexnode/ollama_client.py`), which sets Ollama’s environment **before** the runner loads the model:

| Mechanism | Env / setting | Effect |
|-----------|----------------|--------|
| **Flash attention** | `OLLAMA_FLASH_ATTENTION=1` when enabled (default **on** via `ollama_flash_attention`) | Faster, more memory-efficient attention paths where Ollama supports it. |
| **KV cache dtype** | `OLLAMA_KV_CACHE_TYPE` from settings (default **`q8_0`**) | **`q8_0`**: about **~50%** less KV cache VRAM vs `f16`. **`q4_0`**: about **~75%** savings. **`f16`**: no KV quant (closest to “vanilla” Ollama cache). |

**Tester-facing detail:** Quality can shift slightly at aggressive quant levels; if replies feel degraded, try **`q8_0`** before turning KV quant off entirely.

**Where to see it:** `GET /health` → `optimizations` includes `flash_attention`, `kv_cache_type`, and a short `kv_savings` hint (`q8_0` / `q4_0` / none).

---

### TurboQuant-style **embedding** quantization (Chroma / disk & RAM)

**What it is *not*:** This does **not** quantize the **LLM weights**. It targets **embedding vectors** produced by your embed model (e.g. `nomic-embed-text`) when documents and chat turns are written into **ChromaDB**.

**What it is:** `hexnode/embed_quantize.py` implements a **data-oblivious** pipeline **inspired by TurboQuant**:

1. **Deterministic random rotation** — A fixed-seed orthogonal matrix (Haar-style via QR) spreads mass across dimensions so no single coordinate hoards all the information.
2. **Scalar quantization** in the rotated frame — Per-vector min/max scaling to **8-bit** (default), **4-bit**, or **1-bit** (binary sign) levels.
3. **Inverse rotation** — Vectors are rotated back so downstream code still sees a **list of floats** in the original coordinate system.

**Why bother:** For a typical **768-d float32** embedding, raw storage is on the order of **3 KiB/vector**; aggressive quant targets **~4×** (int8-style), **~8×** (int4), or **~32×** (binary) **information compression** while **preserving cosine-similarity behavior** for retrieval better than naive “round each float.”

**Chroma note:** The implementation still returns **`list[float]`** because Chroma’s API expects floats; values sit on a **small discrete lattice**. The code documents room for future backends that store packed ints.

| `EMBED_QUANTIZE_BITS` | Mode | Rough compression (vs full float32) |
|------------------------|------|-------------------------------------|
| **`0`** | Off — passthrough | **1×** |
| **`8`** (default) | 256 levels after rotation | **~4×** |
| **`4`** | 16 levels | **~8×** |
| **`1`** | Sign only (+ normalization) | **~32×** |

**Who benefits**

| Audience | Benefit |
|----------|---------|
| **End user** | Larger personal **memory library** on the same disk; retrieval stays responsive. |
| **Clinician / power user** | Big ingest queues (papers, SOPs, de-identified notes) without exploding `chroma/` size as fast. |
| **Operator** | Fewer “Chroma ate my SSD” surprises; pair with **`OLLAMA_EMBED_ON_CPU=true`** (default in settings) so **embedding** runs on **CPU** and does not evict the **chat** model from a small **GPU**. |

**Where to see it:** `GET /health` → `optimizations.embed_quantize` shows `int8` / `int4` / `int1` or `off`.

---

### Quick `.env` reference (optimizations only)

```env
# Ollama KV + attention (also configurable via pydantic field names in .env)
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_FLASH_ATTENTION=1

# Chroma embedding quantization (TurboQuant-style path)
EMBED_QUANTIZE_BITS=8
```

Full configuration tables: `doc/reference/configuration.md` and root `README.md` in the source repository.

---

## Requirements

| Item | Notes |
|------|--------|
| **Windows 10/11 x64** | Primary OS for the installer under **private test**. |
| **Ollama** | [ollama.com](https://ollama.com) + at least one pulled model. |
| **RAM / VRAM** | Model-dependent; start small if unsure. |
| **Disk** | EEG jobs and HTML exports can be large. |
| **Network** | Localhost-first; optional SearXNG / Skye / Discord as **you** configure. |

---

## Install (private `.exe`)

Your tester package includes **two** Windows executables (names may match the Discord pin / private release):

| Artifact | Role |
|----------|------|
| **Paradox** desktop / API installer | The main application (chat, EEG panel, agent, etc.). |
| **`ParadoxMachineInfo.exe`** | Small **machine registration** helper — collects the **same machine fingerprint** the licensed product uses so you can request a **machine-locked** license key. |

Steps for the **main** installer:

1. **Download** only from the **Discord pin** or **private GitHub Release** you were given.
2. **Run** as a normal user (elevate if the installer asks).
3. **SmartScreen** may warn on unsigned beta builds — expected; proceed only if you trust the source.
4. **Path** — prefer simple ASCII paths for the install directory to avoid subprocess edge cases with the EEG worker.

> [!TIP]
> Put **build version** (**0.3.4**) and **build date** in every bug report.

---

## Machine registration — full activation

**`ParadoxMachineInfo.exe`** is a standalone, windowed utility (no console). It is built from the **License Manager** `machine_registration_app` project and is **not** the main Paradox app — run it when you need to **prove which PC** should receive a full activation.

### What it does

- Reads **machine ID**, **OS**, **arch**, and **hostname** using the same logic as production licensing (`machine_id` fingerprint).
- Lets you **copy** the Machine ID or a **full plain-text summary** to the clipboard.
- Lets you **Save JSON…** to a file (default suggested name `paradox_machine_registration.json`) containing a structured payload: schema version, product name, UTC timestamp, `machine_id`, and the full summary — **send this file or the Machine ID** through the **private channel** your organizer gave you (email, Discord DM, ticket — **not** a public GitHub issue).

### Workflow (typical)

1. On the **same Windows PC** where you will run Paradox, run **`ParadoxMachineInfo.exe`**.
2. Click **Copy Machine ID** *or* **Save JSON…** and attach the file in the agreed channel.
3. Wait for the vendor to return a **license key / file** and instructions to drop it where the app expects (see in-app **License** panel or tester notes).
4. Start the **main** Paradox application and complete activation there.

> [!WARNING]
> **Privacy:** The JSON and on-screen summary include **hostname** and hardware-derived identifiers. Treat the file like **PII-adjacent operational data** — send only to the authorized contact, never paste into public threads or issues.

> [!NOTE]
> If activation fails after you move disks, reinstall Windows, or change hardware, **re-run** `ParadoxMachineInfo.exe` on the new effective machine and request a re-key through the same private channel.

---

## First run

1. Start **Ollama**; confirm `ollama list`.
2. Launch **Paradox** from the shortcut.
3. Open the **web console**; send a short **ping**.
4. Optionally open **EEG Data** and run a **tiny test file** before clinical recordings.

> [!NOTE]
> **License** — if you need **full** tier activation, complete **[Machine registration — full activation](#machine-registration--full-activation)** first, then apply the key/file you receive. Do not post keys or JSON in screenshots or public issues.

---

## Optional: Discord bridge

The **Discord bot** is optional and separate from the `.exe`.

```bash
set DISCORD_TOKEN=your_bot_token
set DISCORD_CHANNEL_ID=numeric_channel_id
set PARADOX_API=http://127.0.0.1:8765
python scripts/discord_bot.py
```

| Variable | Purpose |
|----------|---------|
| `DISCORD_TOKEN` | Required. |
| `DISCORD_CHANNEL_ID` | Required. |
| `PARADOX_API` | Optional; default `http://127.0.0.1:8765`. `HEX_API` / `ANTON_API` legacy. |

Enable **Message Content Intent** in the Discord developer portal. Replies truncated ~**1900** chars.

---

## Environment cheat sheet

<details>
<summary><strong>Core variables (partial)</strong></summary>

| Variable | Purpose |
|----------|---------|
| `OLLAMA_HOST` | Non-default Ollama reachability. |
| `CHROMA_PATH` / related | Vector DB location when overridden. |
| `SEARXNG_URL` | Enables **`web_search`** / parts of **`deep_research`**. |
| `SKYE_URL` / `SKYE_MODEL` | Remote Ollama for **`skye_infer`**. |
| `DISCORD_TOKEN` / `DISCORD_CHANNEL_ID` | **`send_discord_message`** + bot script. |
| `PARADOX_EEG_PYTHON` / `EEG_PYTHON` | Override EEG subprocess executable. |
| `OLLAMA_KV_CACHE_TYPE` | `f16` · `q8_0` (default) · `q4_0` — KV cache VRAM vs quality tradeoff. |
| `OLLAMA_FLASH_ATTENTION` | `1` when flash attention enabled (default on in app settings). |
| `EMBED_QUANTIZE_BITS` | `0` off · `8` default TurboQuant-style · `4` / `1` more aggressive. |
| `OLLAMA_EMBED_ON_CPU` | Default **true** — keep embed model on CPU so GPU stays for chat. |

Full tables: `doc/reference/configuration.md` in the source repository.

</details>

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| **No reply** | Ollama up? Model pulled? Firewall on localhost? |
| **EEG job failed** | **`GET /health`** → `eeg_subprocess`; worker present; v0.3.2+ for known Plotly/orjson/encoding fixes per docs. |
| **GPU OOM / model evicted** | Check **`GET /health`** → `optimizations`. Try **`OLLAMA_KV_CACHE_TYPE=q8_0`** or **`q4_0`**; ensure **`OLLAMA_EMBED_ON_CPU=true`** so embeddings do not steal VRAM from chat. |
| **Discord silent** | Intents, channel id, bot invite. |
| **401 / license** | Tier, key file path, clock. **Fingerprint mismatch?** Re-run **`ParadoxMachineInfo.exe`** on the PC that actually runs Paradox and request a key for that ID. |

---

## How to report feedback

1. **Version** (0.3.4) + **installer date**.  
2. **Steps**, **expected**, **actual**.  
3. **Logs** — redact tokens, paths, **PHI**.  
4. Post only in the **designated private** Discord thread or **private** GitHub issue.

---

<div align="center">

**Paradox Solutions LLM** · *EEG Paradox Solutions* · GPL-3.0-or-later · [`LICENSE`](LICENSE) · [`NOTICE`](NOTICE)

*Private test build. Ships with care. Reads the manual twice.*

</div>
