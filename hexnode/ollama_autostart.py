"""Try to start the Ollama daemon when the API starts (browser / run_server.py mode).

The Tauri desktop app uses its own setup; this covers dev and local web UI.
"""
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
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from hexnode.ollama_client import OllamaClient

log = logging.getLogger("hexnode.ollama_autostart")


def find_ollama_executable() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        p = Path(local) / "Programs" / "Ollama" / "ollama.exe"
        if p.is_file():
            return str(p)
        for pf in ("ProgramFiles", "ProgramFiles(x86)"):
            v = os.environ.get(pf)
            if v:
                q = Path(v) / "Ollama" / "ollama.exe"
                if q.is_file():
                    return str(q)
    if sys.platform == "darwin":
        p = Path("/Applications/Ollama.app/Contents/Resources/ollama")
        if p.is_file():
            return str(p)
    return None


def spawn_ollama_serve(executable: str) -> bool:
    try:
        if sys.platform == "win32":
            cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                [executable, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=cf,
            )
        else:
            subprocess.Popen(
                [executable, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        return True
    except Exception as e:
        log.warning("Could not spawn ollama serve: %s", e)
        return False


async def wait_until_ollama_responds(
    client: OllamaClient, *, timeout_s: float = 45.0, interval_s: float = 0.5
) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if await client.ping():
            return True
        await asyncio.sleep(interval_s)
    return False


async def try_spawn_ollama_if_down(client: OllamaClient) -> bool:
    """If Ollama is down, run ``ollama serve`` and wait until /api/tags responds."""
    if await client.ping():
        return True
    exe = find_ollama_executable()
    if not exe:
        log.warning(
            "Ollama is not running and no ollama executable was found (PATH or default install path)."
        )
        return False
    log.info("Starting Ollama: %s serve", exe)
    if not spawn_ollama_serve(exe):
        return False
    ok = await wait_until_ollama_responds(client)
    if ok:
        log.info("Ollama is responding.")
    else:
        log.warning("Ollama process started but did not respond before timeout.")
    return ok
