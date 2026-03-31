"""Fetch a URL with retry logic and content caching (adapted from EEG Paradox)."""
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

import asyncio
import logging
import re
from typing import Any

import httpx
import trafilatura

from hexnode.tools.base import Tool, ToolContext, ToolResult

log = logging.getLogger("hexnode.fetch_url")

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_RETRY_CODES = {429, 500, 502, 503, 504}


async def _fetch_with_retry(
    url: str, *, max_retries: int = 2, timeout: float = 30.0
) -> httpx.Response | None:
    """Fetch with exponential backoff on transient errors."""
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True, headers=_DEFAULT_HEADERS
            ) as client:
                r = await client.get(url)
            if r.status_code in _RETRY_CODES and attempt < max_retries:
                delay = 1.5 * (2 ** attempt)
                log.info("fetch_url %s got %d, retrying in %.1fs", url, r.status_code, delay)
                await asyncio.sleep(delay)
                continue
            return r
        except httpx.HTTPError as e:
            if attempt < max_retries:
                await asyncio.sleep(1.5 * (2 ** attempt))
            else:
                raise
    return None


def _extract_pdf_text(content: bytes, char_limit: int = 12000) -> str:
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        return text[:char_limit] if text.strip() else ""
    except Exception:
        return ""


class FetchUrlTool(Tool):
    name = "fetch_url"
    description = (
        "Fetch a URL and extract main text. Supports HTML (trafilatura) and PDF. "
        "Retries on transient errors (429, 5xx). Params: url (str)."
    )

    async def run(self, ctx: ToolContext, url: str = "", **_: Any) -> ToolResult:
        if not url.strip():
            return ToolResult(ok=False, data=None, error="url is required")

        try:
            from hexnode.tools.deep_research import _cache
            cached = _cache.get(url)
            if cached:
                return ToolResult(ok=True, data=cached[:12000], meta={"cached": True})
        except Exception:
            pass

        try:
            r = await _fetch_with_retry(url)
        except httpx.HTTPError as e:
            return ToolResult(ok=False, data=None, error=str(e)[:800])

        if r is None or r.status_code >= 400:
            status = r.status_code if r else 0
            return ToolResult(
                ok=False, data=None,
                error=f"HTTP {status} from URL (site may block automated requests)",
            )

        content_type = r.headers.get("content-type", "")
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            text = _extract_pdf_text(r.content)
            if text:
                try:
                    from hexnode.tools.deep_research import _cache
                    _cache.put(url, text[:12000])
                except Exception:
                    pass
                return ToolResult(ok=True, data=text)
            return ToolResult(ok=True, data="(PDF found but no extractable text)")

        raw_html = r.text
        text = trafilatura.extract(raw_html) or ""

        if not text.strip():
            title_match = re.search(r"<title[^>]*>([^<]+)</title>", raw_html, re.I)
            og_desc_match = re.search(
                r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
                raw_html, re.I,
            )
            parts = []
            if title_match:
                parts.append(f"Title: {title_match.group(1).strip()}")
            if og_desc_match:
                parts.append(og_desc_match.group(1).strip())
            text = "\n".join(parts) if parts else ""

        text = (text or "")[:12000]

        try:
            from hexnode.tools.deep_research import _cache
            if text.strip():
                _cache.put(url, text)
        except Exception:
            pass

        return ToolResult(ok=True, data=text or "(no extractable text)")
