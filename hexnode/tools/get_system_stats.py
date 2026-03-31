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
import shutil
import subprocess
from typing import Any

import psutil

from hexnode.tools.base import Tool, ToolContext, ToolResult


def _nvidia_smi_snapshot() -> dict[str, Any]:
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return {}
        parts = [p.strip() for p in out.stdout.strip().split(",")]
        if len(parts) < 5:
            return {}
        return {
            "gpu_name": parts[0],
            "gpu_mem_used_mb": parts[1],
            "gpu_mem_total_mb": parts[2],
            "gpu_util_pct": parts[3],
            "gpu_temp_c": parts[4],
        }
    except Exception:
        return {}


class GetSystemStatsTool(Tool):
    name = "get_system_stats"
    description = "Live CPU, RAM, disk, and NVIDIA GPU stats for this Windows host."

    async def run(self, ctx: ToolContext, **_: Any) -> ToolResult:
        vm = psutil.virtual_memory()
        root = os.environ.get("SystemDrive", "C:") + "\\"
        du = shutil.disk_usage(root)
        payload = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_used_gb": round(vm.used / (1024**3), 2),
            "ram_total_gb": round(vm.total / (1024**3), 2),
            "ram_percent": vm.percent,
            "disk_free_gb": round(du.free / (1024**3), 2),
            "disk_total_gb": round(du.total / (1024**3), 2),
            "disk_percent": round(100 * (1 - du.free / du.total), 1),
        }
        payload.update(_nvidia_smi_snapshot())
        return ToolResult(ok=True, data=payload)

