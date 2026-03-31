# User Manual 02 — Installation

## Objective

Produce a reproducible installation of Paradox Solutions LLM on a Windows workstation.

## Procedure

### 1. Obtain the source tree

Place the project directory at a path without restrictive permissions (e.g. `Desktop\Super Bot`).

### 2. Create a virtual environment

```powershell
cd "path\to\Super Bot"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Shall:** Use this venv for all Python commands unless a containerized deployment replaces it.

### 3. Install the Python package

```powershell
pip install -e ".[discord]"
```

The `[discord]` extra installs `discord.py` for the optional bot script. Omit `[discord]` if Discord is unused.

### 4. Environment file

```powershell
copy .env.example .env
```

Edit `.env`. Minimum attention items:

| Variable | Action |
|----------|--------|
| `CHAT_MODEL` | Match a pulled Ollama model name. |
| `EMBED_MODEL` | Match a pulled embedding model. |
| `PORT` | Change if 8765 conflicts. |
| `CORS_ORIGINS` | Add origins if the web UI is not on localhost:3000. |

Full semantics: `reference/configuration.md`.

### 5. Install web dependencies

```powershell
cd web
npm install
```

### 6. Create data directories (automatic)

On first API start, `data/ingest_queue` is created. Chroma and vault paths are created when first written. The operator **may** pre-create:

```powershell
mkdir data\ingest_queue, data\vault\reflections -Force
```

## Post-install verification

1. Start Ollama (system tray or `ollama serve`).
2. From project root with venv active:

   ```powershell
   python -c "from hexnode.tools.registry import get_registry; print(len(get_registry().tool_specs()))"
   ```

   Expect a positive integer. The exact count changes with releases; see `reference/tools-catalog.md`.

3. Start API: `python run_server.py`
4. In another shell: `Invoke-WebRequest http://127.0.0.1:8765/health`

`ollama: true` in JSON indicates the inference layer is reachable.

For EEG operators, inspect `eeg_subprocess` in the same response: `bundled_worker` and `viz_script_found` should be favorable in a correct desktop install; from source, ensure the venv has `[eeg]` before running jobs.

## Failure modes

| Symptom | Likely cause |
|---------|----------------|
| `pip` conflicts | Global site-packages; recreate venv. |
| Chroma import errors | Incomplete install; rerun `pip install -e .` |
| Health `ollama: false` | Ollama not running or wrong `OLLAMA_BASE`. |

Next: `user/03-daily-operation.md`.
