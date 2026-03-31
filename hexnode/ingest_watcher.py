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
from pathlib import Path
from typing import TYPE_CHECKING

from hexnode.config import settings
from hexnode.tools.base import ToolContext
from hexnode.tools.ingest_document import ingest_file_path

if TYPE_CHECKING:
    from hexnode.memory_store import MemoryStore
    from hexnode.ollama_client import OllamaClient

log = logging.getLogger("hexnode.ingest")

_SEEN: set[str] = set()


async def ingest_watcher_loop(memory: MemoryStore, ollama: OllamaClient) -> None:
    settings.ingest_queue.mkdir(parents=True, exist_ok=True)
    ctx = ToolContext(memory=memory, ollama=ollama, settings=settings)
    while True:
        try:
            for p in sorted(settings.ingest_queue.iterdir()):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in {
                    ".pdf", ".txt", ".md", ".markdown",
                    ".csv", ".json", ".yaml", ".yml", ".docx",
                    ".edf", ".bdf",
                }:
                    continue
                key = f"{p.resolve()}|{p.stat().st_mtime_ns}"
                if key in _SEEN:
                    continue
                try:
                    n = await ingest_file_path(p, ctx, str(p))
                    log.info("Ingested %s chunks from %s", n, p.name)
                    _SEEN.add(key)
                except Exception as e:
                    log.warning("Ingest failed %s: %s", p, e)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Watcher error: %s", e)
        await asyncio.sleep(60)
