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

import re
import uuid
from typing import Any

import httpx

from hexnode.agent.answer_format import format_answer_for_user
from hexnode.agent.script_workspace import build_script_workspace
from hexnode.agent.prompts import build_system_prompt, format_observation, skye_escalation_prompt
from hexnode.config import settings
from hexnode.memory_store import MemoryStore
from hexnode.ollama_client import OllamaClient
from hexnode.reflection import read_current_focus
from hexnode.symbolic.rules import load_symbolic_hints
from hexnode.tools.base import ToolContext
from hexnode.tools.registry import get_registry


def _extract_fallback_answer(obs_text: str, user_question: str) -> str:
    """Last-resort: pull key facts from collected observations into a basic answer."""
    lines: list[str] = []
    events: list[str] = []
    details: list[str] = []
    dates: set[str] = set()
    locations: set[str] = set()
    urls: set[str] = set()
    links: list[str] = []

    for m in re.finditer(r"Event:\s*(.+)", obs_text):
        events.append(m.group(1).strip())
    for m in re.finditer(r"Detail:\s*(.+)", obs_text):
        details.append(m.group(1).strip())
    for m in re.finditer(r"Link:\s*(https?://\S+)", obs_text):
        urls.add(m.group(1).strip())
    for m in re.finditer(
        r"(?:Date(?:\s+mentioned)?)\s*:\s*(.+)", obs_text, re.IGNORECASE
    ):
        dates.add(m.group(1).strip())
    for m in re.finditer(
        r"(?:Location|Address)(?:\s+mentioned)?\s*:\s*(.+)", obs_text, re.IGNORECASE
    ):
        locations.add(m.group(1).strip())
    for m in re.finditer(r"URL:\s*(https?://\S+)", obs_text):
        urls.add(m.group(1).strip())
    for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", obs_text):
        links.append(f"[{m.group(1)}]({m.group(2)})")
        urls.add(m.group(2))

    if events:
        lines.append(f"**{events[0]}**\n")
    for d in details[:3]:
        if d not in (events[0] if events else ""):
            lines.append(f"- {d}")

    if dates:
        lines.append(f"- **Dates mentioned**: {', '.join(sorted(dates))}")
    if locations:
        lines.append(f"- **Location**: {', '.join(sorted(locations))}")

    if urls:
        top_url = sorted(urls)[0]
        event_name = events[0].split(" - ")[0] if events else "Event Website"
        lines.append(f"\nMore info: [{event_name}]({top_url})")
    for lnk in links[:2]:
        if lnk not in "\n".join(lines):
            lines.append(lnk)

    if lines:
        return "\n".join(lines)

    return (
        "I searched but could not extract specific details. "
        "Try checking the event's official website directly."
    )


def _clip_assistant_content(text: str) -> str:
    text = OllamaClient.strip_thinking(text)
    cap = max(500, settings.agent_assistant_message_max_chars)
    if len(text) <= cap:
        return text
    return text[: cap - 40] + "\n...[truncated for context]"


def _normalize_action(action: Any) -> str | None:
    if action is None:
        return None
    s = str(action).strip()
    if not s or s.lower() in ("null", "none"):
        return None
    return s


_ROUTE_PROMPT = (
    "Classify this user message. Reply with EXACTLY one word:\n"
    "- DIRECT if you can answer from general knowledge (no web search, no tools needed)\n"
    "- AGENT if it needs a web search, research, file analysis, current events, or specific data\n\n"
    "Message: {msg}\n\nClassification:"
)


async def _route_query(ollama: OllamaClient, user_message: str) -> str:
    """Use the fast model to classify whether a query needs the full agent loop."""
    fast = (settings.fast_model or "").strip()
    if not fast:
        return "agent"
    try:
        raw = await ollama.chat(
            fast,
            [{"role": "user", "content": _ROUTE_PROMPT.format(msg=user_message)}],
            temperature=0.0,
            format_json=False,
        )
        clean = OllamaClient.strip_thinking(raw).strip().upper()
        if "DIRECT" in clean:
            return "direct"
        return "agent"
    except Exception:
        return "agent"


