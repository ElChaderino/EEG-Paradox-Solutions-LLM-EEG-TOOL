"""Tier: intermediate — Mark near-flat / high-noise channels as bad, then `raw.interpolate_bads()`.
Heuristic only — review outputs. Adapt FLAT_UV (std threshold) and MAX_BAD_FRACTION.
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

import mne
import numpy as np
import os
import warnings

warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
FLAT_UV = 0.5  # channel std below this (microvolts) → suspicious flat
MAX_BAD_FRACTION = 0.25
os.makedirs(OUTPUT_DIR, exist_ok=True)

LOADERS = {
    ".edf": mne.io.read_raw_edf,
    ".bdf": mne.io.read_raw_bdf,
    ".fif": mne.io.read_raw_fif,
    ".vhdr": mne.io.read_raw_brainvision,
}

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loader = LOADERS.get(ext, mne.io.read_raw_edf)
raw = loader(INPUT_FILE, preload=True, verbose=False)
raw.pick(picks="eeg", exclude="bads")
raw.filter(0.5, 45.0, fir_design="firwin", verbose=False)

data = raw.get_data()
# Volts → microvolts
stds = np.std(data, axis=1) * 1e6
flat = [raw.ch_names[i] for i in range(len(stds)) if stds[i] < FLAT_UV]
max_bad = max(1, int(len(raw.ch_names) * MAX_BAD_FRACTION))
if len(flat) > max_bad:
    idx = np.argsort(stds)[:max_bad]
    flat = [raw.ch_names[i] for i in idx]

raw.info["bads"] = list(dict.fromkeys(raw.info["bads"] + flat))
print(f"Marked bad: {raw.info['bads']}")

stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
if raw.info["bads"]:
    try:
        raw.interpolate_bads(reset_bads=False, verbose=False)
        out = os.path.join(OUTPUT_DIR, f"{stem}_interp_clean.fif")
        raw.save(out, overwrite=True)
        print(f"Saved {out}")
    except Exception as e:
        print(f"Interpolation failed (need enough good neighbors / montage): {e}")
else:
    print("No bad channels detected with current threshold — nothing to interpolate")
