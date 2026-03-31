# Paradox Solutions LLM — Documentation Index

This folder is the authoritative documentation set for the Super Bot / Paradox Solutions LLM codebase. Documents are grouped by audience and by architectural layer.

**New here?** Open **[START-HERE](START-HERE.md)** and pick *end user*, *operator*, *developer*, or *integrator*. For a single architectural pass, read **[00-overview](00-overview.md)** next.

## Conventions

- **Shall / shall not** indicate normative requirements for correct operation.
- **May** indicates optional capability.
- **Layer** refers to a level of the system stack (host, process, service, API, agent, persistence, presentation). Each layer has explicit inputs, outputs, and failure modes.

## Document map

| ID | Title | Audience |
|----|--------|----------|
| [START-HERE](START-HERE.md) | Choose your doc path by role | All |
| [00-overview](00-overview.md) | System overview and terminology | All |
| **User** | | |
| [user/01-prerequisites](user/01-prerequisites.md) | Hardware, OS, and external services | Operator |
| [user/02-installation](user/02-installation.md) | Install and first configuration | Operator |
| [user/03-daily-operation](user/03-daily-operation.md) | Running the API, UI, and jobs | Operator |
| [user/04-web-console](user/04-web-console.md) | Next.js console (chat, panels) | End user |
| [user/05-memory-ingest-reflection](user/05-memory-ingest-reflection.md) | Memory, queue, vault, reflection | Operator / power user |
| [user/06-integrations](user/06-integrations.md) | SearXNG, Skye, Discord | Operator |
| [user/07-troubleshooting](user/07-troubleshooting.md) | Fault isolation procedures (includes EEG jobs §8) | Operator |
| [user/08-desktop-tauri](user/08-desktop-tauri.md) | Native Windows shell (Tauri) | End user / operator |
| [user/09-eeg-research](user/09-eeg-research.md) | EEG uploads, jobs, dashboards, clinical outputs | End user / operator |
| [user/10-eeg-norms-addon](user/10-eeg-norms-addon.md) | Optional Cuban norms DLC, UI font size | Operator |
| **Developer** | | |
| [developer/01-repository-structure](developer/01-repository-structure.md) | Modules and entry points | Engineer |
| [developer/02-dev-environment](developer/02-dev-environment.md) | Virtualenv, dependencies, running locally | Engineer |
| [developer/03-architecture](developer/03-architecture.md) | Control flow and component coupling | Engineer |
| [developer/04-tools-and-registry](developer/04-tools-and-registry.md) | Adding and testing tools | Engineer |
| [developer/05-agent-and-prompts](developer/05-agent-and-prompts.md) | Agent loop and prompt contracts | Engineer |
| [developer/06-frontend](developer/06-frontend.md) | Web client and API coupling | Engineer |
| [developer/07-symbolic-rules](developer/07-symbolic-rules.md) | Neuro-symbolic YAML hints | Engineer |
| **Reference** | | |
| [reference/configuration](reference/configuration.md) | Environment variables and defaults | All technical |
| [reference/rest-api](reference/rest-api.md) | HTTP routes and payloads | Integrator |
| [reference/tools-catalog](reference/tools-catalog.md) | Tool names, parameters, behavior | All technical |
| [reference/memory-and-chroma](reference/memory-and-chroma.md) | Collections, metadata, scoring | Engineer |
| [reference/agent-contract](reference/agent-contract.md) | JSON schema and escalation rules | Engineer |
| [reference/security](reference/security.md) | Threat model and controls | Engineer / security |
| [reference/operations](reference/operations.md) | Scheduling, backup, logging | Operator |
| [glossary](glossary.md) | Definitions | All |
| **Interactive** | | |
| [technical-reference.html](technical-reference.html) | Full interactive technical reference (open in browser) | All |
| **Appendix** | | |
| [appendix/layer-matrix](appendix/layer-matrix.md) | Full L0–L16 stack matrix | Architect / lead |
| [appendix/documentation-style](appendix/documentation-style.md) | How to edit these docs | Contributors |

## What's New (v0.3.2)

**Patch release — desktop EEG interactive HTML reliability**

- **Not a license issue:** Missing interactive traceroute, Granger Plotly HTML, 3D scalp, LORETA, Coben overlays, microstate explorer, or trace viewer on the **installed** app was traced to the **frozen EEG worker + Plotly**, not to feature flags. `/eeg/process` only requires the broad **`eeg`** license feature; NetOps visualizations are not separately keyed in the pipeline.
- **Worker bundles real `orjson`:** Plotly 6.x uses `orjson` when calling `fig.to_html()`. The API’s `_internal/orjson/` layout could resolve as an empty namespace when prepended to `sys.path`, breaking **all** Plotly HTML exports from the worker. v0.3.2 ships **`orjson` inside `paradox-eeg-worker`** via `paradox-eeg-worker.spec`.
- **Windows console encoding:** `eeg_subprocess_launcher.py` forces UTF-8 I/O so pipeline `print()` statements with Unicode (e.g. trace viewer) do not raise **`UnicodeEncodeError`** on cp1252 consoles.
- **Microstate contract:** `run_visualizations._compute_microstates()` now returns **`ch_names`**, **`maps` as a list of state vectors**, **`labels_downsampled`**, **`gfp_downsampled`**, and related fields expected by `microstate_visualizer.py`.
- **Optional anatomy deps:** Spec includes hooks for **nibabel** / **nilearn**; full surface-quality LORETA may still fall back when those packages are not fully collected by PyInstaller (sphere / voxel paths remain).

See **`CHANGELOG.md`** for the full list. Operators: after upgrading, confirm `GET /health` → `eeg_subprocess.bundled_worker` and run a fresh EEG job. Troubleshooting detail: [user/07-troubleshooting](user/07-troubleshooting.md) §8, [user/09-eeg-research](user/09-eeg-research.md).

### Baseline (v0.3.1 and earlier)

Desktop (Tauri + PyInstaller), bundled EEG worker, GPU opts, licensing, file management, full EEG + NetOps stack, `/health` EEG fields, agent **504** on Ollama timeout, and `VERSION` / `CHANGELOG` / `bump_version.ps1` workflow are described in **`CHANGELOG.md`** and [user/09-eeg-research](user/09-eeg-research.md).

## Revision

Documentation shall be updated when any of the following change: default ports, environment variable names, public HTTP contracts, tool registry behavior, memory metadata fields, licensing models, optimization settings, desktop packaging configuration, EEG worker layout, or the root **`VERSION`** / release process. The repository `README.md` remains a short entry point; this folder carries the full specification.
