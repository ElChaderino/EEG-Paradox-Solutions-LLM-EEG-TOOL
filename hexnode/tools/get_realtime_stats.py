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

from typing import Any

import psutil

from hexnode.tools.base import Tool, ToolContext, ToolResult


class GetRealtimeStatsTool(Tool):
    name = "get_realtime_stats"
    description = "Top CPU/memory processes and basic service-style snapshot (local node)."

    async def run(self, ctx: ToolContext, limit: int = 12, **_: Any) -> ToolResult:
        limit = max(3, min(40, int(limit or 12)))
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs = [p for p in procs if p and p.get("name")]
        procs.sort(key=lambda x: (x.get("memory_percent") or 0), reverse=True)
        slim = [
            {
                "pid": p.get("pid"),
                "name": p.get("name"),
                "cpu_percent": round(p.get("cpu_percent") or 0, 2),
                "mem_percent": round(p.get("memory_percent") or 0, 2),
            }
            for p in procs[:limit]
        ]
        return ToolResult(ok=True, data={"top_processes": slim, "boot_time": psutil.boot_time()})

