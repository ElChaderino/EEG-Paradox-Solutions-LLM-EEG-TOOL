"""Tier: intermediate — Fixed-length epochs from continuous EEG + global field power / average (mne.tools epoching tutorials).
No external triggers required. Good for resting-state blocks. Adapt INPUT_FILE, EPOCH_LEN_S, OVERLAP_S.
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
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
EPOCH_LEN_S = 2.0
OVERLAP_S = 0.0
LOW_HZ = 1.0
HIGH_HZ = 40.0

LOADERS = {
    ".edf": mne.io.read_raw_edf,
    ".bdf": mne.io.read_raw_bdf,
    ".fif": mne.io.read_raw_fif,
    ".vhdr": mne.io.read_raw_brainvision,
}

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loader = LOADERS.get(ext)
if not loader:
    raise ValueError(f"Unsupported format: {ext}")

raw = loader(INPUT_FILE, preload=True, verbose=False)
raw.pick(picks="eeg", exclude="bads")
try:
    raw.set_montage("standard_1020", match_case=False, on_missing="ignore")
except Exception:
    pass
raw.filter(LOW_HZ, HIGH_HZ, fir_design="firwin", verbose=False)

events = mne.make_fixed_length_events(raw, id=1, duration=EPOCH_LEN_S, overlap=OVERLAP_S)
epochs = mne.Epochs(
    raw,
    events,
    event_id=1,
    tmin=0.0,
    tmax=EPOCH_LEN_S - 1.0 / raw.info["sfreq"],
    baseline=None,
    preload=True,
    verbose=False,
)
evoked = epochs.average()
fig = evoked.plot_joint(times="peaks", show=False)
out = INPUT_FILE.rsplit(".", 1)[0] + "_evoked_joint.png"
fig.savefig(out, dpi=150)
print(f"Epochs: {len(epochs)}, saved {out}")
gfp = evoked.data.std(axis=0).mean()
print(f"Mean global field power (approx): {gfp:.2e}")