async def _fast_answer(
    ollama: OllamaClient, user_message: str, trace_id: str
) -> dict[str, Any] | None:
    """Try to answer a simple query with the fast model. Returns None if it can't."""
    fast = (settings.fast_model or "").strip()
    if not fast:
        return None
    try:
        raw = await ollama.chat(
            fast,
            [
                {
                    "role": "system",
                    "content": (
                        "You are Paradox, a helpful AI research assistant by Paradox Solutions LLM. Answer concisely in Markdown. "
                        "Format links as [text](url). Be accurate and confident."
                    ),
                },
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            format_json=False,
        )
        answer = OllamaClient.strip_thinking(raw).strip()
        if not answer:
            return None
        return {
            "answer": answer,
            "confidence": 0.85,
            "steps": [{"step": 1, "thought": "fast-model direct answer", "action": None, "confidence": 0.85, "parse_ok": True}],
            "trace_id": trace_id,
            "escalated_skye": False,
            "symbolic_hints": None,
            "react_version": "v2-fast",
            "script_workspace": build_script_workspace(answer, []),
        }
    except Exception:
        return None


async def run_agent(
    user_message: str,
    memory: MemoryStore,
    ollama: OllamaClient,
    interface: str = "api",
) -> dict[str, Any]:
    trace_id = str(uuid.uuid4())[:8]

    route = await _route_query(ollama, user_message)
    if route == "direct":
        fast_result = await _fast_answer(ollama, user_message, trace_id)
        if fast_result:
            await memory.add_text(
                "chat_history",
                f"User ({interface}): {user_message}\nParadox: {fast_result['answer']}",
                memory_type="chat",
                importance=0.55,
                extra_meta={"interface": interface, "trace_id": trace_id, "fast": True},
            )
            return fast_result

    registry = get_registry()
    specs = registry.tool_specs()
    symbolic_block = load_symbolic_hints(user_message, settings)
    system = build_system_prompt(specs, read_current_focus(), symbolic_suffix=symbolic_block)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]

    transcript_parts: list[str] = []
    steps: list[dict[str, Any]] = []
    observed_urls: set[str] = set()
    final_answer = ""
    confidence = 0.0
    escalated_skye = False
    tool_call_counts: dict[str, int] = {}

    ctx = ToolContext(memory=memory, ollama=ollama, settings=settings, trace_id=trace_id)

    model = settings.chat_model

    for step in range(settings.agent_max_steps):
        if step == settings.agent_max_steps - 1:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "ReAct budget: final step. You MUST provide your best answer now. "
                        "Output JSON with action null, your answer (even if uncertain), and "
                        "calibrated confidence (0-1). Do NOT call another tool."
                    ),
                }
            )

        raw = await ollama.chat(model, messages, temperature=0.2, format_json=True)
        data = OllamaClient.parse_json_loose(raw)
        parse_ok = bool(data)
        if not data:
            data = {
                "thought": raw[:500],
                "action": None,
                "action_input": {},
                "answer": raw,
                "confidence": 0.4,
            }

        thought = str(data.get("thought", ""))
        action = _normalize_action(data.get("action"))
        action_input = data.get("action_input") or {}
        answer = data.get("answer")
        conf = float(data.get("confidence") or 0.0)

        step_rec: dict[str, Any] = {
            "step": step + 1,
            "thought": thought,
            "action": action,
            "confidence": conf,
            "parse_ok": parse_ok,
        }

        if action:
            tool_call_counts[action] = tool_call_counts.get(action, 0) + 1

            if tool_call_counts[action] >= 2:
                step_rec["action"] = None
                step_rec["note"] = f"tool {action} called {tool_call_counts[action]}x, hard stop"
                steps.append(step_rec)
                search_obs = "\n".join(
                    s.get("observation", "") for s in steps
                    if s.get("action") == "web_search" and s.get("tool_ok")
                )
                if search_obs.strip():
                    final_answer = _extract_fallback_answer(search_obs, user_message)
                    confidence = 0.7
                break

            if not isinstance(action_input, dict):
                action_input = {}
            if action == "run_python_analysis":
                sc = action_input.get("script")
                if isinstance(sc, str) and sc.strip():
                    step_rec["python_script"] = sc[:80000]
            result = await registry.run(str(action), ctx, action_input)
            step_rec["tool_ok"] = result.ok
            if not result.ok:
                step_rec["tool_error"] = (result.error or "")[:500]
            obs = format_observation(str(action), result.data if result.ok else result.error)
            step_rec["observation"] = obs[:4000]
            for url_match in re.finditer(r"https?://\S+", obs):
                observed_urls.add(url_match.group(0).rstrip(".,;)>"))

            transcript_parts.append(f"Step {step+1}: {thought}\n{obs}\n")
            messages.append({"role": "assistant", "content": _clip_assistant_content(raw)})

            result_str = str(result.data or "")
            no_results = "(no results)" in result_str or "(no hits)" in result_str
            has_answer_data = ">>> ANSWER DATA" in result_str

            if no_results:
                obs_msg = (
                    "Observation: No results found. Provide your best answer with "
                    "honest uncertainty. Do NOT search again."
                )
            elif has_answer_data:
                ad_start = result_str.find(">>> ANSWER DATA")
                ad_end = result_str.find(">>> END ANSWER DATA <<<")
                if ad_start >= 0 and ad_end > ad_start:
                    answer_block = result_str[ad_start:ad_end + len(">>> END ANSWER DATA <<<")]
                    obs_msg = (
                        f"Search complete. Write your answer using this data:\n\n"
                        f"{answer_block}\n\n"
                        f"INSTRUCTIONS: Set action=null. Write the answer field as Markdown "
                        f"with [clickable links](url). Set confidence=0.85. "
                        f"Do NOT call web_search again."
                    )
                else:
                    obs_msg = f"Observation:\n{obs}"
            else:
                obs_msg = f"Observation:\n{obs}"
            messages.append({"role": "user", "content": obs_msg})
            steps.append(step_rec)
            continue

        if answer is not None and str(answer).strip() != "":
            final_answer = str(answer)
            confidence = conf
            steps.append(step_rec)
            transcript_parts.append(f"Step {step+1}: {thought}\nAnswer: {final_answer}\n")
            if conf >= settings.confidence_threshold:
                break
            messages.append({"role": "assistant", "content": _clip_assistant_content(raw)})
            messages.append(
                {
                    "role": "user",
                    "content": "Either raise confidence with evidence/tools or provide your best answer with honest uncertainty.",
                }
            )
            continue

        if conf > 0.5 and thought.strip():
            final_answer = thought
            confidence = conf
            steps.append(step_rec)
            break

        messages.append({"role": "assistant", "content": _clip_assistant_content(raw)})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Your answer field was empty. Put your answer text in the 'answer' field, "
                    "not in 'thought'. Output valid JSON with action=null and a non-empty answer."
                ),
            }
        )
        steps.append(step_rec)

    if not final_answer:
        searched = any(s.get("action") == "web_search" for s in steps)
        search_obs = [
            s.get("observation", "") for s in steps
            if s.get("action") == "web_search" and s.get("tool_ok")
        ]
        combined_obs = "\n".join(search_obs)
        if searched and combined_obs.strip():
            final_answer = _extract_fallback_answer(combined_obs, user_message)
            confidence = 0.5
        elif searched:
            final_answer = (
                "I searched for this but could not find specific, verified information. "
                "This may be a niche or local event. Try checking the event's official "
                "website directly for the latest schedule."
            )
            confidence = 0.3
        else:
            final_answer = (
                "I was unable to determine a confident answer within the available steps. "
                "Try rephrasing your question or asking me to search the web for it."
            )
            confidence = 0.2

    if confidence < settings.confidence_threshold and (settings.skye_url or "").strip():
        escalated_skye = True
        prompt = skye_escalation_prompt(user_message, "\n".join(transcript_parts))
        async with httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=30.0)) as client:
            r = await client.post(
                f"{settings.skye_url.rstrip('/')}/api/generate",
                json={
                    "model": settings.skye_model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            if r.status_code == 200:
                final_answer = r.json().get("response", final_answer)
                confidence = max(confidence, 0.55)

    final_answer = format_answer_for_user(final_answer, known_urls=observed_urls or None)

    await memory.add_text(
        "chat_history",
        f"User ({interface}): {user_message}\nParadox: {final_answer}",
        memory_type="chat",
        importance=0.55,
        extra_meta={"interface": interface, "trace_id": trace_id, "skye": escalated_skye},
    )

    return {
        "answer": final_answer,
        "confidence": confidence,
        "steps": steps,
        "trace_id": trace_id,
        "escalated_skye": escalated_skye,
        "symbolic_hints": symbolic_block.strip() or None,
        "react_version": "v2",
        "script_workspace": build_script_workspace(final_answer, steps),
    }
