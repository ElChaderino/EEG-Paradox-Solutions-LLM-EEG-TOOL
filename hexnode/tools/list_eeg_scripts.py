"""List and read pre-made EEG analysis script templates."""
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

import sys
from pathlib import Path
from typing import Any

from hexnode.config import settings
from hexnode.tools.base import Tool, ToolContext, ToolResult


def get_eeg_scripts_directory() -> Path:
    """Public path to bundled `data/eeg_scripts` (same resolution as list_eeg_scripts)."""
    return _scripts_dir()


def _scripts_dir() -> Path:
    if getattr(sys, "frozen", False):
        import os
        data_dir = (
            Path(os.environ.get("LOCALAPPDATA", Path.home()))
            / "ParadoxSolutionsLLM" / "data" / "eeg_scripts"
        )
        if data_dir.is_dir():
            return data_dir
    return Path(__file__).resolve().parent.parent.parent / "data" / "eeg_scripts"


class ListEegScriptsTool(Tool):
    name = "list_eeg_scripts"
    required_feature = "eeg"
    description = (
        "List or read pre-made EEG analysis script templates. "
        "Params: name (str, optional) — script filename to read (e.g. 'band_power_analysis.py'). "
        "If omitted, lists all available templates with descriptions."
    )

    async def run(self, ctx: ToolContext, name: str = "", **_: Any) -> ToolResult:
        scripts_dir = _scripts_dir()
        if not scripts_dir.is_dir():
            return ToolResult(ok=False, data=None, error="eeg_scripts directory not found")

        if name.strip():
            target = scripts_dir / name.strip()
            if not target.exists():
                avail = [f.name for f in scripts_dir.glob("*.py")]
                return ToolResult(
                    ok=False, data=None,
                    error=f"Script '{name}' not found. Available: {', '.join(avail)}"
                )
            content = target.read_text(encoding="utf-8")
            return ToolResult(ok=True, data=content, error=None)

        entries = []
        for f in sorted(scripts_dir.glob("*.py")):
            doc = ""
            text = f.read_text(encoding="utf-8", errors="replace")
            if text.startswith('"""'):
                end = text.find('"""', 3)
                if end > 3:
                    doc = text[3:end].strip().split("\n")[0]
            entries.append(f"{f.name} — {doc}")

        return ToolResult(ok=True, data="\n".join(entries), error=None)
