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

from hexnode.tools.base import Tool, ToolContext, ToolResult


class BoostMemoryTool(Tool):
    name = "boost_memory"
    description = (
        "Increase importance weight for a memory id. Params: memory_id (str), "
        "collection (chat_history|documents|library), amount (float 0-1, default 0.15)."
    )

    async def run(
        self,
        ctx: ToolContext,
        memory_id: str = "",
        collection: str = "chat_history",
        amount: float = 0.15,
        **_: Any,
    ) -> ToolResult:
        if not memory_id.strip():
            return ToolResult(ok=False, data=None, error="memory_id is required")
        ok = ctx.memory.boost_memory(memory_id.strip(), collection, float(amount))
        if not ok:
            return ToolResult(ok=False, data=None, error="memory id not found or update failed")
        return ToolResult(ok=True, data="boost applied")

