"""Sandboxed Python script executor for EEG / scientific analysis.

The agent supplies a Python script string; this tool writes it to a temp file,
runs it inside the project venv interpreter with a configurable timeout, and
returns stdout + stderr.  Scripts run with cwd = ``eeg_workspace`` so they can
read/write EEG files placed there.  Plots saved to ``eeg_workspace/output/``
are listed in the result.
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

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from hexnode.config import settings
from hexnode.tools.base import Tool, ToolContext, ToolResult

_CREATION_FLAGS = (
    subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
)

_PREAMBLE = """\
import warnings as _w; _w.filterwarnings("ignore")
import matplotlib as _mpl; _mpl.use("Agg")
"""

_MAX_RETRIES = 2


def _output_dir() -> Path:
    d = settings.eeg_workspace / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _list_new_files(output_dir: Path, before: set[str]) -> list[str]:
    after = {f.name for f in output_dir.iterdir() if f.is_file()}
    return sorted(after - before)


def _apply_auto_fix(script: str, stderr: str) -> str | None:
    """Try simple automatic fixes for common errors. Returns patched script or None."""
    if "No module named 'mne_icalabel'" in stderr:
        return script.replace("from mne_icalabel", "# mne_icalabel not installed\n# from mne_icalabel")
    if "preload" in stderr and "preload=True" not in script:
        return script.replace(".get_data()", ".load_data()\n    .get_data()")
    if "channel(s) missing from info" in stderr or "set_montage" in stderr:
        return script.replace(
            'set_montage(montage)',
            'set_montage(montage, on_missing="ignore")'
        )
    return None


def _format_run_message(
    stdout: str, stderr: str, new_files: list[str]
) -> str:
    output_parts: list[str] = []
    if stdout:
        output_parts.append(stdout[:6000])
    if stderr:
        output_parts.append(f"--- stderr ---\n{stderr[:2000]}")
    if new_files:
        output_parts.append("--- new files in output/ ---\n" + "\n".join(new_files))
    return "\n\n".join(output_parts) if output_parts else "(no output)"


def execute_python_analysis_script(user_script: str) -> dict[str, Any]:
    """Run a user script under ``eeg_workspace`` (same as tool). For HTTP API + tool.

    Returns keys: ok, exit_code, stdout, stderr, new_files, message, error.
    """
    body = (user_script or "").strip()
    if not body:
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "new_files": [],
            "message": "",
            "error": "script is empty",
        }

    ws = settings.eeg_workspace
    ws.mkdir(parents=True, exist_ok=True)
    out_dir = _output_dir()
    files_before = {f.name for f in out_dir.iterdir() if f.is_file()}
    current_script = _PREAMBLE + body
    last_stdout = ""
    last_stderr = ""
    last_exit = -1
    last_new: list[str] = []

    from hexnode.config import python_for_eeg

    python = python_for_eeg()
    timeout = max(10, settings.python_analysis_timeout)

    for attempt in range(_MAX_RETRIES + 1):
        fd, tmp = tempfile.mkstemp(suffix=".py", prefix="hex_analysis_", dir=str(ws))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(current_script)

            proc = subprocess.run(
                [python, tmp],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(ws),
                creationflags=_CREATION_FLAGS,
                env={**os.environ, "MPLBACKEND": "Agg"},
            )
            last_stdout = (proc.stdout or "").strip()
            last_stderr = (proc.stderr or "").strip()
            last_exit = proc.returncode
            last_new = _list_new_files(out_dir, files_before)
            msg = _format_run_message(last_stdout, last_stderr, last_new)

            if proc.returncode == 0:
                return {
                    "ok": True,
                    "exit_code": 0,
                    "stdout": last_stdout,
                    "stderr": last_stderr,
                    "new_files": last_new,
                    "message": msg,
                    "error": None,
                }

            if attempt < _MAX_RETRIES:
                fixed = _apply_auto_fix(current_script, last_stderr)
                if fixed and fixed != current_script:
                    current_script = fixed
                    continue

            return {
                "ok": False,
                "exit_code": last_exit,
                "stdout": last_stdout,
                "stderr": last_stderr,
                "new_files": last_new,
                "message": msg,
                "error": f"exit code {last_exit}",
            }

        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": last_stdout,
                "stderr": last_stderr,
                "new_files": last_new,
                "message": _format_run_message(last_stdout, last_stderr, last_new),
                "error": f"Script timed out after {settings.python_analysis_timeout}s",
            }
        except Exception as e:
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": last_stdout,
                "stderr": last_stderr,
                "new_files": last_new,
                "message": "",
                "error": str(e)[:800],
            }
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    return {
        "ok": False,
        "exit_code": last_exit,
        "stdout": last_stdout,
        "stderr": last_stderr,
        "new_files": last_new,
        "message": _format_run_message(last_stdout, last_stderr, last_new),
        "error": "Unexpected retry failure",
    }


class RunPythonAnalysisTool(Tool):
    name = "run_python_analysis"
    required_feature = "python_analysis"
    required_all_features = ("eeg",)
    description = (
        "Execute a Python script for EEG / scientific analysis (MNE, NumPy, SciPy, matplotlib). "
        "Params: script (str, required) — full Python source code. "
        "Working dir is data/eeg_workspace/; save plots to output/ subdir. "
        "Auto-retries up to 2 times on failure with simple error-based fixes. "
        "The desktop **Script** tab shows your last run script and links from the reply when applicable."
    )

    async def run(self, ctx: ToolContext, script: str = "", **_: Any) -> ToolResult:
        d = execute_python_analysis_script(script)
        if d["ok"]:
            return ToolResult(ok=True, data=d["message"], error=None)
        return ToolResult(ok=False, data=d.get("message") or None, error=d.get("error"))
