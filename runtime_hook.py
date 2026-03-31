"""PyInstaller runtime hook — runs before the main entry point.

Creates the appdata directory structure and copies bundled reference data
on first run so user data persists across updates.
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


import os
import shutil
import sys
from pathlib import Path


def _bootstrap():
    if not getattr(sys, "frozen", False):
        return

    appdata = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ParadoxSolutionsLLM"
    data_dir = appdata / "data"
    bundle_dir = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()

    for sub in ["chroma", "vault", "reflections", "ingest_queue", "eeg_workspace"]:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)

    env_file = appdata / ".env"
    if not env_file.exists():
        bundled_env = bundle_dir / ".env.example"
        if bundled_env.exists():
            shutil.copy2(bundled_env, env_file)
        else:
            env_file.write_text("# Paradox Solutions LLM config — edit as needed\n", encoding="utf-8")

    bundled_eeg_ref = bundle_dir / "data" / "eeg_reference"
    target_eeg_ref = data_dir / "eeg_reference"
    if bundled_eeg_ref.is_dir() and not target_eeg_ref.is_dir():
        shutil.copytree(bundled_eeg_ref, target_eeg_ref)

    bundled_eeg_scripts = bundle_dir / "data" / "eeg_scripts"
    target_eeg_scripts = data_dir / "eeg_scripts"
    if bundled_eeg_scripts.is_dir():
        if target_eeg_scripts.is_dir():
            shutil.rmtree(target_eeg_scripts)
        shutil.copytree(bundled_eeg_scripts, target_eeg_scripts)

    bundled_rules = bundle_dir / "rules.example.yaml"
    target_rules = data_dir / "rules.yaml"
    if bundled_rules.exists() and not target_rules.exists():
        shutil.copy2(bundled_rules, target_rules)

    _validate_bundle(bundle_dir)


def _validate_bundle(bundle_dir: Path):
    """Warn loudly at startup if critical files are missing from the PyInstaller bundle."""
    critical = {
        "EEG viz orchestrator": bundle_dir / "hexnode" / "eeg" / "viz" / "run_visualizations.py",
        "EEG viz package init": bundle_dir / "hexnode" / "eeg" / "viz" / "__init__.py",
        "hexnode package init": bundle_dir / "hexnode" / "__init__.py",
        "EEG norms enrichment": bundle_dir / "hexnode" / "eeg" / "norms" / "enrichment.py",
        "Clinical Q script":    bundle_dir / "data" / "eeg_scripts" / "clinical_q_assessment.py",
        "Band power script":    bundle_dir / "data" / "eeg_scripts" / "band_power_analysis.py",
    }

    missing = [label for label, path in critical.items() if not path.is_file()]
    if not missing:
        return

    banner = (
        "\n"
        "╔══════════════════════════════════════════════════════════════════╗\n"
        "║  BUNDLE INTEGRITY WARNING                                      ║\n"
        "║  The following files are missing from the packaged build.      ║\n"
        "║  EEG processing will produce incomplete results.               ║\n"
        "╠══════════════════════════════════════════════════════════════════╣\n"
    )
    for label in missing:
        banner += f"║  MISSING: {label:<53}║\n"
    banner += (
        "╠══════════════════════════════════════════════════════════════════╣\n"
        "║  FIX: Rebuild with updated paradox-api.spec that includes:     ║\n"
        '║    ("hexnode/__init__.py", "hexnode")                           ║\n'
        '║    ("hexnode/eeg", "hexnode/eeg")                               ║\n'
        "║  in the added_datas list.                                       ║\n"
        "╚══════════════════════════════════════════════════════════════════╝\n"
    )
    print(banner, file=sys.stderr, flush=True)


_bootstrap()
