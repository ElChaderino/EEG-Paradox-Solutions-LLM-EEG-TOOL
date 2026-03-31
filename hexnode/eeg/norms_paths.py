"""Resolve optional EEG normative (Cuban) DLC install location.

Search order:
1. EEG_NORMS_DLC_ROOT environment variable
2. %ProgramData%\\ParadoxSolutions\\EEGNorms (typical Windows add-on install)
3. Repo: addons/eeg-norms-dlc/payload (developer / bundled tree)
4. Repo: data/cuban_databases at project root (legacy dev layout)
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
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MANIFEST = "manifest.json"


def _project_root() -> Path:
    # hexnode/eeg/norms_paths.py -> parents[2] = repo root (Super Bot)
    return Path(__file__).resolve().parents[2]


def get_eeg_norms_dlc_root() -> Optional[Path]:
    """Return the root directory of the norms add-on (contains manifest.json and/or data/)."""
    env = (os.environ.get("EEG_NORMS_DLC_ROOT") or "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p.resolve()
        logger.warning("EEG_NORMS_DLC_ROOT is set but not a directory: %s", env)

    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    pd_root = Path(program_data) / "ParadoxSolutions" / "EEGNorms"
    if pd_root.is_dir():
        if (pd_root / _MANIFEST).is_file() or (pd_root / "data" / "cuban_databases").is_dir():
            return pd_root.resolve()

    addon = _project_root() / "addons" / "eeg-norms-dlc" / "payload"
    if addon.is_dir():
        if (addon / _MANIFEST).is_file() or (addon / "data" / "cuban_databases").is_dir():
            return addon.resolve()

    legacy = _project_root() / "data" / "cuban_databases"
    if legacy.is_dir():
        return _project_root().resolve()

    return None


def get_cuban_databases_dir() -> Optional[Path]:
    """Directory containing cuban_database/ and cuban_2nd_wave_database/ trees."""
    root = get_eeg_norms_dlc_root()
    if not root:
        return None
    d1 = root / "data" / "cuban_databases"
    if d1.is_dir():
        return d1.resolve()
    d2 = root / "cuban_databases"
    if d2.is_dir():
        return d2.resolve()
    # Legacy: root is project root with data/cuban_databases
    if root.name != "cuban_databases" and (root / "cuban_databases").is_dir():
        return (root / "cuban_databases").resolve()
    if root.name == "cuban_databases" or (root / "cuban_2nd_wave_database").is_dir():
        return root.resolve()
    return None


def read_eeg_norms_manifest() -> Optional[dict[str, Any]]:
    root = get_eeg_norms_dlc_root()
    if not root:
        return None
    mf = root / _MANIFEST
    if not mf.is_file():
        return None
    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("Could not read norms manifest: %s", e)
        return None


def norms_addon_status() -> dict[str, Any]:
    """Summary for /health and diagnostics."""
    root = get_eeg_norms_dlc_root()
    cuban = get_cuban_databases_dir()
    mf = read_eeg_norms_manifest()
    return {
        "installed": cuban is not None,
        "root": str(root) if root else None,
        "cuban_databases": str(cuban) if cuban else None,
        "version": (mf or {}).get("version"),
        "id": (mf or {}).get("id"),
    }
