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

import math
import uuid
from datetime import datetime, timezone
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from hexnode.config import settings
from hexnode.embed_quantize import quantize_embedding
from hexnode.ollama_client import OllamaClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_utc(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def recency_score(last_iso: str | None, half_life_days: float) -> float:
    """Exponential decay from last_accessed; 0.5 if unknown. half_life_days<=0 → neutral 0.5."""
    if half_life_days <= 0:
        return 0.5
    dt = _parse_iso_utc(last_iso)
    if not dt:
        return 0.5
    age_days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
    return math.exp(-age_days / half_life_days)


def blend_memory_score(
    sim: float,
    importance: float,
    recency: float,
    boost: float,
    s: Any,
) -> tuple[float, dict[str, float]]:
    w = (float(s.memory_w_sim), float(s.memory_w_imp), float(s.memory_w_rec), float(s.memory_w_boost))
    tw = sum(w) or 1.0
    w = tuple(x / tw for x in w)
    score = w[0] * sim + w[1] * importance + w[2] * recency + w[3] * boost
    components = {
        "similarity": sim,
        "importance": importance,
        "recency": recency,
        "manual_boost": boost,
        "weight_sim": w[0],
        "weight_imp": w[1],
        "weight_rec": w[2],
        "weight_boost": w[3],
    }
    return score, components


COLLECTIONS = ("chat_history", "documents", "library")


class MemoryStore:
    def __init__(self, ollama: OllamaClient) -> None:
        settings.chroma_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(settings.chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collections: dict[str, Any] = {}
        for name in COLLECTIONS:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"description": f"Paradox {name}"},
            )
        self._ollama = ollama

    def collection(self, name: str):
        if name not in self._collections:
            raise ValueError(f"Unknown collection: {name}")
        return self._collections[name]

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding and optionally quantize for storage compression."""
        raw = await self._ollama.embed(text)
        return quantize_embedding(raw)

    async def add_text(
        self,
        collection_name: str,
        text: str,
        memory_type: str,
        importance: float = 0.5,
        extra_meta: dict[str, Any] | None = None,
    ) -> str:
        coll = self.collection(collection_name)
        _id = str(uuid.uuid4())
        emb = await self._embed(text)
        meta: dict[str, Any] = {
            "memory_type": memory_type,
            "importance": importance,
            "access_count": 0,
            "last_accessed": _now_iso(),
            "manual_boost": 0.0,
            "created": _now_iso(),
        }
        if extra_meta:
            meta.update({k: v for k, v in extra_meta.items() if k not in meta})
        coll.add(ids=[_id], documents=[text], embeddings=[emb], metadatas=[meta])
        return _id

    async def query(
        self,
        collection_name: str | None,
        query_text: str,
        top_k: int | None = None,
        memory_type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        k = top_k or settings.memory_search_top_k
        emb = await self._embed(query_text)
        half_life = float(settings.memory_recency_half_life_days)

        def run_one(name: str) -> list[dict[str, Any]]:
            coll = self.collection(name)
            raw = coll.query(
                query_embeddings=[emb],
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )
            out: list[dict[str, Any]] = []
            ids = raw.get("ids") or [[]]
            docs = raw.get("documents") or [[]]
            metas = raw.get("metadatas") or [[]]
            dists = raw.get("distances") or [[]]
            for i, _id in enumerate(ids[0]):
                md = dict(metas[0][i] or {})
                dist = float(dists[0][i]) if dists and dists[0] else 1.0
                imp = float(md.get("importance", 0.5))
                boost = float(md.get("manual_boost", 0.0))
                sim = 1.0 / (1.0 + dist)
                last = md.get("last_accessed") or md.get("created")
                rec = recency_score(str(last) if last else None, half_life)
                score, components = blend_memory_score(sim, imp, rec, boost, settings)
                out.append(
                    {
                        "id": _id,
                        "document": (docs[0][i] if docs and docs[0] else "") or "",
                        "metadata": md,
                        "distance": dist,
                        "score": score,
                        "score_components": components,
                        "collection": name,
                    }
                )
            return out

        targets = [collection_name] if collection_name else list(COLLECTIONS)
        merged: list[dict[str, Any]] = []
        for name in targets:
            merged.extend(run_one(name))

        if memory_type_filter:
            merged = [m for m in merged if m["metadata"].get("memory_type") == memory_type_filter]

        merged.sort(key=lambda x: -x["score"])
        return merged[:k]

    def touch_ids(self, hits: list[dict[str, Any]]) -> None:
        for h in hits:
            coll = self.collection(h["collection"])
            _id = h["id"]
            try:
                existing = coll.get(ids=[_id], include=["metadatas"])
                meta = (existing.get("metadatas") or [[]])[0]
                if not meta:
                    continue
                m = dict(meta[0])
                m["access_count"] = int(m.get("access_count", 0)) + 1
                m["last_accessed"] = _now_iso()
                m["importance"] = min(1.0, float(m.get("importance", 0.5)) + 0.02)
                coll.update(ids=[_id], metadatas=[m])
            except Exception:
                continue

    def boost_memory(self, memory_id: str, collection_name: str, amount: float) -> bool:
        coll = self.collection(collection_name)
        try:
            existing = coll.get(ids=[memory_id], include=["metadatas"])
            meta = (existing.get("metadatas") or [[]])[0]
            if not meta:
                return False
            m = dict(meta[0])
            m["manual_boost"] = min(1.0, float(m.get("manual_boost", 0.0)) + amount)
            m["importance"] = min(1.0, float(m.get("importance", 0.5)) + amount * 0.5)
            coll.update(ids=[memory_id], metadatas=[m])
            return True
        except Exception:
            return False
