"""Deep research tool — multi-source scraper + cache adapted from EEG Paradox."""
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
import gzip
import hashlib
import logging
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from hexnode.config import settings
from hexnode.tools.base import Tool, ToolContext, ToolResult

log = logging.getLogger("hexnode.deep_research")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_CACHE_DB = Path(settings.vault_path) / "research_cache.db"
_RETRY_CODES = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Content cache (SQLite + gzip, ported from EEG Paradox)
# ---------------------------------------------------------------------------
class _ContentCache:
    def __init__(self, db_path: Path = _CACHE_DB, ttl_hours: int = 48):
        self._db = str(db_path)
        self._ttl = ttl_hours * 3600
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db, check_same_thread=False)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(url_hash TEXT PRIMARY KEY, url TEXT, content BLOB, ts REAL, size INT)"
        )
        conn.commit()
        conn.close()

    def get(self, url: str) -> str | None:
        h = hashlib.md5(url.encode()).hexdigest()
        conn = sqlite3.connect(self._db, check_same_thread=False)
        row = conn.execute(
            "SELECT content, ts FROM cache WHERE url_hash=? AND ts>?",
            (h, time.time() - self._ttl),
        ).fetchone()
        conn.close()
        if row:
            return gzip.decompress(row[0]).decode("utf-8")
        return None

    def put(self, url: str, content: str) -> None:
        h = hashlib.md5(url.encode()).hexdigest()
        blob = gzip.compress(content.encode("utf-8"))
        conn = sqlite3.connect(self._db, check_same_thread=False)
        conn.execute(
            "INSERT OR REPLACE INTO cache (url_hash,url,content,ts,size) VALUES (?,?,?,?,?)",
            (h, url, blob, time.time(), len(content)),
        )
        conn.commit()
        conn.close()


_cache = _ContentCache()


# ---------------------------------------------------------------------------
# Retry-aware async fetcher
# ---------------------------------------------------------------------------
async def _fetch_with_retry(
    url: str, *, max_retries: int = 2, timeout: float = 20.0
) -> tuple[str | None, int]:
    """Fetch URL text with retries on transient failures. Returns (text, status)."""
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True, headers=_HEADERS
            ) as client:
                r = await client.get(url)
            if r.status_code in _RETRY_CODES and attempt < max_retries:
                await asyncio.sleep(1.5 * (2 ** attempt))
                continue
            if r.status_code >= 400:
                return None, r.status_code
            return r.text, r.status_code
        except Exception:
            if attempt < max_retries:
                await asyncio.sleep(1.5 * (2 ** attempt))
            else:
                return None, 0
    return None, 0


# ---------------------------------------------------------------------------
# Page content extractor
# ---------------------------------------------------------------------------
async def _extract_page(url: str, char_limit: int = 6000) -> dict[str, str] | None:
    cached = _cache.get(url)
    if cached:
        return {"url": url, "text": cached[:char_limit], "cached": True}

    html, status = await _fetch_with_retry(url)
    if not html:
        return None

    text = trafilatura.extract(html) or ""
    if not text.strip():
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)

    title = ""
    tm = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if tm:
        title = tm.group(1).strip()

    if not text.strip():
        return None

    _cache.put(url, text[:12000])
    return {"url": url, "title": title, "text": text[:char_limit]}


