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
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from hexnode.config import settings
from hexnode.ollama_client import OllamaClient

if TYPE_CHECKING:
    from hexnode.memory_store import MemoryStore


async def sample_collection(memory: MemoryStore, name: str, query: str, k: int) -> str:
    hits = await memory.query(name, query, top_k=k)
    lines = []
    for h in hits:
        lines.append(h.get("document", "")[:600])
    return "\n".join(lines)


ROUND_A = [
    ("chat_history", "recent activity patterns user preferences"),
    ("documents", "setup knowledge reflections and focus"),
    ("library", "ingested facts sources and documents"),
]

ROUND_B = [
    ("chat_history", "unresolved questions mistakes or confusion"),
    ("documents", "contradictions or stale information"),
    ("library", "important technical facts worth reinforcing"),
]


async def _build_bundle(memory: MemoryStore) -> str:
    parts: list[str] = []
    for coll, q in ROUND_A:
        text = await sample_collection(memory, coll, q, 5)
        parts.append(f"## {coll}\n{text}")
    mid = "\n\n".join(parts)[:8000]
    parts_b: list[str] = []
    for coll, q in ROUND_B:
        text = await sample_collection(memory, coll, q, 4)
        parts_b.append(f"## {coll}\n{text}")
    tail = "\n\n".join(parts_b)[:8000]
    return f"{mid}\n\n--- DIVERSITY PASS ---\n\n{tail}"


def _latest_reflection_excerpt() -> str:
    try:
        settings.reflections_dir.mkdir(parents=True, exist_ok=True)
        paths = sorted(settings.reflections_dir.glob("reflection_*.md"))
        if not paths:
            return ""
        return paths[-1].read_text(encoding="utf-8", errors="replace")[:3500]
    except Exception:
        return ""


async def run_reflection_pass(memory: MemoryStore, ollama: OllamaClient) -> str:
    settings.reflections_dir.mkdir(parents=True, exist_ok=True)
    settings.vault_path.mkdir(parents=True, exist_ok=True)

    bundle = (await _build_bundle(memory))[:16000]
    prev = _latest_reflection_excerpt() if settings.reflection_compare_previous else ""
    compare_block = ""
    if prev.strip():
        compare_block = (
            "\n\n## Previous reflection on disk (summarize deltas, not repetition)\n"
            f"{prev}\n"
        )

    system = (
        "You are Paradox's reflection engine. Output concise JSON only with keys: "
        "summary (string), patterns (array of strings), gaps (array of strings), "
        "next_focus (string), confidence (number 0-1), deltas_from_previous (string, empty if none)."
    )
    prompt = f"Memory samples:\n{bundle}{compare_block}\n\nReflect on patterns, gaps, and what changed since the prior reflection if excerpt provided. JSON only."
    raw = await ollama.generate(settings.chat_model, prompt, system=system, format_json=True)
    data = OllamaClient.parse_json_loose(raw)
    if not data:
        data = {
            "summary": raw[:2000],
            "patterns": [],
            "gaps": [],
            "next_focus": "",
            "confidence": 0.3,
            "deltas_from_previous": "",
        }

    conf = float(data.get("confidence") or 0.0)
    min_c = float(settings.reflection_min_confidence)
    low_conf = conf < min_c

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    md_path = settings.reflections_dir / f"reflection_{ts}.md"

    deltas = str(data.get("deltas_from_previous") or "").strip()
    body_core = (
        f"# Reflection {ts}\n\n## Summary\n{data.get('summary', '')}\n\n"
        f"## Model confidence\n{conf:.2f} (min configured {min_c:.2f})\n\n"
        f"## Patterns\n"
        + "\n".join(f"- {p}" for p in data.get("patterns") or [])
        + "\n\n## Gaps\n"
        + "\n".join(f"- {g}" for g in data.get("gaps") or [])
        + f"\n\n## Next focus\n{data.get('next_focus', '')}\n"
    )
    if deltas:
        body_core += f"\n## Deltas from previous\n{deltas}\n"
    if low_conf:
        body_core += (
            "\n## Note\nLow-confidence pass: treat as tentative; operator may re-run after more data.\n"
        )

    md_path.write_text(body_core, encoding="utf-8")

    focus_text = str(data.get("next_focus") or data.get("summary") or "")[:8000]
    if low_conf and len(focus_text.strip()) < 80:
        try:
            if settings.current_focus_file.is_file():
                focus_text = settings.current_focus_file.read_text(encoding="utf-8", errors="replace")[:8000]
        except Exception:
            pass
    settings.current_focus_file.write_text(focus_text, encoding="utf-8")

    reflect_text = json.dumps(data, indent=2)[:6000]
    imp = 0.45 if low_conf else 0.7
    await memory.add_text(
        "documents",
        reflect_text,
        memory_type="reflection",
        importance=imp,
        extra_meta={
            "kind": "nightly_reflection",
            "path": str(md_path),
            "reflection_confidence": conf,
            "low_confidence_flag": 1 if low_conf else 0,
        },
    )
    status = "tentative" if low_conf else "committed"
    return f"Reflection ({status}) written to {md_path.name}; current_focus updated."


def read_current_focus() -> str:
    try:
        if settings.current_focus_file.is_file():
            return settings.current_focus_file.read_text(encoding="utf-8", errors="replace")[:4000]
    except Exception:
        pass
    return ""
