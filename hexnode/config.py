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

import os
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

IS_FROZEN = getattr(sys, "frozen", False)

_system_python: str | None = None
_eeg_plotly_checked: str | None = None


def _warn_if_no_plotly(exe: str) -> None:
    """Log once if the frozen app's EEG subprocess Python lacks plotly (NetOps / traceroute HTML)."""
    global _eeg_plotly_checked
    if not IS_FROZEN or _eeg_plotly_checked == exe:
        return
    import logging
    import subprocess

    _eeg_plotly_checked = exe
    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        r = subprocess.run(
            [exe, "-c", "import plotly.graph_objects"],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=creationflags,
        )
        if r.returncode != 0:
            logging.getLogger("hexnode.config").warning(
                "EEG Python has MNE but not plotly (%s). NetOps dashboards and interactive "
                "traceroute HTML need: pip install plotly",
                exe,
            )
    except Exception:
        pass


def _probe_eeg_worker(worker: Path) -> bool:
    """True if ``paradox-eeg-worker`` was built with MNE/plotly/scipy (see ``--eeg-probe``)."""
    import subprocess

    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        proc = subprocess.run(
            [str(worker), "--eeg-probe"],
            capture_output=True,
            text=True,
            timeout=90,
            creationflags=creationflags,
        )
        return proc.returncode == 0 and "ok" in (proc.stdout or "")
    except Exception:
        return False


def _bundled_eeg_worker_exe() -> Path | None:
    """Next to the main frozen exe: ``eeg-worker/paradox-eeg-worker.exe`` (Windows) or same name without ``.exe``."""
    if not IS_FROZEN:
        return None
    base = Path(sys.executable).resolve().parent
    names = [
        ("eeg-worker", "paradox-eeg-worker.exe"),
        ("paradox-eeg-worker.exe",),
    ]
    if sys.platform != "win32":
        names.extend(
            [
                ("eeg-worker", "paradox-eeg-worker"),
                ("paradox-eeg-worker",),
            ]
        )
    for parts in names:
        p = base.joinpath(*parts)
        if p.is_file():
            return p
    return None


def _resolve_eeg_executable_candidate(c: Path) -> str | None:
    """Bundled worker (probe) or a real Python with MNE."""
    if not c.is_file():
        return None
    n = c.name.lower()
    if n == "paradox-eeg-worker.exe" or n == "paradox-eeg-worker":
        if _probe_eeg_worker(c):
            return str(c.resolve())
        return None
    return _probe_python_has_mne([str(c)])


def eeg_subprocess_pythonpath() -> str:
    """Directory on PYTHONPATH so ``import hexnode`` works in EEG child processes (viz, etc.).

    Frozen: PyInstaller ``_MEIPASS`` (contains the ``hexnode`` package). Dev: repo root.
    Prepends to any existing ``PYTHONPATH``.
    """
    root = str(_bundle_dir()) if IS_FROZEN else str(Path(__file__).resolve().parent.parent)
    extra = (os.environ.get("PYTHONPATH") or "").strip()
    if not extra:
        return root
    return f"{root}{os.pathsep}{extra}"


def _probe_python_has_mne(argv: list[str]) -> str | None:
    """If ``argv`` can run ``python -c 'import mne; print(sys.executable)'``, return that exe path."""
    import subprocess

    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        proc = subprocess.run(
            [*argv, "-c", "import mne, sys; print(sys.executable)"],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=creationflags,
        )
        if proc.returncode != 0:
            return None
        line = (proc.stdout or "").strip().splitlines()
        if not line:
            return None
        resolved = line[-1].strip().strip('"')
        if resolved and Path(resolved).is_file():
            return resolved
    except Exception:
        return None
    return None


def python_for_eeg() -> str:
    """Return an executable suitable for EEG subprocesses (MNE, plotly, scipy, …).

    Development: ``sys.executable`` (venv).

    Frozen: prefer ``eeg-worker/paradox-eeg-worker.exe`` (PyInstaller worker built from
    ``paradox-eeg-worker.spec``), else a **system** Python with MNE (``py -3``, PATH).

    Override: ``PARADOX_EEG_PYTHON`` / ``EEG_PYTHON`` — path to ``python.exe`` or to
    ``paradox-eeg-worker.exe``.
    """
    import logging

    log = logging.getLogger("hexnode.config")

    global _system_python
    if _system_python is not None:
        return _system_python

    import os
    import shutil

    for env_key in ("PARADOX_EEG_PYTHON", "EEG_PYTHON"):
        raw = (os.environ.get(env_key) or "").strip().strip('"')
        if not raw:
            continue
        p = Path(raw)
        if p.is_file():
            candidates = [p]
        else:
            candidates = [
                p / "python.exe",
                p / "Scripts" / "python.exe",
                p / "paradox-eeg-worker.exe",
                p / "paradox-eeg-worker",
                p / "eeg-worker" / "paradox-eeg-worker.exe",
                p / "eeg-worker" / "paradox-eeg-worker",
            ]
        for c in candidates:
            got = _resolve_eeg_executable_candidate(c)
            if got:
                _system_python = got
                log.info("EEG subprocess (from %s): %s", env_key, got)
                if Path(got).name.lower() not in ("paradox-eeg-worker.exe", "paradox-eeg-worker"):
                    _warn_if_no_plotly(got)
                return _system_python

    if not IS_FROZEN:
        _system_python = sys.executable
        return _system_python

    bundled = _bundled_eeg_worker_exe()
    if bundled is not None:
        if _probe_eeg_worker(bundled):
            _system_python = str(bundled.resolve())
            log.info("EEG subprocess (bundled worker): %s", _system_python)
            return _system_python
        log.warning("Bundled EEG worker failed --eeg-probe: %s (falling back to system Python)", bundled)

    # Windows: Python Launcher is often the only shims on PATH; resolve to real python.exe.
    py_launcher = shutil.which("py")
    if py_launcher and sys.platform == "win32":
        got = _probe_python_has_mne([py_launcher, "-3"])
        if got:
            _system_python = got
            log.info("EEG Python (py -3 launcher): %s", got)
            _warn_if_no_plotly(got)
            return _system_python

    for candidate in ("python", "python3"):
        exe = shutil.which(candidate)
        if not exe:
            continue
        got = _probe_python_has_mne([exe])
        if got:
            _system_python = got
            log.info("EEG Python (PATH %s): %s", candidate, got)
            _warn_if_no_plotly(got)
            return _system_python

    # Last resort: bundled exe cannot import mne; still return it so stderr shows ImportError.
    _system_python = sys.executable
    log.warning(
        "No system Python with MNE found — EEG subprocesses will fail. "
        "Install MNE in a system Python or set PARADOX_EEG_PYTHON."
    )
    return _system_python


