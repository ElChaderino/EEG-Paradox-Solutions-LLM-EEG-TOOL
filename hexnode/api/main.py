# Copyright (C) 2026  EEG Paradox Solutions LLM contributors
#
# This file is part of Paradox Solutions LLM.
#
# Paradox Solutions LLM is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Paradox Solutions LLM is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Paradox Solutions LLM.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Form, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hexnode.agent.loop import run_agent
from hexnode.config import settings
from hexnode.ingest_watcher import ingest_watcher_loop
from hexnode.memory_store import MemoryStore
from hexnode.ollama_autostart import try_spawn_ollama_if_down
from hexnode.ollama_client import OllamaChatError, OllamaClient, apply_ollama_env
from hexnode.reflection import read_current_focus
from hexnode.tools.get_system_stats import _nvidia_smi_snapshot
from hexnode.tools.registry import get_registry

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hexnode")

_ollama: OllamaClient | None = None
_memory: MemoryStore | None = None
_watcher_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ollama, _memory, _watcher_task
    opt = apply_ollama_env()
    if opt:
        log.info("Ollama optimizations: %s", opt)
    _ollama = OllamaClient()
    if settings.paradox_ollama_autostart:
        if not await _ollama.ping():
            await try_spawn_ollama_if_down(_ollama)
    if await _ollama.ping():
        log.info("Ollama reachable at %s", settings.ollama_base)
    else:
        log.warning(
            "Ollama not reachable at %s — chat/embeddings will fail until it is running. "
            "Install from https://ollama.com or run: ollama serve. "
            "Autostart: PARADOX_OLLAMA_AUTOSTART=false to disable spawn attempts.",
            settings.ollama_base,
        )
    _memory = MemoryStore(_ollama)
    settings.ingest_queue.mkdir(parents=True, exist_ok=True)
    # EEG: only on real process start — never on routine /eeg/jobs polls
    _recover_orphaned_eeg_jobs_after_restart()
    _eeg_jobs.update(_read_eeg_jobs_from_disk())
    _watcher_task = asyncio.create_task(ingest_watcher_loop(_memory, _ollama))
    log.info("Paradox Solutions LLM online (port %s)", settings.port)
    yield
    if _watcher_task:
        _watcher_task.cancel()
        try:
            await _watcher_task
        except asyncio.CancelledError:
            pass
    if _ollama:
        await _ollama.aclose()


