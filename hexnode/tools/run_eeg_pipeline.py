"""Tool: run a full EEG preprocessing + analysis pipeline on a recording file.

Generates a complete 24-step MNE-Python pipeline script from
``hexnode.eeg.pipeline``, executes it in the venv subprocess,
and returns the structured results (quality metrics, step status, output files).
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
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from hexnode.config import settings
from hexnode.eeg.pipeline import PipelineConfig, generate_pipeline_script
from hexnode.tools.base import Tool, ToolContext, ToolResult

_CREATION_FLAGS = (
    subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
)


class RunEegPipelineTool(Tool):
    name = "run_eeg_pipeline"
    required_feature = "eeg"
    description = (
        "Run a full 24-step EEG preprocessing + analysis pipeline on a recording file. "
        "Produces cleaned data, ICA, ERP, spectral, connectivity, and a quality report. "
        "Params: filename (str, required — file in eeg_workspace/), "
        "hp_freq (float, 0.5), lp_freq (float, 40), notch_freq (float, 60), "
        "ica_method (str, 'fastica'), icalabel_threshold (float, 0.80), "
        "connectivity_method (str, 'coh'), "
        "connectivity_norm_csv (str, optional — overrides bundled norms), "
        "connectivity_bundled_norms (bool, default True — use shipped norms when csv empty), "
        "condition (str, EC or EO — picks eyes_closed vs eyes_open bundled connectivity norms)."
    )

    async def run(
        self,
        ctx: ToolContext,
        filename: str = "",
        hp_freq: float = 0.5,
        lp_freq: float = 40.0,
        notch_freq: float = 60.0,
        ica_method: str = "fastica",
        icalabel_threshold: float = 0.80,
        connectivity_method: str = "coh",
        connectivity_norm_csv: str = "",
        connectivity_bundled_norms: bool = True,
        condition: str = "EC",
        **_: Any,
    ) -> ToolResult:
        if not filename.strip():
            return ToolResult(ok=False, data=None, error="filename is required")

        ws = settings.eeg_workspace
        ws.mkdir(parents=True, exist_ok=True)
        out_dir = ws / "output"
        out_dir.mkdir(parents=True, exist_ok=True)

        fpath = ws / filename
        if not fpath.is_file():
            fpath = Path(filename)
        if not fpath.is_file():
            return ToolResult(
                ok=False, data=None,
                error=f"File not found: {filename} (looked in {ws} and as absolute path)",
            )

        cfg = PipelineConfig(
            input_file=str(fpath.name) if fpath.parent == ws else str(fpath),
            condition=(condition or "EC").strip(),
            hp_freq=hp_freq,
            lp_freq=lp_freq,
            notch_freq=notch_freq,
            ica_method=ica_method,
            icalabel_threshold=icalabel_threshold,
            connectivity_method=connectivity_method,
            connectivity_norm_csv=connectivity_norm_csv or "",
            connectivity_bundled_norms=connectivity_bundled_norms,
        )
        script = generate_pipeline_script(cfg)

        fd, tmp = tempfile.mkstemp(suffix=".py", prefix="hex_pipeline_", dir=str(ws))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(script)

            from hexnode.config import python_for_eeg
            timeout = max(60, settings.python_analysis_timeout * 3)
            proc = subprocess.run(
                [python_for_eeg(), tmp],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(ws),
                creationflags=_CREATION_FLAGS,
                env={**os.environ, "MPLBACKEND": "Agg"},
            )
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()

            output_parts: list[str] = []
            if stdout:
                output_parts.append(stdout[-6000:])
            if proc.returncode != 0 and stderr:
                output_parts.append(f"--- stderr (last 2000 chars) ---\n{stderr[-2000:]}")

            metrics_file = out_dir / f"{cfg.output_prefix or fpath.stem}_metrics.json"
            if metrics_file.is_file():
                try:
                    metrics = json.loads(metrics_file.read_text("utf-8"))
                    output_parts.append(
                        f"--- METRICS ---\n{json.dumps(metrics, indent=2)[:3000]}"
                    )
                except Exception:
                    pass

            new_files = sorted(f.name for f in out_dir.iterdir() if f.is_file())
            if new_files:
                output_parts.append(
                    f"--- output files ({len(new_files)}) ---\n" + "\n".join(new_files)
                )

            text = "\n\n".join(output_parts) if output_parts else "(no output)"
            return ToolResult(
                ok=proc.returncode == 0,
                data=text,
                error=f"Pipeline exited with code {proc.returncode}" if proc.returncode != 0 else None,
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                ok=False, data=None,
                error=f"Pipeline timed out after {timeout}s",
            )
        except Exception as e:
            return ToolResult(ok=False, data=None, error=str(e)[:800])
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
