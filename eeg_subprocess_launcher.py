"""Frozen EEG worker entry point.

PyInstaller builds this into ``paradox-eeg-worker.exe`` with MNE, SciPy, Matplotlib,
Plotly, scikit-learn, etc. The main ``paradox-api.exe`` stays lean; this executable
runs ``_pipeline.py``, ``run_visualizations.py``, and clinical scripts the same way
``python script.py`` would.
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
import runpy
import sys


def _fix_io_encoding() -> None:
    """Force UTF-8 for stdout/stderr in frozen builds.

    On Windows the console often defaults to cp1252, which chokes on
    emoji and non-Latin characters used in log/print statements from
    pipeline scripts (e.g. trace_viewer_generator).
    """
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _inject_pythonpath() -> None:
    """Ensure PYTHONPATH dirs are on sys.path.

    In a frozen PyInstaller exe, the interpreter startup does NOT process
    PYTHONPATH the way a regular ``python`` does.  The API sets PYTHONPATH
    to its ``_internal`` directory so ``import hexnode`` works; we must
    honour that here.
    """
    extra = os.environ.get("PYTHONPATH", "")
    if not extra:
        return
    for p in reversed(extra.split(os.pathsep)):
        p = p.strip()
        if p and p not in sys.path:
            sys.path.insert(0, p)


def main() -> int:
    _fix_io_encoding()
    _inject_pythonpath()

    if len(sys.argv) >= 2 and sys.argv[1] == "--eeg-probe":
        # Used by hexnode.config to verify the frozen worker (not a real Python -c).
        import mne  # noqa: F401
        import matplotlib  # noqa: F401
        import plotly.graph_objects as _go  # noqa: F401
        import scipy  # noqa: F401
        import networkx  # noqa: F401
        import sklearn  # noqa: F401
        import statsmodels  # noqa: F401

        print("ok", flush=True)
        return 0

    if len(sys.argv) < 2:
        sys.stderr.write("usage: paradox-eeg-worker SCRIPT.py [args...]\n")
        return 2
    script = sys.argv[1]
    sys.argv = sys.argv[1:]
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        try:
            return int(code)
        except (TypeError, ValueError):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
