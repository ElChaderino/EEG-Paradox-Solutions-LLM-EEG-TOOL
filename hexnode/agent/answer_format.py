"""Normalize final `answer` text for end users (HUD / API)."""
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

import ast
import json
import re
from typing import Any

_REACT_KEYS = frozenset({"thought", "action", "action_input", "answer", "confidence"})
_FENCE = re.compile(r"^```(?:json)?\s*([\s\S]*?)```\s*$", re.MULTILINE | re.DOTALL)

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")
_BARE_URL_RE = re.compile(r"(?<!\()(https?://\S+?)(?=[)\s,;]|$)")


def _unwrap_fences(text: str) -> str:
    t = text.strip()
    m = _FENCE.match(t)
    if m:
        return m.group(1).strip()
    return t


def _dict_to_markdown(obj: dict[str, Any], depth: int = 0) -> str:
    lines: list[str] = []
    for key, val in obj.items():
        title = str(key).replace("_", " ").strip()
        if title:
            title = title[0].upper() + title[1:] if len(title) > 1 else title.upper()
        if depth == 0:
            lines.append(f"## {title}\n")
        else:
            lines.append(f"**{title}**\n")
        if isinstance(val, list):
            for x in val:
                sx = str(x).strip()
                if sx:
                    lines.append(f"- {sx}")
        elif isinstance(val, dict):
            lines.append(_dict_to_markdown(val, depth + 1))
        else:
            st = str(val).strip()
            if st:
                lines.append(st)
        lines.append("")
    return "\n".join(lines).strip()


def _looks_like_react_payload(d: dict[str, Any]) -> bool:
    return bool(_REACT_KEYS & set(d.keys()))


def _try_literal_dict(s: str) -> dict[str, Any] | None:
    s = s.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return None
    try:
        obj = ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return None
    return obj if isinstance(obj, dict) else None


def _try_json_dict(s: str) -> dict[str, Any] | None:
    s = s.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return None
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _validate_urls(text: str, known_urls: set[str] | None = None) -> str:
    """Strip URLs that weren't seen in tool observations (likely fabricated)."""
    if known_urls is None:
        return text

    def _check_md_link(m: re.Match) -> str:
        url = m.group(2)
        if _url_in_known(url, known_urls):
            return m.group(0)
        return m.group(1)

    text = _MD_LINK_RE.sub(_check_md_link, text)
    return text


def _url_in_known(url: str, known: set[str]) -> bool:
    """Check if url (or its domain) appears in the known set."""
    if url in known:
        return True
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    for k in known:
        if domain in k.lower():
            return True
    return False


def _clean_raw_json_leak(text: str) -> str:
    """If the answer contains raw JSON keys like 'thought:', 'action:', strip them."""
    if '"thought"' in text and '"action"' in text:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "answer" in obj:
                return str(obj["answer"])
        except json.JSONDecodeError:
            pass
    return text


def format_answer_for_user(text: str, known_urls: set[str] | None = None) -> str:
    """If the model returned a dict/JSON blob as the answer, render it as Markdown.
    Optionally validates URLs against a known set from tool observations."""
    if not text or not str(text).strip():
        return text
    raw = str(text).strip()

    raw = _clean_raw_json_leak(raw)
    candidate = _unwrap_fences(raw)

    for parse in (_try_literal_dict, _try_json_dict):
        obj = parse(candidate)
        if obj and not _looks_like_react_payload(obj):
            result = _dict_to_markdown(obj)
            return _validate_urls(result, known_urls)

    return _validate_urls(raw, known_urls)
