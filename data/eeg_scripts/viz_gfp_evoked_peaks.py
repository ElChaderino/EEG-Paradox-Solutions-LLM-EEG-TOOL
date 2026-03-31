"""Tier: expert — Global Field Power (GFP) time course from averaged fixed-length epochs + topomaps at GFP peaks.
Classic ERP-style viz without external triggers. Adapt N_PEAKS.
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
EPOCH_LEN_S = 2.0
N_PEAKS = 5
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

gfp = evoked.data.std(axis=0)
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

fig1, ax1 = plt.subplots(figsize=(9, 3))
ax1.plot(evoked.times, gfp, "k", lw=1)
ax1.set_xlabel("Time (s)")
ax1.set_ylabel("GFP")
ax1.set_title("Global Field Power (averaged epochs)")
ax1.grid(True, alpha=0.3)
fig1.savefig(os.path.join(OUTPUT_DIR, f"{stem}_gfp_curve.png"), dpi=150, bbox_inches="tight")
plt.close(fig1)

peak_idx = np.argsort(gfp)[::-1][:N_PEAKS]
peak_times = np.sort(np.unique(evoked.times[peak_idx]))
fig2 = evoked.plot_topomap(times=list(peak_times), colorbar=True, show=False)
fig2.savefig(os.path.join(OUTPUT_DIR, f"{stem}_gfp_peak_topos.png"), dpi=150, bbox_inches="tight")
plt.close(fig2)
print(f"Saved GFP curve and {len(peak_times)}-time topomap figure under {OUTPUT_DIR}/")