def _default_data_dir() -> Path:
    if IS_FROZEN:
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ParadoxSolutionsLLM" / "data"
    return Path(__file__).resolve().parent.parent / "data"


def _bundle_dir() -> Path:
    """Root of the PyInstaller _internal dir (data files), or repo root in dev."""
    if IS_FROZEN:
        return Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
    return Path(__file__).resolve().parent.parent


def _env_file_path() -> str:
    if IS_FROZEN:
        return str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ParadoxSolutionsLLM" / ".env")
    return ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file_path(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8765
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8765,http://127.0.0.1:8765,tauri://localhost,http://tauri.localhost,https://tauri.localhost"

    ollama_base: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen3:8b"
    fast_model: str = ""  # Optional smaller model for classification/simple tasks (e.g. phi4-mini). Empty = use chat_model.
    embed_model: str = "nomic-embed-text"
    # Embeddings: num_ctx should not exceed the model's trained context (nomic-embed-text = 2048).
    # 0 = omit options.num_ctx (Ollama default; can trigger warnings on BERT embedders).
    ollama_embed_num_ctx: int = 2048
    # Run embedding model on CPU (uses system RAM) so a loaded chat model is not evicted from a small GPU.
    ollama_embed_on_cpu: bool = True
    # Bound VRAM / KV cache for local models (0 = omit; let Ollama default).
    ollama_chat_num_ctx: int = 16384
    ollama_chat_num_predict: int = 4096

    # GPU/VRAM optimizations (applied via Ollama env vars and API options)
    ollama_flash_attention: bool = True
    ollama_kv_cache_type: str = "q8_0"  # "f16" (default/off), "q8_0" (50% savings), "q4_0" (75% savings)
    # If Ollama is not reachable when the API starts, try ``ollama serve`` (browser / python run_server.py).
    # Disable: PARADOX_OLLAMA_AUTOSTART=false
    paradox_ollama_autostart: bool = True

    # Embedding quantization for ChromaDB storage compression
    embed_quantize_bits: int = 8  # 0 = off (full float32), 8 = int8, 4 = int4, 1 = binary

    # Agent loop: keep prompts small so the llama runner is less likely to OOM / crash.
    agent_observation_max_chars: int = 8000
    agent_assistant_message_max_chars: int = 12000

    skye_url: str = ""
    skye_model: str = "mistral-small:22b"

    searxng_url: str = ""
    # Google Programmable Search (Custom Search JSON API). When both are set, web search uses
    # Google as primary and DuckDuckGo as secondary (unless SearXNG is configured).
    # Create a search engine at https://programmablesearchengine.google.com/ and enable the API.
    google_cse_api_key: str = ""
    google_cse_cx: str = ""
    # When SearXNG is unset: merge DuckDuckGo with Google (secondary) or use alone if no Google keys.
    web_search_fallback_ddg: bool = True
    # Auto-fetch top N result pages and include page text in search output.
    web_search_auto_fetch: bool = True
    web_search_auto_fetch_max: int = 2
    web_search_auto_fetch_chars: int = 3000

    chroma_path: Path = Field(default_factory=lambda: _default_data_dir() / "chroma")
    vault_path: Path = Field(default_factory=lambda: _default_data_dir() / "vault")
    ingest_queue: Path = Field(default_factory=lambda: _default_data_dir() / "ingest_queue")
    reflections_dir: Path = Field(default_factory=lambda: _default_data_dir() / "vault" / "reflections")
    current_focus_file: Path = Field(
        default_factory=lambda: _default_data_dir() / "vault" / "current_focus.md"
    )

    agent_max_steps: int = 8
    confidence_threshold: float = 0.75
    memory_search_top_k: int = 8

    # Memory ranking (weighted blend; weights normalized at runtime)
    memory_w_sim: float = 0.45
    memory_w_imp: float = 0.20
    memory_w_rec: float = 0.20
    memory_w_boost: float = 0.15
    memory_recency_half_life_days: float = 14.0

    # Neuro-symbolic rules (YAML); merged with packaged default_rules.yaml
    symbolic_enabled: bool = True
    symbolic_rules_path: Path = Field(default_factory=lambda: _default_data_dir() / "rules.yaml")

    # EEG research
    eeg_domain_enabled: bool = True
    eeg_workspace: Path = Field(default_factory=lambda: _default_data_dir() / "eeg_workspace")
    python_analysis_timeout: int = 300

    # Reflection intelligence
    reflection_min_confidence: float = 0.35
    reflection_compare_previous: bool = True

    discord_token: str = ""
    discord_guild_id: int = 0
    discord_channel_id: int = 0

    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
