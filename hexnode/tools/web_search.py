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
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from hexnode.config import settings
from hexnode.tools.base import Tool, ToolContext, ToolResult

log = logging.getLogger("hexnode.web_search")

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_DATE_RE = re.compile(
    r"""(?ix)
    (?:
        (?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|
           Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)
        \s+\d{1,2}(?:\s*[-\u2013]\s*\d{1,2})?,?\s*\d{4}
    )
    |
    (?:
        \d{1,2}\s+
        (?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|
           Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)
        ,?\s*\d{4}
    )
    |
    (?:\d{4}[-/]\d{2}[-/]\d{2})
    """
)

_ADDRESS_RE = re.compile(
    r"\d{2,5}\s+[A-Z][A-Za-z\s]+(?:Blvd|St|Ave|Dr|Rd|Ln|Way|Ct|Cir|Pkwy)\b[^,]*,"
    r"\s*[A-Za-z\s]+,\s*[A-Z]{2}(?:\s+\d{5})?",
)

_CITY_STATE_RE = re.compile(
    r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z]{2}(?:\s+\d{5})?)"
)

_YEAR_IN_PATH_RE = re.compile(r"/(20\d{2})/|-(20\d{2})(?:[/\-.]|$)")

_STOP_WORDS = frozenset({
    "when", "where", "what", "how", "is", "the", "next", "and", "for",
    "of", "a", "an", "in", "at", "on", "are", "was", "will", "be", "do",
    "does", "did", "can", "could", "should", "would", "about", "this",
    "that", "with", "from", "have", "has", "had",
})

_SKIP_DOMAINS = frozenset({
    "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "youtube.com", "reddit.com", "tiktok.com", "pinterest.com",
    "wikipedia.org", "amazon.com", "ebay.com",
    "waset.org", "clocate.com", "sciencedz.net", "jorlio.com",
    "vendelux.com", "conferenceconnect.com", "msbmb.com",
    "google.com", "goo.gl",
})


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def _query_keywords(query: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{3,}", query.lower()) if w not in _STOP_WORDS]


def _domain_of(url: str) -> str:
    parts = urlparse(url).netloc.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else urlparse(url).netloc


def _is_skip_domain(url: str) -> bool:
    return _domain_of(url) in _SKIP_DOMAINS


# ---------------------------------------------------------------------------
# Key fact extraction
# ---------------------------------------------------------------------------
def _extract_key_facts(snippets: list[str]) -> list[str]:
    facts: list[str] = []
    seen: set[str] = set()
    for text in snippets:
        for m in _DATE_RE.finditer(text):
            d = m.group(0).strip()
            if d not in seen:
                facts.append(f"Date: {d}")
                seen.add(d)
        for m in _ADDRESS_RE.finditer(text):
            addr = m.group(0).strip()
            if addr not in seen:
                facts.append(f"Address: {addr}")
                seen.add(addr)
        for m in _CITY_STATE_RE.finditer(text):
            loc = m.group(1).strip()
            if loc not in seen:
                facts.append(f"Location: {loc}")
                seen.add(loc)
    return facts


def _fix_spacing(text: str) -> str:
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", text)


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------
def _relevance_score(item: dict[str, str], keywords: list[str]) -> float:
    if not keywords:
        return 0.5
    title = (item.get("title", "") or "").lower()
    body = (item.get("body") or item.get("content") or "").lower()
    href = (item.get("href") or item.get("url", "")).lower()
    combined = f"{title} {body} {href}"
    hits = sum(1 for kw in keywords if kw in combined)
    return hits / len(keywords)


def _sort_by_relevance(items: list[dict[str, str]], keywords: list[str]) -> list[dict[str, str]]:
    return sorted(items, key=lambda it: _relevance_score(it, keywords), reverse=True)


# ---------------------------------------------------------------------------
# Search engines
# ---------------------------------------------------------------------------
def _ddg_search(query: str) -> list[dict[str, str]]:
    from ddgs import DDGS
    items: list[dict[str, str]] = []
    try:
        with DDGS() as ddgs:
            for item in ddgs.text(query, max_results=8):
                items.append({
                    "title": item.get("title", ""),
                    "href": item.get("href", ""),
                    "body": (item.get("body") or "")[:400],
                })
    except Exception as e:
        log.warning("DDG search failed for '%s': %s", query, e)
    return items


def _google_cse_search(query: str) -> list[dict[str, str]]:
    """Google Custom Search JSON API — returns same shape as DDG hits."""
    key = (settings.google_cse_api_key or "").strip()
    cx = (settings.google_cse_cx or "").strip()
    if not key or not cx:
        return []
    api = "https://www.googleapis.com/customsearch/v1"
    params = {"key": key, "cx": cx, "q": query, "num": 10}
    items: list[dict[str, str]] = []
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(api, params=params)
        if r.status_code != 200:
            log.warning(
                "Google CSE HTTP %s for '%s': %s",
                r.status_code,
                query,
                (r.text or "")[:200],
            )
            return []
        data = r.json()
        for it in (data.get("items") or [])[:10]:
            items.append({
                "title": it.get("title", "") or "",
                "href": it.get("link", "") or "",
                "body": (it.get("snippet") or "")[:400],
            })
    except Exception as e:
        log.warning("Google CSE search failed for '%s': %s", query, e)
    return items


def combined_primary_web_results(query: str) -> list[dict[str, str]]:
    """Google Custom Search (if configured) as primary, DuckDuckGo merged as secondary."""
    google_hits = _google_cse_search(query)
    ddg_hits = _ddg_search(query) if settings.web_search_fallback_ddg else []
    if google_hits:
        return _merge_items(google_hits, ddg_hits)
    return ddg_hits


def _searx_search(base: str, query: str) -> list[dict[str, str]]:
    url = f"{base}/search?q={quote_plus(query)}&format=json"
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url)
        if r.status_code != 200:
            raise RuntimeError(f"SearXNG HTTP {r.status_code}")
        data = r.json()
    results = data.get("results") or []
    return [
        {"title": r.get("title", ""), "href": r.get("url", ""), "body": (r.get("content") or "")[:400]}
        for r in results[:8]
    ]


