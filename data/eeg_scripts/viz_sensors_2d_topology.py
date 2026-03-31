"""Tier: basic — 2D sensor layout (top-down) to verify montage and channel positions before topomaps.
Saves PNG; uses mne.viz.plot_plot_sensors. Adapt INPUT_FILE.
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
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
import warnings

warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

LOADERS = {
    ".edf": mne.io.read_raw_edf,
    ".bdf": mne.io.read_raw_bdf,
    ".fif": mne.io.read_raw_fif,
    ".vhdr": mne.io.read_raw_brainvision,
    ".set": mne.io.read_raw_eeglab,
}

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loader = LOADERS.get(ext, mne.io.read_raw_edf)
raw = loader(INPUT_FILE, preload=False, verbose=False)
raw.pick(picks="eeg", exclude="bads")
try:
    raw.set_montage("standard_1020", match_case=False, on_missing="warn")
except Exception as e:
    print(f"Montage warning: {e}")

stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
fig, ax = plt.subplots(figsize=(5, 5))
raw.plot_sensors(axes=ax, show_names=True, show=False)
ax.set_title("EEG sensor layout")
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_sensors_2d.png"), dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"Saved {OUTPUT_DIR}/{stem}_sensors_2d.png")
