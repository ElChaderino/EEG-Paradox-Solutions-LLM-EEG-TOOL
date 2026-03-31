"""Run reflection once (schedule via Windows Task Scheduler, e.g. 03:30 daily)."""
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


import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def main() -> None:
    from hexnode.memory_store import MemoryStore
    from hexnode.ollama_client import OllamaClient
    from hexnode.reflection import run_reflection_pass

    ollama = OllamaClient()
    try:
        memory = MemoryStore(ollama)
        out = await run_reflection_pass(memory, ollama)
        print(out)
    finally:
        await ollama.aclose()


if __name__ == "__main__":
    asyncio.run(main())
