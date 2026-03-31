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

import json
import logging
import os
from typing import Any

import httpx

from hexnode.config import settings

log = logging.getLogger("hexnode.ollama")


def apply_ollama_env() -> dict[str, str]:
    """Set Ollama environment variables for KV cache and flash attention optimizations.
    Returns a dict of what was applied (for logging/UI display)."""
    applied: dict[str, str] = {}
    if settings.ollama_flash_attention:
        os.environ.setdefault("OLLAMA_FLASH_ATTENTION", "1")
        applied["flash_attention"] = "enabled"
    if settings.ollama_kv_cache_type and settings.ollama_kv_cache_type != "f16":
        os.environ.setdefault("OLLAMA_KV_CACHE_TYPE", settings.ollama_kv_cache_type)
        applied["kv_cache_type"] = settings.ollama_kv_cache_type
    return applied


def _ollama_error_text(r: httpx.Response) -> str:
    try:
        j = r.json()
        if isinstance(j, dict) and j.get("error"):
            return str(j["error"])
    except Exception:
        pass
    return (r.text or "").strip()[:4000] or f"HTTP {r.status_code}"


class OllamaChatError(RuntimeError):
    """Ollama /api/chat returned an error; detail may include server JSON `error` field."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class OllamaClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base = (base_url or settings.ollama_base).rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ping(self) -> bool:
        try:
            r = await self._client.get(f"{self.base}/api/tags", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    async def embed(self, text: str) -> list[float]:
        opts: dict[str, Any] = {}
        if settings.ollama_embed_num_ctx > 0:
            opts["num_ctx"] = settings.ollama_embed_num_ctx
        if settings.ollama_embed_on_cpu:
            opts["num_gpu"] = 0
        payload: dict[str, Any] = {
            "model": settings.embed_model,
            "prompt": text,
        }
        if opts:
            payload["options"] = opts
        r = await self._client.post(
            f"{self.base}/api/embeddings",
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        return data["embedding"]

    @staticmethod
    def _base_opts(temperature: float) -> dict[str, Any]:
        # Flash attention is controlled by OLLAMA_FLASH_ATTENTION (env), set in apply_ollama_env /
        # Tauri when starting Ollama. Do not pass flash_attn in API options — Ollama 0.18+ rejects it
        # ("invalid option provided option=flash_attn").
        return {"temperature": temperature}

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.2,
        format_json: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": self._base_opts(temperature),
        }
        if system:
            payload["system"] = system
        if format_json:
            payload["format"] = "json"
        r = await self._client.post(f"{self.base}/api/generate", json=payload)
        r.raise_for_status()
        return r.json().get("response", "")

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        format_json: bool = False,
    ) -> str:
        opts = self._base_opts(temperature)
        if settings.ollama_chat_num_ctx > 0:
            opts["num_ctx"] = settings.ollama_chat_num_ctx
        if settings.ollama_chat_num_predict > 0:
            opts["num_predict"] = settings.ollama_chat_num_predict
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": opts,
        }
        if format_json:
            payload["format"] = "json"
        r = await self._client.post(f"{self.base}/api/chat", json=payload)
        if r.status_code != 200 and format_json:
            err = _ollama_error_text(r)
            log.warning(
                "Ollama /api/chat failed (%s) with format=json; retrying without JSON mode: %s",
                r.status_code,
                err[:500],
            )
            payload.pop("format", None)
            r = await self._client.post(f"{self.base}/api/chat", json=payload)
        if r.status_code != 200:
            raise OllamaChatError(r.status_code, _ollama_error_text(r))
        data = r.json()
        msg = data.get("message") or {}
        return msg.get("content", "")

    @staticmethod
    def strip_thinking(text: str) -> str:
        """Remove Qwen3-style <think>...</think> blocks from model output."""
        import re
        return re.sub(r"<think>[\s\S]*?</think>\s*", "", text).strip()

    @staticmethod
    def parse_json_loose(text: str) -> dict[str, Any]:
        text = OllamaClient.strip_thinking(text).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        return {}
