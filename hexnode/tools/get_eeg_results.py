"""Tool: retrieve the latest EEG pipeline results for LLM interpretation.

Returns metrics, clinical findings, and band power from the most recent
(or a specified) processing job — no LLM compute needed to run the analysis,
just reads the pre-computed JSON outputs.
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


from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hexnode.config import settings
from hexnode.tools.base import Tool, ToolContext, ToolResult


class GetEegResultsTool(Tool):
    name = "get_eeg_results"
    required_feature = "eeg"
    description = (
        "Retrieve pre-computed EEG analysis results from a completed processing job. "
        "Returns pipeline metrics, clinical Q findings (Swingle protocol), band power, "
        "and report text. Params: "
        "job_id (str, optional — defaults to most recent job; pass 'list' to list all jobs), "
        "include (str, optional — 'all', 'metrics', 'clinical', 'bandpower'; default 'all')."
    )

    async def run(
        self,
        ctx: ToolContext,
        job_id: str = "",
        include: str = "all",
        **_: Any,
    ) -> ToolResult:
        out_dir = settings.eeg_workspace / "output"
        if not out_dir.is_dir():
            return ToolResult(ok=False, data=None, error="No EEG output directory found")

        if job_id == "list":
            jobs = []
            for d in sorted(out_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if not d.is_dir():
                    continue
                meta_path = d / "_job.json"
                if meta_path.is_file():
                    try:
                        meta = json.loads(meta_path.read_text("utf-8"))
                        jobs.append({
                            "id": meta.get("id", d.name),
                            "filename": meta.get("filename", ""),
                            "status": meta.get("status", "unknown"),
                            "started": meta.get("started", ""),
                        })
                    except Exception:
                        jobs.append({"id": d.name, "status": "unknown"})
                else:
                    jobs.append({"id": d.name, "status": "unknown"})
            return ToolResult(ok=True, data={"jobs": jobs, "count": len(jobs)})

        if job_id:
            job_dir = out_dir / job_id
            if not job_dir.is_dir():
                return ToolResult(ok=False, data=None, error=f"Job {job_id} not found")
        else:
            subdirs = sorted(
                [d for d in out_dir.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
            if not subdirs:
                json_files = sorted(out_dir.glob("*_metrics.json"), key=lambda f: f.stat().st_mtime, reverse=True)
                if json_files:
                    job_dir = out_dir
                else:
                    return ToolResult(ok=False, data=None, error="No completed EEG jobs found. Ask the user to upload an EDF via the EEG Data tab first.")
            else:
                job_dir = subdirs[0]

        results: dict[str, Any] = {"job_id": job_dir.name}
        found_any = False

        if include in ("all", "metrics"):
            for mf in job_dir.glob("*_metrics.json"):
                try:
                    results["pipeline_metrics"] = json.loads(mf.read_text("utf-8"))
                    found_any = True
                    break
                except Exception:
                    pass

        if include in ("all", "clinical"):
            for cf in job_dir.glob("*_clinicalq.json"):
                try:
                    cdata = json.loads(cf.read_text("utf-8"))
                    findings = cdata.get("findings", [])
                    flagged = [f for f in findings if f.get("significant")]
                    results["clinical_q"] = {
                        "total_checks": len(findings),
                        "flagged": len(flagged),
                        "findings": findings,
                    }
                    found_any = True
                    break
                except Exception:
                    pass

        if include in ("all", "bandpower"):
            for bf in job_dir.glob("*_band_power.json"):
                try:
                    bdata = json.loads(bf.read_text("utf-8"))
                    summary: dict[str, Any] = {}
                    for ch, bands in bdata.items():
                        if isinstance(bands, dict):
                            summary[ch] = {
                                b: round(v.get("amp_uV", 0), 2)
                                for b, v in bands.items()
                                if isinstance(v, dict)
                            }
                    results["band_power"] = summary
                    found_any = True
                    break
                except Exception:
                    pass

        for rf in job_dir.glob("*_report.txt"):
            try:
                results["report_summary"] = rf.read_text("utf-8")[:2000]
                found_any = True
                break
            except Exception:
                pass

        output_files = sorted(
            f.name for f in job_dir.iterdir()
            if f.is_file() and not f.name.startswith("_")
        )
        results["output_files"] = output_files

        if not found_any:
            results["note"] = "Job directory exists but no analysis outputs found — the job may still be processing."

        return ToolResult(ok=True, data=results)