app = FastAPI(title="Paradox Solutions LLM", version="0.3.2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32000)
    interface: str = "api"


class MemoryQuery(BaseModel):
    query: str
    collection: str | None = None
    top_k: int | None = 8


@app.post("/system/ensure-ollama")
async def ensure_ollama() -> dict[str, Any]:
    """Try to start ``ollama serve`` if the daemon is down (local use)."""
    o = _ollama
    if not o:
        raise HTTPException(503, "Service not ready")
    ok = await try_spawn_ollama_if_down(o)
    return {"ollama": ok, "base": settings.ollama_base}


@app.get("/health")
async def health() -> dict[str, Any]:
    o = _ollama
    ok = await o.ping() if o else False
    kv_type = settings.ollama_kv_cache_type or "f16"
    try:
        from hexnode.eeg.norms_paths import norms_addon_status

        eeg_norms = norms_addon_status()
    except Exception:
        eeg_norms = {"installed": False, "root": None, "cuban_databases": None, "version": None, "id": None}

    import sys as _sys

    eeg_subprocess_ok = True
    eeg_subprocess_detail: dict[str, Any] = {}
    try:
        from hexnode.config import IS_FROZEN, python_for_eeg

        py = python_for_eeg()
        eeg_subprocess_detail["python"] = py
        eeg_subprocess_detail["frozen"] = IS_FROZEN
        eeg_subprocess_detail["bundled_worker"] = Path(py).name.lower() in (
            "paradox-eeg-worker.exe",
            "paradox-eeg-worker",
        )
        if IS_FROZEN and py == _sys.executable:
            eeg_subprocess_ok = False
            eeg_subprocess_detail["warning"] = "No system Python with MNE found — EEG jobs will fail"
        viz_ok = _resolve_viz_script() is not None
        eeg_subprocess_detail["viz_script_found"] = viz_ok
        if not viz_ok:
            eeg_subprocess_ok = False
            eeg_subprocess_detail["warning"] = (
                eeg_subprocess_detail.get("warning", "") +
                "; run_visualizations.py missing from bundle — rebuild needed"
            ).lstrip("; ")
    except Exception as exc:
        eeg_subprocess_ok = False
        eeg_subprocess_detail["error"] = str(exc)

    return {
        "status": "ok" if ok else "degraded",
        "ollama": ok,
        "chroma_path": str(settings.chroma_path),
        "eeg_norms_addon": eeg_norms,
        "eeg_subprocess": {
            "ok": eeg_subprocess_ok,
            **eeg_subprocess_detail,
        },
        "optimizations": {
            "flash_attention": settings.ollama_flash_attention,
            "kv_cache_type": kv_type,
            "kv_savings": {"q8_0": "~50%", "q4_0": "~75%"}.get(kv_type, "none"),
            "embed_quantize": f"int{settings.embed_quantize_bits}" if settings.embed_quantize_bits > 0 else "off",
        },
    }


@app.post("/agent")
async def agent(req: AgentRequest) -> dict[str, Any]:
    if not _memory or not _ollama:
        raise HTTPException(503, "Service not ready")
    try:
        return await run_agent(req.message, _memory, _ollama, interface=req.interface)
    except OllamaChatError as e:
        raise HTTPException(502, detail=e.detail) from e
    except httpx.ReadTimeout:
        raise HTTPException(
            504,
            detail="The LLM took too long to respond. This can happen when a model "
            "is loading for the first time or your system is under heavy load. "
            "Try again in a moment.",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, detail=f"Ollama HTTP error: {e}") from e


@app.post("/memory/query")
async def memory_query(req: MemoryQuery) -> dict[str, Any]:
    if not _memory:
        raise HTTPException(503, "Service not ready")
    hits = await _memory.query(req.collection, req.query, top_k=req.top_k)
    return {"hits": hits}


@app.get("/system/stats")
async def system_stats() -> dict[str, Any]:
    from hexnode.tools.get_system_stats import GetSystemStatsTool
    from hexnode.tools.base import ToolContext

    if not _memory or not _ollama:
        raise HTTPException(503, "Service not ready")
    ctx = ToolContext(memory=_memory, ollama=_ollama, settings=settings)
    res = await GetSystemStatsTool().run(ctx)
    if not res.ok:
        raise HTTPException(500, res.error or "stats failed")
    return {"stats": res.data, "gpu": _nvidia_smi_snapshot()}


@app.get("/focus")
async def focus() -> dict[str, str]:
    return {"current_focus": read_current_focus()}


@app.get("/tools")
async def tools_list() -> dict[str, Any]:
    return {"tools": get_registry().tool_specs()}


class IngestRequest(BaseModel):
    path: str


@app.post("/ingest/path")
async def ingest_path(req: IngestRequest) -> dict[str, Any]:
    from hexnode.tools.ingest_document import ingest_file_path

    if not _memory or not _ollama:
        raise HTTPException(503, "Service not ready")
    p = Path(req.path).expanduser()
    if not p.is_file():
        raise HTTPException(400, "not a file")
    ctx = ToolContext(memory=_memory, ollama=_ollama, settings=settings)
    try:
        n = await ingest_file_path(p, ctx, str(p))
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    return {"chunks": n, "path": str(p)}


# ── File upload + management ─────────────────────────────────────────────

_EEG_EXTS = frozenset({".edf", ".bdf", ".set", ".fif", ".vhdr", ".cnt"})
_INGEST_EXTS = frozenset({".pdf", ".txt", ".md", ".markdown", ".csv", ".json", ".yaml", ".yml", ".docx"})
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


def _route_file(filename: str) -> tuple[Path, str]:
    """Decide destination directory and category based on file extension."""
    ext = Path(filename).suffix.lower()
    if ext in _EEG_EXTS:
        return settings.eeg_workspace, "eeg"
    if ext in _INGEST_EXTS:
        return settings.ingest_queue, "document"
    return settings.vault_path / "uploads", "general"


@app.post("/files/upload")
async def upload_files(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    from hexnode.tools.ingest_document import ingest_file_path
    from hexnode.tools.base import ToolContext

    results = []
    for uf in files:
        if not uf.filename:
            continue

        dest_dir, category = _route_file(uf.filename)

        dest_dir.mkdir(parents=True, exist_ok=True)

        dest = dest_dir / uf.filename
        stem, suffix = dest.stem, dest.suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        data = await uf.read()
        if len(data) > _MAX_UPLOAD_BYTES:
            results.append({
                "filename": uf.filename,
                "ok": False,
                "error": f"File too large ({len(data) / 1024 / 1024:.0f} MB, max 500 MB)",
            })
            continue

        dest.write_bytes(data)

        entry: dict[str, Any] = {
            "filename": dest.name,
            "original_name": uf.filename,
            "category": category,
            "size": len(data),
            "path": str(dest),
            "ok": True,
        }

        if category in ("document", "eeg") and _memory and _ollama:
            try:
                ctx = ToolContext(memory=_memory, ollama=_ollama, settings=settings)
                chunks = await ingest_file_path(dest, ctx, dest.name)
                entry["ingested_chunks"] = chunks
            except Exception as e:
                entry["ingest_error"] = str(e)

        results.append(entry)

    return {"uploaded": results}


@app.get("/files")
async def list_files(category: str = Query("all")) -> dict[str, Any]:
    """List files across managed directories. Category: all, eeg, document, general."""
    dirs = {
        "eeg": settings.eeg_workspace,
        "document": settings.ingest_queue,
        "general": settings.vault_path / "uploads",
    }
    out: list[dict[str, Any]] = []
    cats = dirs.keys() if category == "all" else [category]
    for cat in cats:
        d = dirs.get(cat)
        if not d or not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            out.append({
                "name": f.name,
                "category": cat,
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
                "path": str(f),
            })
    return {"files": out}


@app.delete("/files/{category}/{filename}")
async def delete_file(category: str, filename: str) -> dict[str, str]:
    dirs = {
        "eeg": settings.eeg_workspace,
        "document": settings.ingest_queue,
        "general": settings.vault_path / "uploads",
    }
    d = dirs.get(category)
    if not d:
        raise HTTPException(400, f"Unknown category: {category}")
    target = d / filename
    if not target.is_file():
        raise HTTPException(404, f"File not found: {filename}")
    target.unlink()
    return {"status": "deleted", "filename": filename}


# ── EEG outputs (analysis results: HTML, PNG, JSON) ─────────────────────


def _output_dir() -> Path:
    return settings.eeg_workspace / "output"


@app.get("/eeg/outputs")
async def list_eeg_outputs() -> dict[str, Any]:
    out_dir = _output_dir()
    if not out_dir.is_dir():
        return {"files": []}
    items: list[dict[str, Any]] = []
    for f in sorted(out_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext in (".html", ".htm"):
            ftype = "html"
        elif ext in (".png", ".jpg", ".jpeg", ".svg"):
            ftype = "image"
        elif ext == ".json":
            ftype = "json"
        elif ext in (".fif", ".edf", ".bdf"):
            ftype = "data"
        else:
            ftype = "other"
        items.append({
            "name": f.name,
            "type": ftype,
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        })
    return {"files": items}


@app.get("/eeg/outputs/{filename:path}")
async def get_eeg_output(filename: str):
    from fastapi.responses import FileResponse

    out_dir = _output_dir()
    target = (out_dir / filename).resolve()
    if not target.is_relative_to(out_dir.resolve()):
        raise HTTPException(403, "Access denied")
    if not target.is_file():
        raise HTTPException(404, f"Not found: {filename}")
    ext = target.suffix.lower()
    media_types = {
        ".html": "text/html", ".htm": "text/html",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".json": "application/json",
        ".fif": "application/octet-stream",
    }
    return FileResponse(target, media_type=media_types.get(ext, "application/octet-stream"))


class EegRunPythonRequest(BaseModel):
    script: str = Field(..., min_length=1, max_length=500_000)


@app.post("/eeg/run-python")
async def eeg_run_python(req: EegRunPythonRequest) -> dict[str, Any]:
    """Run MNE/analysis Python in ``eeg_workspace`` (same engine as ``run_python_analysis`` tool)."""
    from hexnode.tools.run_python_analysis import execute_python_analysis_script

    return execute_python_analysis_script(req.script)


@app.get("/eeg/script-templates")
async def eeg_script_templates_list() -> dict[str, Any]:
    """List bundled ``data/eeg_scripts/*.py`` with first line of docstring as summary."""
    from hexnode.tools.list_eeg_scripts import get_eeg_scripts_directory

    d = get_eeg_scripts_directory()
    if not d.is_dir():
        return {"templates": []}
    rows: list[dict[str, str]] = []
    for f in sorted(d.glob("*.py")):
        doc = ""
        text = f.read_text(encoding="utf-8", errors="replace")
        if text.startswith('"""'):
            end = text.find('"""', 3)
            if end > 3:
                doc = text[3:end].strip().split("\n")[0]
        rows.append({"name": f.name, "summary": doc})
    return {"templates": rows}


@app.get("/eeg/script-templates/{name}")
async def eeg_script_templates_get(name: str) -> dict[str, Any]:
    """Return full source for one template (basename ``*.py`` only)."""
    from hexnode.tools.list_eeg_scripts import get_eeg_scripts_directory

    safe = Path(name).name
    if safe != name or ".." in name or not safe.endswith(".py"):
        raise HTTPException(400, "Invalid template name")
    p = get_eeg_scripts_directory() / safe
    if not p.is_file():
        raise HTTPException(404, f"Unknown template: {safe}")
    return {"name": safe, "content": p.read_text(encoding="utf-8")}


@app.post("/workspace/open")
async def open_workspace() -> dict[str, str]:
    import subprocess, sys

    ws = settings.eeg_workspace
    ws.mkdir(parents=True, exist_ok=True)
    out = ws / "output"
    out.mkdir(parents=True, exist_ok=True)
    target = str(out) if out.is_dir() else str(ws)
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", target])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except Exception as e:
        raise HTTPException(500, f"Could not open folder: {e}") from e
    return {"status": "opened", "path": target}


# ── EEG processing jobs (upload → auto-pipeline → results) ──────────────
# Job state persists to disk (_job.json in each job dir) so it survives
# server reloads. In-memory dict is a cache; disk is the source of truth.

_eeg_jobs: dict[str, dict[str, Any]] = {}
_JOB_META = "_job.json"


def _save_job(job: dict[str, Any], job_dir: Path) -> None:
    """Write job state to disk."""
    import json as _json
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / _JOB_META).write_text(_json.dumps(job, default=str), encoding="utf-8")
    except Exception as exc:
        logging.getLogger("hexnode").warning("Failed to persist job %s: %s", job.get("id"), exc)


def _load_job(job_dir: Path) -> dict[str, Any] | None:
    """Read job state from disk."""
    import json as _json
    meta = job_dir / _JOB_META
    if not meta.is_file():
        return None
    try:
        return _json.loads(meta.read_text("utf-8"))
    except Exception:
        return None


def _read_eeg_jobs_from_disk() -> dict[str, dict[str, Any]]:
    """Load all job metadata from disk without mutating in-progress jobs."""
    out = _output_dir()
    if not out.is_dir():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for d in out.iterdir():
        if not d.is_dir():
            continue
        job = _load_job(d)
        if not job or "id" not in job:
            continue
        result[job["id"]] = job
    return result


def _recover_orphaned_eeg_jobs_after_restart() -> None:
    """Run once at process startup.

    Jobs left ``running``/``queued`` on disk belonged to a dead process; mark them
    finished so the UI does not spin forever. **Must not** run on routine
    ``GET /eeg/jobs`` polls — that falsely killed active jobs while the worker
    was still running (every poll looked like a 'server restart').
    """
    out = _output_dir()
    if not out.is_dir():
        return
    log = logging.getLogger("hexnode")
    for d in out.iterdir():
        if not d.is_dir():
            continue
        job = _load_job(d)
        if not job or "id" not in job:
            continue
        if job.get("status") not in ("running", "queued"):
            continue
        output_files = sorted(
            f.name for f in d.iterdir()
            if f.is_file()
            and not f.name.startswith("_")
            and not f.name.startswith(".")
        )
        job["output_files"] = output_files
        job["status"] = "complete_with_warnings" if output_files else "error"
        job["error"] = job.get("error") or "Server restarted during processing"
        job["progress"] = 100
        msgs = job.setdefault("messages", [])
        msgs.append(
            "— Job interrupted: API process restarted or stopped before this run finished. "
            "Delete this job and re-upload the file for a full analysis."
        )
        if len(msgs) > 100:
            job["messages"] = msgs[-60:]
        _save_job(job, d)
        log.warning(
            "Recovered orphaned EEG job %s (%s) -> %s (%d output files)",
            job.get("id"),
            job.get("filename"),
            job.get("status"),
            len(output_files),
        )


def _get_job(job_id: str) -> dict[str, Any] | None:
    """Get from cache or disk."""
    if job_id in _eeg_jobs:
        return _eeg_jobs[job_id]
    job_dir = _output_dir() / job_id
    job = _load_job(job_dir)
    if job:
        _eeg_jobs[job_id] = job
    return job


def _run_eeg_job(job_id: str, edf_path: Path, job_dir: Path) -> None:
    """Background worker: runs the full pipeline + clinical scripts on an EDF."""
    import json
    import os
    import subprocess
    import sys

    from hexnode.config import eeg_subprocess_pythonpath, python_for_eeg

    job = _eeg_jobs[job_id]

    def _progress(msg: str, pct: int = -1) -> None:
        job["messages"].append(msg)
        if len(job["messages"]) > 100:
            job["messages"] = job["messages"][-60:]
        if pct >= 0:
            job["progress"] = pct
        job["status"] = "running"
        _save_job(job, job_dir)

    try:
        from hexnode.eeg.pipeline import PipelineConfig, generate_pipeline_script

        stem = edf_path.stem
        job_dir.mkdir(parents=True, exist_ok=True)

        _progress(f"Starting pipeline for {edf_path.name}", 5)

        cfg = PipelineConfig(
            input_file=str(edf_path),
            output_prefix=stem,
            output_dir=str(job_dir),
            condition=job.get("condition", "EC"),
            output_mode=job.get("output_mode", "standard"),
            remontage_ref=job.get("remontage_ref", ""),
        )
        script = generate_pipeline_script(cfg)
        script_path = job_dir / "_pipeline.py"
        script_path.write_text(script, encoding="utf-8")

        _progress("Running 24-step preprocessing + analysis pipeline...", 10)
        py = python_for_eeg()
        creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        proc = subprocess.run(
            [py, str(script_path)],
            capture_output=True, text=True,
            timeout=max(120, settings.python_analysis_timeout * 3),
            cwd=str(settings.eeg_workspace),
            creationflags=creation_flags,
            env={
                **os.environ,
                "MPLBACKEND": "Agg",
                "PYTHONPATH": eeg_subprocess_pythonpath(),
            },
        )

        pipeline_ok = proc.returncode == 0
        if not pipeline_ok:
            stderr_tail = (proc.stderr or "")[-500:]
            _progress(f"Pipeline error: {stderr_tail}", 50)
            job["error"] = f"Pipeline exited with code {proc.returncode}"
            combined_err = (proc.stderr or "") + "\n" + (proc.stdout or "")
            if any(
                s in combined_err
                for s in ("No module named 'mne'", "No module named 'matplotlib'", "No module named 'scipy'")
            ):
                _progress(
                    "Tip: the packaged app does not bundle MNE. Install a system Python with "
                    "`pip install mne matplotlib scipy` (or your project `[eeg]` extra), or set "
                    "PARADOX_EEG_PYTHON to that python.exe — see User Manual EEG troubleshooting.",
                    52,
                )
        else:
            _progress("Pipeline complete, running clinical analyses...", 60)

        _progress("Running Clinical Q Assessment (Swingle protocol)...", 65)
        _run_clinical_script(
            "clinical_q_assessment.py", edf_path, job_dir, stem, _progress
        )

        _progress("Running Band Power Analysis...", 80)
        _run_clinical_script(
            "band_power_analysis.py", edf_path, job_dir, stem, _progress
        )

        _progress("Generating interactive visualizations...", 85)
        _run_viz_subprocess(edf_path, job_dir, stem, job.get("condition", "EC"), _progress)

        try:
            script_path.unlink()
        except OSError:
            pass

        output_files = sorted(
            f.name for f in job_dir.iterdir()
            if f.is_file()
            and not f.name.startswith("_")
            and not f.name.startswith(".")
        )
        metrics_path = job_dir / f"{stem}_metrics.json"
        metrics = {}
        if metrics_path.is_file():
            try:
                metrics = json.loads(metrics_path.read_text("utf-8"))
            except Exception:
                pass

        job["output_files"] = output_files
        job["metrics"] = metrics
        if pipeline_ok:
            job["status"] = "complete"
        else:
            job["status"] = "complete_with_warnings" if output_files else "error"
        job["progress"] = 100
        job["messages"].append(f"Done — {len(output_files)} output files generated")
        _save_job(job, job_dir)

    except subprocess.TimeoutExpired:
        job["status"] = "error"
        job["error"] = "Pipeline timed out"
        _save_job(job, job_dir)
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)[:500]
        _save_job(job, job_dir)


def _resolve_viz_script() -> Path | None:
    """Locate ``run_visualizations.py`` on disk (source, bundle, or .pyc fallback)."""
    from hexnode.config import _bundle_dir

    candidates = [
        Path(__file__).resolve().parent.parent / "eeg" / "viz" / "run_visualizations.py",
        _bundle_dir() / "hexnode" / "eeg" / "viz" / "run_visualizations.py",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _run_viz_subprocess(
    edf_path: Path, job_dir: Path, stem: str, condition: str,
    progress_fn: Any,
) -> None:
    """Run the visualization orchestrator as a subprocess so it uses system Python
    with MNE/scipy/matplotlib/plotly (which are excluded from the PyInstaller bundle)."""
    import json as _json
    import os
    import subprocess

    from hexnode.config import IS_FROZEN, eeg_subprocess_pythonpath, python_for_eeg

    viz_script = _resolve_viz_script()

    if viz_script is None:
        msg = (
            "WARNING: run_visualizations.py not found on disk — "
            "all interactive visualizations (topomaps, 3D scalp, spectra, microstates) will be skipped. "
        )
        if IS_FROZEN:
            msg += (
                "This usually means the PyInstaller build did not bundle hexnode/eeg/ as data files. "
                "Check paradox-api.spec: ('hexnode/eeg', 'hexnode/eeg') must be in added_datas."
            )
        progress_fn(msg)
        logging.getLogger("hexnode").error(msg)
        return

    try:
        py = python_for_eeg()
        creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        proc = subprocess.run(
            [py, str(viz_script), str(edf_path), str(job_dir), stem, condition],
            capture_output=True, text=True,
            timeout=1200,
            cwd=str(settings.eeg_workspace),
            creationflags=creation_flags,
            env={
                **os.environ,
                "MPLBACKEND": "Agg",
                "PYTHONPATH": eeg_subprocess_pythonpath(),
            },
        )
        if proc.returncode != 0:
            progress_fn(f"  Visualization had errors: {(proc.stderr or '')[-400:]}")
        else:
            for line in (proc.stdout or "").splitlines():
                if line.strip().startswith("VIZ_HINT:"):
                    progress_fn(f"  {line.split(':', 1)[1].strip()}")
            manifest = job_dir / "_viz_manifest.json"
            if manifest.is_file():
                try:
                    info = _json.loads(manifest.read_text("utf-8"))
                    count = info.get("count", 0)
                    progress_fn(f"  Visualizations complete — {count} files generated", 95)
                    manifest.unlink(missing_ok=True)
                except Exception:
                    progress_fn("  Visualizations complete", 95)
            else:
                progress_fn("  Visualizations complete (no manifest)", 95)
    except subprocess.TimeoutExpired:
        progress_fn("  Visualization timed out (20 min limit)")
    except Exception as e:
        progress_fn(f"  Visualization failed: {e}")


def _run_clinical_script(
    script_name: str, edf_path: Path, job_dir: Path, stem: str,
    progress_fn: Any,
) -> None:
    """Run a pre-made clinical analysis script with INPUT_FILE and OUTPUT_DIR patched."""
    import os
    import subprocess

    from hexnode.config import eeg_subprocess_pythonpath, python_for_eeg

    from hexnode.config import _bundle_dir

    scripts_dir = Path(__file__).resolve().parent.parent.parent / "data" / "eeg_scripts"
    if not scripts_dir.is_dir():
        scripts_dir = _bundle_dir() / "data" / "eeg_scripts"

    src = scripts_dir / script_name
    if not src.is_file():
        progress_fn(
            f"  WARNING: {script_name} not found in {scripts_dir} — analysis skipped. "
            "Check that data/eeg_scripts is bundled in paradox-api.spec."
        )
        logging.getLogger("hexnode").error("Clinical script %s not found under %s", script_name, scripts_dir)
        return

    code = src.read_text("utf-8")
    code = code.replace('INPUT_FILE = "recording.edf"', f'INPUT_FILE = r"{edf_path}"')
    code = code.replace('OUTPUT_DIR = "output"', f'OUTPUT_DIR = r"{job_dir}"')

    tmp = job_dir / f"_{script_name}"
    tmp.write_text(code, encoding="utf-8")
    try:
        py = python_for_eeg()
        creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        proc = subprocess.run(
            [py, str(tmp)],
            capture_output=True, text=True,
            timeout=max(180, settings.python_analysis_timeout),
            cwd=str(settings.eeg_workspace),
            creationflags=creation_flags,
            env={
                **os.environ,
                "MPLBACKEND": "Agg",
                "PYTHONPATH": eeg_subprocess_pythonpath(),
            },
        )
        if proc.returncode != 0:
            progress_fn(f"  {script_name} had errors: {(proc.stderr or '')[-300:]}")
        else:
            progress_fn(f"  {script_name} completed")
    except Exception as e:
        progress_fn(f"  {script_name} failed: {e}")
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


@app.post("/eeg/process")
async def eeg_process(
    file: UploadFile = File(...),
    condition: str = Form("EC"),
    output_mode: str = Form("standard"),
    remontage_ref: str = Form(""),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(400, "No file provided")
    ext = Path(file.filename).suffix.lower()
    if ext not in _EEG_EXTS:
        raise HTTPException(400, f"Unsupported format: {ext}")

    ws = settings.eeg_workspace
    ws.mkdir(parents=True, exist_ok=True)

    dest = ws / file.filename
    stem, suffix = dest.stem, dest.suffix
    counter = 1
    while dest.exists():
        dest = ws / f"{stem}_{counter}{suffix}"
        counter += 1

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large ({len(data) / 1024 / 1024:.0f} MB)")
    dest.write_bytes(data)

    job_id = uuid.uuid4().hex[:12]
    job_dir = _output_dir() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    job: dict[str, Any] = {
        "id": job_id,
        "filename": dest.name,
        "status": "queued",
        "progress": 0,
        "messages": [],
        "started": datetime.now(timezone.utc).isoformat(),
        "output_files": [],
        "metrics": {},
        "error": None,
        "condition": condition,
        "output_mode": output_mode,
        "remontage_ref": remontage_ref,
    }
    _eeg_jobs[job_id] = job
    _save_job(job, job_dir)

    thread = threading.Thread(
        target=_run_eeg_job, args=(job_id, dest, job_dir), daemon=True
    )
    thread.start()

    return {"job_id": job_id, "status": "queued", "filename": dest.name}


@app.get("/eeg/jobs")
async def list_eeg_jobs() -> dict[str, Any]:
    all_jobs = _read_eeg_jobs_from_disk()
    for jid, disk_job in all_jobs.items():
        if jid in _eeg_jobs and _eeg_jobs[jid].get("status") in ("running", "queued"):
            # Worker thread mutates this dict; disk may lag one save behind
            continue
        _eeg_jobs[jid] = disk_job
    jobs = sorted(_eeg_jobs.values(), key=lambda j: j.get("started", ""), reverse=True)
    return {"jobs": [
        {
            "id": j["id"],
            "filename": j.get("filename", ""),
            "status": j.get("status", "unknown"),
            "progress": j.get("progress", 0),
            "started": j.get("started", ""),
            "output_count": len(j.get("output_files", [])),
            "error": j.get("error"),
            "condition": j.get("condition"),
            "output_mode": j.get("output_mode"),
        }
        for j in jobs
    ]}


@app.post("/eeg/jobs/{job_id}/delete")
async def delete_eeg_job(job_id: str) -> dict[str, str]:
    import shutil

    job_dir = _output_dir() / job_id
    if not job_dir.is_dir():
        _eeg_jobs.pop(job_id, None)
        raise HTTPException(404, "Job not found")
    shutil.rmtree(job_dir, ignore_errors=True)
    _eeg_jobs.pop(job_id, None)
    return {"status": "deleted", "id": job_id}


@app.get("/eeg/jobs/{job_id}/files/{filename:path}")
async def get_eeg_job_file(job_id: str, filename: str):
    from fastapi.responses import FileResponse

    job_dir = (_output_dir() / job_id).resolve()
    if not job_dir.is_dir():
        raise HTTPException(404, "Job not found")
    target = (job_dir / filename).resolve()
    if not target.is_relative_to(job_dir):
        raise HTTPException(403, "Access denied")
    if not target.is_file():
        raise HTTPException(404, f"Not found: {filename}")
    ext = target.suffix.lower()
    media_types = {
        ".html": "text/html", ".htm": "text/html",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml", ".json": "application/json",
        ".txt": "text/plain", ".fif": "application/octet-stream",
    }
    headers: dict[str, str] = {}
    if ext in (".html", ".htm"):
        headers["X-Frame-Options"] = "ALLOWALL"
        headers["Content-Security-Policy"] = "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:"
    return FileResponse(
        target,
        media_type=media_types.get(ext, "application/octet-stream"),
        headers=headers,
    )


@app.get("/eeg/jobs/{job_id}")
async def get_eeg_job(job_id: str) -> dict[str, Any]:
    job = _get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")

    if job.get("status") in ("complete", "complete_with_warnings"):
        job_dir = _output_dir() / job_id
        if job_dir.is_dir():
            fresh = sorted(
                f.name for f in job_dir.iterdir()
                if f.is_file()
                and not f.name.startswith("_")
                and not f.name.startswith(".")
            )
            if len(fresh) > len(job.get("output_files") or []):
                job["output_files"] = fresh
                _save_job(job, job_dir)

    return {
        "id": job["id"],
        "filename": job.get("filename", ""),
        "status": job.get("status", "unknown"),
        "progress": job.get("progress", 0),
        "messages": (job.get("messages") or [])[-20:],
        "started": job.get("started", ""),
        "output_files": job.get("output_files", []),
        "metrics": job.get("metrics", {}),
        "error": job.get("error"),
    }


# ── Static frontend (must be last) ──────────────────────────────────────

from hexnode.config import IS_FROZEN, _bundle_dir

_STATIC_DIR = _bundle_dir() / "web" / "out"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static-frontend")


def create_app() -> FastAPI:
    return app
