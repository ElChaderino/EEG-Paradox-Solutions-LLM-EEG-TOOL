"""Tier: advanced — Band-pass Hilbert envelope per channel; topomap of mean envelope (oscillation “strength”).
Adapt BAND (lo, hi) Hz. Good for alpha/beta spatial distribution. mne.tools time-domain + topomap pattern.
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
from scipy.signal import hilbert, butter, filtfilt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
import warnings

warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
BAND = (8.0, 13.0)
MAX_SECONDS = 180.0
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
if raw.times[-1] > MAX_SECONDS:
    raw.crop(tmax=MAX_SECONDS, verbose=False)

sfreq = raw.info["sfreq"]
data = raw.get_data()
lo, hi = BAND
nyq = sfreq / 2
b, a = butter(4, [max(lo, 0.5) / nyq, min(hi, nyq * 0.99) / nyq], btype="band")
env_means = []
for i in range(data.shape[0]):
    f = filtfilt(b, a, data[i])
    env = np.abs(hilbert(f))
    env_means.append(float(np.mean(env)))

stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
vec = np.array(env_means)
fig, ax = plt.subplots(figsize=(5, 5))
im, _ = mne.viz.plot_topomap(vec, raw.info, axes=ax, show=False, cmap="hot")
ax.set_title(f"Mean Hilbert envelope ({lo}-{hi} Hz)")
plt.colorbar(im, ax=ax, shrink=0.7)
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, f"{stem}_envelope_topomap.png")
fig.savefig(out, dpi=150)
plt.close(fig)
print(f"Saved {out}")
