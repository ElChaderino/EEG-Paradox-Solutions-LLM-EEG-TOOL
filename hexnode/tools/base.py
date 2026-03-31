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

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    memory: Any
    ollama: Any
    settings: Any
    trace_id: str = ""


@dataclass
class ToolResult:
    ok: bool
    data: Any
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class Tool:
    name: str = ""
    description: str = ""
    required_feature: str = ""
    #: All of these must be present (in addition to ``required_feature``, if set).
    required_all_features: tuple[str, ...] = ()

    async def run(self, ctx: ToolContext, **params: Any) -> ToolResult:
        raise NotImplementedError
