"""Extract MNE/Python script + reference links for the Script workspace UI."""
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

import re
from typing import Any

# Final answer may contain ```python ... ``` for users to copy; prefer tool-run script when present.
_PYTHON_FENCE = re.compile(r"```(?:python|py)\s*\n([\s\S]*?)```", re.IGNORECASE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_BARE_URL = re.compile(r"(?<![(\[])(https?://[^\s\]>]+)(?=[\s\])]|$)")


def _python_from_fences(text: str) -> str | None:
    matches = list(_PYTHON_FENCE.finditer(text or ""))
    if not matches:
        return None
    return matches[-1].group(1).strip() or None


def _collect_links(text: str, max_links: int = 40) -> list[str]:
    seen: list[str] = []
    for m in _MD_LINK.finditer(text or ""):
        u = m.group(2).strip().rstrip(").,;")
        if u not in seen:
            seen.append(u)
    for m in _BARE_URL.finditer(text or ""):
        u = m.group(1).strip().rstrip(").,;")
        if u not in seen:
            seen.append(u)
        if len(seen) >= max_links:
            break
    return seen[:max_links]


def _last_tool_script(steps: list[dict[str, Any]]) -> str | None:
    for s in reversed(steps):
        if s.get("action") != "run_python_analysis":
            continue
        raw = s.get("python_script")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def build_script_workspace(final_answer: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Payload for web UI: editable script + doc links from the last agent turn."""
    from_tool = _last_tool_script(steps)
    from_fence = _python_from_fences(final_answer or "")
    python_src = from_tool or from_fence
    links = _collect_links(final_answer or "")
    return {
        "python": python_src,
        "reference_links": links,
        "source": (
            "run_python_analysis"
            if from_tool
            else ("markdown_fence" if from_fence else None)
        ),
    }
