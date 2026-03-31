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


class SendDiscordMessageTool(Tool):
    name = "send_discord_message"
    required_feature = "discord"
    description = "Send a short proactive message to the configured Discord channel. Params: text (str)."

    async def run(self, ctx: ToolContext, text: str = "", **_: Any) -> ToolResult:
        if not settings.discord_token or not settings.discord_channel_id:
            return ToolResult(
                ok=False,
                data=None,
                error="Discord not configured (DISCORD_TOKEN, DISCORD_CHANNEL_ID)",
            )
        if not text.strip():
            return ToolResult(ok=False, data=None, error="text is required")
        url = f"https://discord.com/api/v10/channels/{settings.discord_channel_id}/messages"
        headers = {
            "Authorization": f"Bot {settings.discord_token}",
            "Content-Type": "application/json",
        }
        payload = {"content": text.strip()[:2000]}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, headers=headers, json=payload)
        if r.status_code not in (200, 201):
            return ToolResult(ok=False, data=None, error=f"Discord API {r.status_code}: {r.text[:400]}")
        return ToolResult(ok=True, data="sent")

