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

import subprocess
import sys
from typing import Any

from hexnode.config import settings
from hexnode.tools.base import Tool, ToolContext, ToolResult

_EEG_EXTS = (
    ".edf", ".bdf", ".fif", ".set", ".fdt", ".vhdr", ".vmrk", ".eeg",
    ".cnt", ".nfb", ".csv", ".xdf", ".gdf", ".mff",
)

def _get_allowed() -> dict[str, list[str]]:
    from hexnode.config import python_for_eeg
    py = python_for_eeg()
    return {
        "nvidia_smi": [
            "nvidia-smi",
            "--query-gpu=name,memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader",
        ],
        "netstat_listening": ["netstat", "-ano"],
        "mne_sys_info": [py, "-c", "import mne; mne.sys_info()"],
        "pip_list_eeg": [py, "-m", "pip", "list", "--format=columns"],
    }

_ALLOWED: dict[str, list[str]] = {}

_PRESETS_DOC = ", ".join(sorted(_ALLOWED)) + ", list_eeg_files"


class RunShellCommandTool(Tool):
    name = "run_shell_command"
    required_feature = "shell_command"
    description = (
        "Run an allowlisted read-only diagnostic. Params: preset (str) — "
        f"one of: {_PRESETS_DOC}."
    )

    async def run(self, ctx: ToolContext, preset: str = "", **_: Any) -> ToolResult:
        key = (preset or "").strip().lower()

        if key == "list_eeg_files":
            return self._list_eeg_files()

        allowed = _get_allowed()
        if key not in allowed:
            return ToolResult(
                ok=False,
                data=None,
                error=f"Unknown preset. Allowed: {_PRESETS_DOC}",
            )
        argv = allowed[key]
        try:
            out = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            text = (out.stdout or "") + (("\n" + out.stderr) if out.stderr else "")
            text = text[:8000]
            return ToolResult(ok=out.returncode == 0, data=text.strip() or "(empty output)")
        except Exception as e:
            return ToolResult(ok=False, data=None, error=str(e))

    @staticmethod
    def _list_eeg_files() -> ToolResult:
        ws = settings.eeg_workspace
        if not ws.is_dir():
            return ToolResult(ok=True, data=f"(workspace {ws} does not exist yet)")
        lines: list[str] = []
        for f in sorted(ws.rglob("*")):
            if f.is_file() and f.suffix.lower() in _EEG_EXTS:
                rel = f.relative_to(ws)
                size_kb = f.stat().st_size / 1024
                lines.append(f"{rel}  ({size_kb:.0f} KB)")
        return ToolResult(
            ok=True,
            data="\n".join(lines) if lines else "(no EEG files found in eeg_workspace/)",
        )

