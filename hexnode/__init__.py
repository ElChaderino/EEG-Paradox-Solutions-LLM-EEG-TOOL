"""Paradox Solutions LLM — local AI research assistant (memory, tools, agent loop)."""
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


from pathlib import Path as _Path

__version__ = "0.3.2"

def _read_version() -> str:
    """Return version from the root VERSION file if available, else __version__."""
    for anchor in (_Path(__file__).resolve().parent.parent, _Path.cwd()):
        vf = anchor / "VERSION"
        if vf.is_file():
            v = vf.read_text().strip()
            if v:
                return v
    return __version__

VERSION = _read_version()
