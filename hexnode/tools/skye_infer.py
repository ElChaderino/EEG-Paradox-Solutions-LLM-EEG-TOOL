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

import httpx

from hexnode.config import settings
from hexnode.tools.base import Tool, ToolContext, ToolResult


class SkyeInferTool(Tool):
    name = "skye_infer"
    description = (
        "Route a prompt to Skye (remote heavy Ollama node). Params: prompt (str). "
        "Set SKYE_URL to http://host:11434"
    )

    async def run(self, ctx: ToolContext, prompt: str = "", **_: Any) -> ToolResult:
        base = (settings.skye_url or "").rstrip("/")
        if not base:
            return ToolResult(ok=False, data=None, error="skye_url not configured")
        if not prompt.strip():
            return ToolResult(ok=False, data=None, error="prompt is required")
        async with httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=30.0)) as client:
            r = await client.post(
                f"{base}/api/generate",
                json={
                    "model": settings.skye_model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            if r.status_code != 200:
                return ToolResult(ok=False, data=None, error=f"Skye HTTP {r.status_code}: {r.text[:500]}")
            data = r.json()
            return ToolResult(ok=True, data=data.get("response", ""))

