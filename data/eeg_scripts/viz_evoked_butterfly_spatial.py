"""Tier: intermediate — Averaged evoked butterfly with spatial color coding (`evoked.plot` MNE style).
Adapt EPOCH_LEN_S; uses fixed-length epochs.
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
EPOCH_LEN_S = 2.0
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
try:
    raw.set_montage("standard_1020", match_case=False, on_missing="ignore")
except Exception:
    pass
raw.filter(1.0, 40.0, fir_design="firwin", verbose=False)

events = mne.make_fixed_length_events(raw, id=1, duration=EPOCH_LEN_S, overlap=0.0)
tmax = EPOCH_LEN_S - 1.0 / raw.info["sfreq"]
epochs = mne.Epochs(
    raw, events, 1, tmin=0.0, tmax=tmax, baseline=None, preload=True, verbose=False
)
evoked = epochs.average()

stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
fig = evoked.plot(spatial_colors=True, show=False)
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_evoked_butterfly_spatial.png"), dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"Saved {OUTPUT_DIR}/{stem}_evoked_butterfly_spatial.png")
