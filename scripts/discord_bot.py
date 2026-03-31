"""
Optional Discord bridge: messages in a channel → Paradox /agent endpoint.
Install: pip install discord.py
Set DISCORD_TOKEN, DISCORD_CHANNEL_ID, PARADOX_API=http://127.0.0.1:8765 (legacy: HEX_API, ANTON_API)
"""
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


import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import discord
except ImportError:
    print("Install discord.py: pip install discord.py")
    raise


def _api_base() -> str:
    return (
        os.environ.get("PARADOX_API") or os.environ.get("HEX_API") or os.environ.get("ANTON_API") or "http://127.0.0.1:8765"
    ).rstrip("/")


async def ask_agent(text: str) -> str:
    base = _api_base()
    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
        r = await client.post(f"{base}/agent", json={"message": text, "interface": "discord"})
        r.raise_for_status()
        data = r.json()
        return str(data.get("answer", ""))


class ParadoxClient(discord.Client):
    def __init__(self, *, channel_id: int) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.channel_id = channel_id

    async def on_ready(self) -> None:
        print(f"Discord logged in as {self.user} (channel {self.channel_id})")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.channel.id != self.channel_id:
            return
        if not message.content.strip():
            return
        async with message.channel.typing():
            try:
                reply = await ask_agent(message.content)
            except Exception as e:
                reply = f"(Paradox error: {e})"
        await message.reply(reply[:1900])


def main() -> None:
    token = os.environ.get("DISCORD_TOKEN", "")
    ch = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))
    if not token or not ch:
        print("Set DISCORD_TOKEN and DISCORD_CHANNEL_ID")
        sys.exit(1)
    client = ParadoxClient(channel_id=ch)
    client.run(token)


if __name__ == "__main__":
    main()
