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

import importlib
import inspect
import pkgutil
from typing import Any

from hexnode.tools.base import Tool, ToolContext, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tool_specs(self) -> list[dict[str, str]]:
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]

    async def run(self, name: str, ctx: ToolContext, params: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(ok=False, data=None, error=f"Unknown tool: {name}")
        sig = inspect.signature(tool.run)
        accepted = set(sig.parameters.keys()) - {"self", "ctx"}
        filtered = {k: v for k, v in params.items() if k in accepted}
        return await tool.run(ctx, **filtered)


def _discover_tools() -> list[Tool]:
    import hexnode.tools as tools_pkg

    out: list[Tool] = []
    for mod in pkgutil.iter_modules(tools_pkg.__path__):
        if mod.name.startswith("_") or mod.name in ("base", "registry", "tools_impl"):
            continue
        m = importlib.import_module(f"hexnode.tools.{mod.name}")
        for _, obj in inspect.getmembers(m):
            if not (inspect.isclass(obj) and issubclass(obj, Tool) and obj is not Tool):
                continue
            if getattr(obj, "__module__", None) != m.__name__:
                continue
            try:
                inst = obj()
            except Exception:
                continue
            if getattr(inst, "name", None):
                out.append(inst)
    return out


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        for t in _discover_tools():
            _registry.register(t)
    return _registry
