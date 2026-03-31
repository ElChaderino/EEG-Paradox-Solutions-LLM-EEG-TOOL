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

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from hexnode.tools.base import Tool, ToolContext, ToolResult


class GetDatetimeTool(Tool):
    name = "get_datetime"
    description = "Current local date and time. Optional param: timezone (IANA name, e.g. America/New_York)."

    async def run(self, ctx: ToolContext, timezone: str = "", **_: Any) -> ToolResult:
        try:
            tz = ZoneInfo(timezone) if timezone else datetime.now().astimezone().tzinfo
            now = datetime.now(tz) if tz else datetime.now()
        except Exception:
            now = datetime.now()
        return ToolResult(
            ok=True,
            data={
                "iso": now.isoformat(),
                "timezone": str(now.tzinfo) if now.tzinfo else "local",
            },
        )

