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

from hexnode.config import settings
from hexnode.tools.base import Tool, ToolContext, ToolResult


class QueryMemoryTool(Tool):
    name = "query_memory"
    description = (
        "Semantic search across Paradox memory (chat_history, documents, library). "
        "Params: query (required), collection (optional: chat_history|documents|library), top_k (optional int)."
    )

    async def run(
        self,
        ctx: ToolContext,
        query: str = "",
        collection: str | None = None,
        top_k: int | None = None,
        **_: Any,
    ) -> ToolResult:
        if not query.strip():
            return ToolResult(ok=False, data=None, error="query is required")
        hits = await ctx.memory.query(
            collection,
            query,
            top_k=top_k or settings.memory_search_top_k,
        )
        ctx.memory.touch_ids(hits)
        lines = []
        for h in hits[: settings.memory_search_top_k]:
            comp = h.get("score_components") or {}
            extra = ""
            if comp:
                extra = (
                    f" sim={comp.get('similarity', 0):.2f}"
                    f" rec={comp.get('recency', 0):.2f}"
                    f" imp={comp.get('importance', 0):.2f}"
                )
            lines.append(
                f"[{h['collection']}] score={h['score']:.3f}{extra}\n{h['document'][:1200]}"
            )
        return ToolResult(ok=True, data="\n\n---\n\n".join(lines) if lines else "(no hits)")

