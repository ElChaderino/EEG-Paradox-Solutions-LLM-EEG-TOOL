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
from pathlib import Path
from typing import Any

from hexnode.config import settings
from hexnode.tools.base import Tool, ToolContext, ToolResult


def _chunk_text(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + size])
        i += size - overlap
    return chunks


_EEG_EXTENSIONS = frozenset({".edf", ".bdf"})


def _extract_edf_header(path: Path) -> str:
    """Extract structured metadata from EDF/BDF files as readable text."""
    try:
        import pyedflib

        f = pyedflib.EdfReader(str(path))
        try:
            n_ch = f.signals_in_file
            duration = f.file_duration
            ch_names = f.getSignalLabels()
            sfreqs = [f.getSampleFrequency(i) for i in range(n_ch)]
            patient = f.getPatientName() or "(unknown)"
            rec_date = f.getStartdatetime()
            lines = [
                f"EEG Recording: {path.name}",
                f"Format: {path.suffix.upper().strip('.')}",
                f"Patient: {patient}",
                f"Recorded: {rec_date}",
                f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)",
                f"Channels ({n_ch}):",
            ]
            for i, ch in enumerate(ch_names):
                sf = sfreqs[i] if i < len(sfreqs) else 0
                lines.append(f"  - {ch} ({sf:.0f} Hz)")
            unique_sr = sorted(set(int(s) for s in sfreqs))
            lines.append(f"Sample rates: {', '.join(str(s) + ' Hz' for s in unique_sr)}")
            return "\n".join(lines)
        finally:
            f.close()
    except ImportError:
        pass

    try:
        import mne

        raw = mne.io.read_raw_edf(str(path), preload=False, verbose=False) if path.suffix.lower() == ".edf" else mne.io.read_raw_bdf(str(path), preload=False, verbose=False)
        info = raw.info
        lines = [
            f"EEG Recording: {path.name}",
            f"Format: {path.suffix.upper().strip('.')}",
            f"Duration: {raw.n_times / info['sfreq']:.1f} seconds",
            f"Sample rate: {info['sfreq']:.0f} Hz",
            f"Channels ({info['nchan']}): {', '.join(info['ch_names'][:32])}",
        ]
        if info["nchan"] > 32:
            lines[-1] += f" ... and {info['nchan'] - 32} more"
        return "\n".join(lines)
    except (ImportError, Exception):
        pass

    return f"EEG file: {path.name} ({path.suffix.upper().strip('.')}, {path.stat().st_size / 1024:.0f} KB)"


async def ingest_file_path(path: Path, ctx: ToolContext, source_label: str) -> int:
    suffix = path.suffix.lower()
    raw = ""

    if suffix in _EEG_EXTENSIONS:
        header_text = _extract_edf_header(path)
        await ctx.memory.add_text(
            "library",
            header_text,
            memory_type="eeg_recording",
            importance=0.6,
            extra_meta={"source": source_label, "filename": path.name, "format": suffix.strip(".")},
        )
        return 1

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            for page in reader.pages:
                raw += (page.extract_text() or "") + "\n"
        except Exception as e:
            raise RuntimeError(f"PDF read failed: {e}") from e
    else:
        raw = path.read_text(encoding="utf-8", errors="replace")

    n = 0
    for chunk in _chunk_text(raw):
        await ctx.memory.add_text(
            "library",
            chunk,
            memory_type="ingested_doc",
            importance=0.45,
            extra_meta={"source": source_label, "filename": path.name},
        )
        n += 1
    return n


class IngestDocumentTool(Tool):
    name = "ingest_document"
    description = (
        "Ingest text into library memory from a local path or URL. "
        "Params: path_or_url (str). Paths are under data/ or absolute; URLs use fetch+extract."
    )

    async def run(self, ctx: ToolContext, path_or_url: str = "", **_: Any) -> ToolResult:
        if not path_or_url.strip():
            return ToolResult(ok=False, data=None, error="path_or_url is required")
        s = path_or_url.strip()
        if s.startswith("http://") or s.startswith("https://"):
            from hexnode.tools.fetch_url import FetchUrlTool

            fetch = FetchUrlTool()
            fr = await fetch.run(ctx, url=s)
            if not fr.ok:
                return fr
            text = str(fr.data or "")
            n = 0
            for chunk in _chunk_text(text):
                await ctx.memory.add_text(
                    "library",
                    chunk,
                    memory_type="ingested_url",
                    importance=0.45,
                    extra_meta={"source": s},
                )
                n += 1
            return ToolResult(ok=True, data=f"Ingested {n} chunks from URL")

        p = Path(s).expanduser()
        if not p.is_file():
            cand = settings.ingest_queue / s
            if cand.is_file():
                p = cand
        if not p.is_file():
            return ToolResult(ok=False, data=None, error=f"File not found: {s}")
        try:
            n = await ingest_file_path(p, ctx, str(p))
        except Exception as e:
            return ToolResult(ok=False, data=None, error=str(e))
        return ToolResult(ok=True, data=f"Ingested {n} chunks from {p.name}")

