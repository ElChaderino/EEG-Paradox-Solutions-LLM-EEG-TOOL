"""Tier: advanced — Fit ICA and save `plot_properties` figures for first N components (time course, PSD, topomap).
Requires long enough recording; uses same defaults style as ica_artifact_removal.py. Adapt N_PICKS.
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
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
import warnings

warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
ICA_METHOD = "fastica"
N_PICKS = 6
MIN_DURATION_S = 60.0
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
if raw.times[-1] < MIN_DURATION_S:
    print(f"Warning: recording < {MIN_DURATION_S}s — ICA may be unstable")
raw.filter(1.0, 45.0, verbose=False)
raw.notch_filter([60.0], verbose=False)

n_comp = min(15, raw.info["nchan"] - 1, int(np.linalg.matrix_rank(raw.get_data()) - 1))
n_comp = max(5, n_comp)
ica = mne.preprocessing.ICA(n_components=n_comp, method=ICA_METHOD, random_state=42)
ica.fit(raw, verbose=False)

stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
picks = list(range(min(N_PICKS, ica.n_components_)))
try:
    figs = ica.plot_properties(raw, picks=picks, show=False)
    if not isinstance(figs, list):
        figs = [figs]
    for i, f in enumerate(figs):
        f.savefig(os.path.join(OUTPUT_DIR, f"{stem}_ica_prop_{i}.png"), dpi=120, bbox_inches="tight")
        plt.close(f)
    print(f"Saved {len(figs)} ICA property figure(s)")
except Exception as e:
    print(f"plot_properties failed: {e}")