# ---------------------------------------------------------------------------
# PubMed search (direct HTML scrape, no API key needed)
# ---------------------------------------------------------------------------
async def _search_pubmed(query: str, max_results: int = 5) -> list[dict[str, str]]:
    base = "https://pubmed.ncbi.nlm.nih.gov"
    search_url = f"{base}/?term={quote(query)}"
    html, status = await _fetch_with_retry(search_url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    for article in soup.find_all("article", class_="full-docsum"):
        title_el = article.find("a", class_="docsum-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        full_url = f"{base}{href}" if href.startswith("/") else href
        snippet_el = article.find("div", class_="full-view-snippet")
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        results.append({"title": title, "url": full_url, "snippet": snippet, "source": "PubMed"})
        if len(results) >= max_results:
            break
    return results


# ---------------------------------------------------------------------------
# Google Scholar search (HTML scrape, no API key)
# ---------------------------------------------------------------------------
async def _search_scholar(query: str, max_results: int = 5) -> list[dict[str, str]]:
    url = f"https://scholar.google.com/scholar?q={quote(query)}&hl=en"
    html, status = await _fetch_with_retry(url, timeout=15.0)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    for div in soup.find_all("div", class_="gs_ri"):
        h3 = div.find("h3")
        if not h3:
            continue
        link = h3.find("a")
        if not link:
            continue
        title = link.get_text(strip=True)
        href = link.get("href", "")
        snip_div = div.find("div", class_="gs_rs")
        snippet = snip_div.get_text(strip=True) if snip_div else ""
        results.append({"title": title, "url": href, "snippet": snippet, "source": "Scholar"})
        if len(results) >= max_results:
            break
    return results


# ---------------------------------------------------------------------------
# Web search (Google Programmable Search primary + DuckDuckGo secondary when configured)
# ---------------------------------------------------------------------------
def _web_results_for_deep(query: str, max_results: int = 6) -> list[dict[str, str]]:
    from hexnode.tools.web_search import combined_primary_web_results

    rows = combined_primary_web_results(query)[:max_results]
    items: list[dict[str, str]] = []
    for it in rows:
        href = it.get("href") or it.get("url", "")
        if not href:
            continue
        items.append({
            "title": it.get("title", ""),
            "url": href,
            "snippet": (it.get("body") or "")[:300],
            "source": "Web",
        })
    return items


# ---------------------------------------------------------------------------
# PDF text extraction (if PyPDF2 available)
# ---------------------------------------------------------------------------
async def _extract_pdf_text(url: str, char_limit: int = 8000) -> str | None:
    try:
        import io
        from pypdf import PdfReader
        async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS) as client:
            r = await client.get(url)
        if r.status_code >= 400:
            return None
        reader = PdfReader(io.BytesIO(r.content))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        return text[:char_limit] if text.strip() else None
    except Exception as e:
        log.debug("PDF extraction failed for %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Main research orchestrator
# ---------------------------------------------------------------------------
async def _research(
    query: str,
    max_pages: int = 4,
    sources: list[str] | None = None,
) -> str:
    """Run multi-source research and return a formatted summary."""
    if sources is None:
        sources = ["web", "pubmed", "scholar"]

    all_results: list[dict[str, str]] = []
    tasks_map: dict[str, Any] = {}

    if "web" in sources:
        tasks_map["web"] = asyncio.to_thread(_web_results_for_deep, query, 6)
    if "pubmed" in sources:
        tasks_map["pubmed"] = _search_pubmed(query, 5)
    if "scholar" in sources:
        tasks_map["scholar"] = _search_scholar(query, 5)

    search_results = await asyncio.gather(*tasks_map.values(), return_exceptions=True)
    for key, result in zip(tasks_map.keys(), search_results):
        if isinstance(result, Exception):
            log.warning("Search source %s failed: %s", key, result)
            continue
        all_results.extend(result)

    seen_urls: set[str] = set()
    unique: list[dict[str, str]] = []
    for r in all_results:
        u = r.get("url", "")
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique.append(r)

    sections: list[str] = []
    sections.append(f"## Research: {query}")
    sections.append(f"*{len(unique)} results from {', '.join(sources)}*\n")

    for i, r in enumerate(unique[:12], 1):
        sections.append(
            f"{i}. **{r['title']}** ({r['source']})\n"
            f"   {r['url']}\n"
            f"   {r['snippet'][:200]}"
        )

    fetch_urls = [r["url"] for r in unique[:max_pages] if r.get("url")]
    pdf_urls = [u for u in fetch_urls if u.lower().endswith(".pdf")]
    html_urls = [u for u in fetch_urls if u not in pdf_urls]

    page_tasks = [_extract_page(u) for u in html_urls]
    page_results = await asyncio.gather(*page_tasks, return_exceptions=True)

    sections.append("\n## Extracted Content\n")
    for result in page_results:
        if isinstance(result, Exception) or result is None:
            continue
        title = result.get("title", result["url"])
        sections.append(f"### {title}")
        sections.append(f"Source: {result['url']}")
        sections.append(result["text"][:4000])
        sections.append("")

    for pdf_url in pdf_urls[:2]:
        text = await _extract_pdf_text(pdf_url)
        if text:
            sections.append(f"### PDF: {pdf_url.split('/')[-1]}")
            sections.append(f"Source: {pdf_url}")
            sections.append(text[:4000])
            sections.append("")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------
class DeepResearchTool(Tool):
    name = "deep_research"
    required_feature = "deep_research"
    description = (
        "Deep multi-source research: web search (Google Programmable Search + DuckDuckGo when configured, "
        "else DuckDuckGo), plus PubMed and Google Scholar "
        "in parallel, then fetches and extracts content from top results. "
        "Results are cached for 48h. Great for EEG/neuroscience research, finding papers, "
        "and getting comprehensive answers. "
        "Params: query (str), sources (optional list: 'web','pubmed','scholar'), "
        "max_pages (optional int, default 4)."
    )

    async def run(
        self,
        ctx: ToolContext,
        query: str = "",
        sources: list[str] | None = None,
        max_pages: int = 4,
        **_: Any,
    ) -> ToolResult:
        if not query.strip():
            return ToolResult(ok=False, data=None, error="query is required")

        try:
            result = await _research(query.strip(), max_pages=max_pages, sources=sources)
            return ToolResult(ok=True, data=result)
        except Exception as e:
            log.exception("deep_research failed")
            return ToolResult(ok=False, data=None, error=f"Research failed: {e}"[:800])
