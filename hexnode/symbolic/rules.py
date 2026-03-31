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
from pathlib import Path
from typing import Any

import yaml

from hexnode.config import Settings

_PACKAGE_DEFAULT = Path(__file__).resolve().parent / "default_rules.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8", errors="replace")
    return yaml.safe_load(raw) or {}


def _merge_hints(base: dict[str, Any], extra: dict[str, Any]) -> list[dict[str, Any]]:
    a = list(base.get("hints") or [])
    b = list(extra.get("hints") or [])
    return a + b


def load_symbolic_hints(user_message: str, settings: Settings) -> str:
    """Return a markdown bullet block of matched deterministic hints (or empty string)."""
    if not getattr(settings, "symbolic_enabled", True):
        return ""
    base = _read_yaml(_PACKAGE_DEFAULT)
    user_path = settings.symbolic_rules_path
    merged_hints = _merge_hints(base, _read_yaml(user_path))
    lines: list[str] = []
    for h in merged_hints:
        pat = h.get("pattern")
        text = h.get("text")
        if not pat or not text:
            continue
        try:
            if re.search(pat, user_message):
                lines.append(f"- {text}")
        except re.error:
            continue
    if not lines:
        return ""
    return "## Symbolic routing hints (rules; obey when relevant)\n" + "\n".join(lines) + "\n"