# ---------------------------------------------------------------------------
# Merge / dedup
# ---------------------------------------------------------------------------
def _merge_items(
    primary: list[dict[str, str]], secondary: list[dict[str, str]]
) -> list[dict[str, str]]:
    seen = {item["href"] for item in primary if item.get("href")}
    merged = list(primary)
    for item in secondary:
        href = item.get("href", "")
        if href and href not in seen:
            merged.append(item)
            seen.add(href)
    return merged[:14]


# ---------------------------------------------------------------------------
# Alt query generation (diverse strategies)
# ---------------------------------------------------------------------------
def _concat_adjacent_keywords(keywords: list[str]) -> list[str]:
    """Try joining adjacent short keywords to catch split-word typos.
    E.g. ["sui","sun","summit"] -> ["suisun"] because the user
    likely meant the single word 'suisun'."""
    joined: list[str] = []
    for i in range(len(keywords) - 1):
        a, b = keywords[i], keywords[i + 1]
        if len(a) <= 5 and len(b) <= 5:
            merged = a + b
            if merged not in keywords and len(merged) >= 5:
                joined.append(merged)
    return joined


def _generate_alt_queries(query: str, year_str: str) -> list[str]:
    """Generate diverse alt queries. Key insight: shorter queries often
    surface different (better) results on DDG than longer ones.
    Also tries concatenating adjacent short keywords to recover
    split-word typos (e.g. "sui sun" -> "suisun")."""
    alts: list[str] = []
    q_lower = query.lower()

    has_year = year_str in query or str(int(year_str) - 1) in query
    q_no_year = re.sub(r"\b20\d{2}\b", "", query).strip()
    q_no_year = re.sub(r"\s{2,}", " ", q_no_year)

    kw_no_year = _query_keywords(q_no_year)
    short = " ".join(kw_no_year[:2])
    medium = " ".join(kw_no_year[:3])

    event_words = {"summit", "conference", "meeting", "workshop", "congress"}
    first_last = ""
    if len(kw_no_year) >= 3:
        for ew in event_words:
            if ew in kw_no_year:
                unique_kw = [w for w in kw_no_year if w != ew]
                if unique_kw:
                    first_last = f"{unique_kw[0]} {ew}"
                    break
        if not first_last:
            first_last = f"{kw_no_year[0]} {kw_no_year[-1]}"

    # --- Concatenation variants (catches "sui sun" -> "suisun") ---
    concat_words = _concat_adjacent_keywords(kw_no_year)
    for cw in concat_words:
        remaining_kw = [w for w in kw_no_year if w not in (cw[:len(cw)//2], cw[len(cw)//2:])]
        remaining_event = [w for w in remaining_kw if w in event_words]
        if remaining_event:
            alts.append(f"{cw} {remaining_event[0]} {year_str}")
            alts.append(f"{cw} {remaining_event[0]}")
        else:
            alts.append(f"{cw} {year_str}")

    # 1) Shortest meaningful form + year
    target_short = first_last or short
    if target_short:
        alts.append(f"{target_short} {year_str}")

    # 2) Original without year
    if has_year and len(q_no_year) > 4:
        alts.append(q_no_year)

    # 3) Short form with year (if different from #1)
    if short and f"{short} {year_str}" not in alts:
        alts.append(f"{short} {year_str}")

    # 4) Medium form with year
    if medium and medium != short:
        alts.append(f"{medium} {year_str}")

    # 5) Bare keywords without year
    if target_short:
        alts.append(target_short)

    seen = set()
    deduped = []
    for a in alts:
        al = a.lower().strip()
        if al not in seen and al != q_lower.strip():
            seen.add(al)
            deduped.append(a)

    return deduped[:6]


# ---------------------------------------------------------------------------
# URL probing — uses query keywords, skips irrelevant domains
# ---------------------------------------------------------------------------
def _build_year_probe_urls(
    items: list[dict[str, str]], target_year: int, query_keywords: list[str]
) -> list[str]:
    probes: list[str] = []
    seen_domains: set[str] = set()

    relevant_items = [it for it in items if not _is_skip_domain(it.get("href", ""))]

    for item in relevant_items:
        href = item.get("href", "")
        if not href:
            continue
        parsed = urlparse(href)
        domain = parsed.netloc

        m = _YEAR_IN_PATH_RE.search(parsed.path)
        if m:
            old_year = m.group(1) or m.group(2)
            if old_year and int(old_year) != target_year:
                new_path = parsed.path.replace(old_year, str(target_year))
                probe_url = f"{parsed.scheme}://{domain}{new_path}"
                if probe_url != href and probe_url not in probes:
                    probes.append(probe_url)

        if domain not in seen_domains:
            seen_domains.add(domain)
            parts = domain.split(".")
            base_domain = ".".join(parts[-2:]) if len(parts) >= 2 else domain

            sub_candidates = list(dict.fromkeys(query_keywords + _extract_event_words(item)))

            for prefix in sub_candidates:
                if len(prefix) < 3 or prefix in base_domain.lower():
                    continue
                sub_url = f"{parsed.scheme}://{prefix}.{base_domain}"
                if sub_url not in probes and sub_url != href:
                    probes.append(sub_url)

    return probes[:8]


def _extract_event_words(item: dict[str, str]) -> list[str]:
    title = (item.get("title", "") or "").lower()
    words = re.findall(r"[a-z]{4,15}", title)
    stop = {"strategies", "training", "neuro", "page", "resource", "center",
            "articles", "certification", "annual", "events", "calendar",
            "about", "home", "neuroscience", "conference", "summit",
            "biofeedback", "alliance", "international"}
    return [w for w in words if w not in stop][:3]


# ---------------------------------------------------------------------------
# Outbound link extraction — follow links from fetched pages
# ---------------------------------------------------------------------------
def _extract_outbound_links(
    html: str, source_domain: str, query_keywords: list[str]
) -> list[str]:
    """Extract outbound links from HTML that match query keywords."""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []

    candidates: list[tuple[float, str]] = []
    seen: set[str] = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if not href.startswith("http"):
            continue
        link_domain = _domain_of(href)
        if link_domain == source_domain or _is_skip_domain(href):
            continue
        if href in seen:
            continue
        seen.add(href)

        anchor_text = a_tag.get_text(strip=True).lower()
        combined = f"{href.lower()} {anchor_text}"
        hits = sum(1 for kw in query_keywords if kw in combined)
        if hits >= 1:
            candidates.append((hits, href))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [url for _, url in candidates[:4]]


# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------
async def _fetch_page_with_meta(
    url: str, char_limit: int = 3000
) -> tuple[str | None, str | None, str]:
    """Fetch URL; return (text, page_title, raw_html). Falls back to meta extraction."""
    try:
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True, headers=_FETCH_HEADERS
        ) as client:
            r = await client.get(url)
        if r.status_code >= 400:
            return None, None, ""

        html = r.text
        text = trafilatura.extract(html) or ""

        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else None

        og_title = _extract_meta(html, "og:title")
        og_desc = _extract_meta(html, "og:description")
        meta_desc = _extract_meta_name(html, "description")

        if title and og_title and og_title != title:
            title = og_title

        supplement: list[str] = []
        if og_desc:
            clean_og = og_desc.replace("&hellip;", "...").replace("&#8211;", "-")
            if clean_og not in text:
                supplement.append(clean_og)
        if meta_desc and meta_desc not in text and meta_desc not in (og_desc or ""):
            supplement.append(meta_desc)

        if not text.strip() and not supplement and html:
            for m in re.finditer(
                r'content=["\']([^"\']*(?:20\d{2}|summit|conference|event)[^"\']*)["\']',
                html, re.IGNORECASE,
            ):
                val = m.group(1).strip()
                if len(val) > 20:
                    supplement.append(val)
                    if len(supplement) >= 3:
                        break

        if supplement:
            text = text.rstrip() + "\n" + "\n".join(supplement) if text.strip() else "\n".join(supplement)

        return text[:char_limit] if text.strip() else None, title, html
    except Exception:
        return None, None, ""


def _extract_meta(html: str, prop: str) -> str | None:
    m = re.search(
        rf'<meta[^>]+property=["\']{ re.escape(prop) }["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if not m:
        m = re.search(
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{ re.escape(prop) }["\']',
            html, re.IGNORECASE,
        )
    return m.group(1).strip() if m else None


def _extract_meta_name(html: str, name: str) -> str | None:
    m = re.search(
        rf'<meta[^>]+name=["\']{ re.escape(name) }["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if not m:
        m = re.search(
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{ re.escape(name) }["\']',
            html, re.IGNORECASE,
        )
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# ANSWER DATA summary
# ---------------------------------------------------------------------------
def _build_answer_summary(
    items: list[dict[str, str]],
    key_facts: list[str],
    probed_pages: list[tuple[str, str | None, str | None]],
    query_keywords: list[str],
) -> str:
    lines = [">>> ANSWER DATA (use this for your response) <<<"]

    year_str = str(_current_year())
    prev_year = str(_current_year() - 1)
    scored_pages = []
    seen_hosts: set[str] = set()
    for url, title, text in probed_pages:
        host = urlparse(url).netloc
        if host in seen_hosts:
            continue
        seen_hosts.add(host)
        score = _relevance_score(
            {"title": title or "", "body": (text or "")[:600], "href": url},
            query_keywords,
        )
        if score < 0.2:
            continue
        combined = f"{title or ''} {(text or '')[:800]} {url}".lower()
        if year_str in combined:
            score += 0.3
        if prev_year in combined and year_str not in combined:
            score -= 0.05
        scored_pages.append((score, url, title, text))
    scored_pages.sort(key=lambda x: x[0], reverse=True)
    top_pages = scored_pages[:4]

    for rank, (score, url, title, text) in enumerate(top_pages):
        marker = "BEST SOURCE" if rank == 0 else f"Source {rank + 1}"
        lines.append(f"\n--- {marker} (relevance {score:.1%}) ---")
        if title:
            clean_title = title.split(" - ")[0].strip()
            lines.append(f"Event: {clean_title}")
        if text:
            info_count = 0
            for snippet in text.split("\n"):
                snippet = snippet.strip()
                if not snippet or len(snippet) < 15:
                    continue
                snippet = snippet.replace("[...]", "").replace("&hellip;", "").strip()
                if snippet:
                    lines.append(f"Info: {snippet[:250]}")
                    info_count += 1
                    if info_count >= 8:
                        break
        label = title.split(" - ")[0].strip() if title else "Event Website"
        lines.append(f"Link: [{label}]({url})")
        lines.append(f"Website: {url}")

    for f in key_facts:
        if f.startswith("Date:"):
            continue
        lines.append(f)

    if not top_pages:
        for it in items[:5]:
            href = it.get("href", "")
            title = it.get("title", "Source")
            score = _relevance_score(it, query_keywords)
            if score >= 0.3 and href and not _is_skip_domain(href):
                lines.append(f"Link: [{title}]({href})")
                lines.append(f"Website: {href}")
                break
        else:
            for it in items[:3]:
                href = it.get("href", "")
                if href and not _is_skip_domain(href):
                    title = it.get("title", "Source")
                    lines.append(f"Link: [{title}]({href})")
                    lines.append(f"Website: {href}")
                    break

    lines.append("")
    lines.append("INSTRUCTIONS: Use the BEST SOURCE above for your answer. "
                  "Include its Link as a clickable [text](url). "
                  "If no confirmed future dates appear, say dates are TBD and link to the source.")
    lines.append(">>> END ANSWER DATA <<<")
    return "\n".join(lines)


def _format_results(items: list[dict[str, str]]) -> tuple[str, list[str]]:
    lines: list[str] = []
    snippets: list[str] = []
    for i, item in enumerate(items, 1):
        title = _fix_spacing(item.get("title", ""))
        href = item.get("href") or item.get("url", "")
        body = _fix_spacing((item.get("body") or item.get("content") or "")[:400])
        lines.append(f"{i}. **{title}**\n   URL: {href}\n   {body}")
        snippets.append(f"{title} {body}")
    return "\n".join(lines), snippets


# ---------------------------------------------------------------------------
# Main tool
# ---------------------------------------------------------------------------
class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web and read top result pages automatically. "
        "Uses Google Programmable Search first and DuckDuckGo as secondary when configured in .env; "
        "otherwise DuckDuckGo or self-hosted SearXNG. "
        "Returns search snippets + extracted page content from the top results. "
        "Also follows relevant outbound links to find the best source pages. "
        "Params: query (str) -- use natural, simple phrases (3-6 words) "
        "like 'suisun neuroscience summit 2026'. "
        "One search call is usually enough -- read the ANSWER DATA at the top "
        "of the result, then write your answer."
    )

    async def run(self, ctx: ToolContext, query: str = "", **_: Any) -> ToolResult:
        if not query.strip():
            return ToolResult(ok=False, data=None, error="query is required")

        q = query.strip()
        year = _current_year()
        year_str = str(year)
        keywords = _query_keywords(q)
        concat_kw = _concat_adjacent_keywords(keywords)
        keywords_expanded = keywords + [c for c in concat_kw if c not in keywords]

        base = (settings.searxng_url or "").strip().rstrip("/")
        g_ok = bool(
            (settings.google_cse_api_key or "").strip()
            and (settings.google_cse_cx or "").strip()
        )

        all_queries = [q] + _generate_alt_queries(q, year_str)
        all_queries = list(dict.fromkeys(all_queries))

        if not base and not settings.web_search_fallback_ddg and not g_ok:
            return ToolResult(
                ok=False,
                data=None,
                error=(
                    "Configure SEARXNG_URL, or set GOOGLE_CSE_API_KEY + GOOGLE_CSE_CX, "
                    "or enable WEB_SEARCH_FALLBACK_DDG"
                ),
            )

        raw_items: list[dict[str, str]] = []
        # Stagger DDG queries in pairs with a brief delay to avoid rate limits
        for batch_start in range(0, len(all_queries), 2):
            batch = all_queries[batch_start:batch_start + 2]
            tasks = []
            for sq in batch:
                if base:
                    tasks.append(asyncio.to_thread(_searx_search, base, sq))
                else:
                    tasks.append(asyncio.to_thread(combined_primary_web_results, sq))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    raw_items = _merge_items(raw_items, r)
            if batch_start + 2 < len(all_queries):
                await asyncio.sleep(1.5)

        # --- Phase 3: Relevance-sort results ---
        raw_items = _sort_by_relevance(raw_items, keywords_expanded)

        formatted, snippets = _format_results(raw_items)
        key_facts = _extract_key_facts(snippets)

        sections: list[str] = []
        probed_pages: list[tuple[str, str | None, str | None]] = []

        if key_facts:
            sections.append("=== KEY FACTS ===")
            sections.extend(key_facts)
            sections.append("")

        sections.append(f"=== SEARCH RESULTS ({len(raw_items)} hits) ===")
        sections.append(formatted)

        # --- Phase 4: Auto-fetch + smart probing + link following ---
        if settings.web_search_auto_fetch:
            char_limit = settings.web_search_auto_fetch_chars

            relevant_items = [
                it for it in raw_items
                if it.get("href") and not _is_skip_domain(it["href"])
            ]
            fetch_count = min(settings.web_search_auto_fetch_max + 1, len(relevant_items))
            regular_urls = [it["href"] for it in relevant_items[:fetch_count]]

            probe_urls = _build_year_probe_urls(raw_items, year, keywords_expanded)
            all_urls = regular_urls + [u for u in probe_urls if u not in regular_urls]

            if all_urls:
                tasks = [_fetch_page_with_meta(u, char_limit) for u in all_urls]
                fetch_results = await asyncio.gather(*tasks)

                discovered_links: list[str] = []
                fetched_urls: set[str] = set(all_urls)
                probe_set = set(probe_urls)

                for url, (page_text, page_title, raw_html) in zip(all_urls, fetch_results):
                    if not page_text:
                        continue
                    is_probe = url in probe_set
                    is_relevant = _relevance_score(
                        {"title": page_title or "", "body": page_text[:500], "href": url},
                        keywords_expanded,
                    ) >= 0.3
                    if is_probe or is_relevant:
                        probed_pages.append((url, page_title, page_text))

                    header = f"\n=== {'LATEST' if is_probe else 'PAGE'}: {url}"
                    if page_title:
                        header += f" ({page_title})"
                    header += " ==="
                    sections.append(header)
                    sections.append(page_text)

                    if raw_html:
                        outbound = _extract_outbound_links(
                            raw_html, _domain_of(url), keywords_expanded
                        )
                        for link in outbound:
                            if link not in fetched_urls:
                                discovered_links.append(link)
                                fetched_urls.add(link)

                # Phase 5: Follow the best discovered outbound links
                if discovered_links:
                    follow_urls = discovered_links[:3]
                    follow_tasks = [_fetch_page_with_meta(u, char_limit) for u in follow_urls]
                    follow_results = await asyncio.gather(*follow_tasks)

                    for url, (page_text, page_title, _) in zip(follow_urls, follow_results):
                        if not page_text:
                            continue
                        probed_pages.append((url, page_title, page_text))
                        header = f"\n=== DISCOVERED: {url}"
                        if page_title:
                            header += f" ({page_title})"
                        header += " ==="
                        sections.append(header)
                        sections.append(page_text)

        answer_data = _build_answer_summary(raw_items, key_facts, probed_pages, keywords_expanded)
        sections.insert(0, answer_data)

        sections.append(
            "\n--- Use the ANSWER DATA at the top for your response. "
            "Format links as [text](url). Do NOT search again. ---"
        )

        return ToolResult(ok=True, data="\n".join(sections))
