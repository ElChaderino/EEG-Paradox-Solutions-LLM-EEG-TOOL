"""Tier: intermediate — Per-channel peak frequency in a band (e.g. alpha) from Welch PSD → topomap of peak Hz.
Useful for alpha frequency / sluggishness screening. Adapt FMIN, FMAX (search band).
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
FMIN, FMAX = 7.0, 13.0  # search band (alpha default)
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
raw.filter(0.5, 45.0, fir_design="firwin", verbose=False)

spectrum = raw.compute_psd(fmin=1.0, fmax=40.0, verbose=False)
psd, freqs = spectrum.get_data(return_freqs=True)
mask = (freqs >= FMIN) & (freqs <= FMAX)
peaks = []
for i in range(psd.shape[0]):
    sub = psd[i, mask]
    f_sub = freqs[mask]
    if sub.size == 0:
        peaks.append(np.nan)
    else:
        peaks.append(float(f_sub[np.argmax(sub)]))

stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
peaks = np.array(peaks, dtype=float)
fig, ax = plt.subplots(figsize=(5, 5))
im, _ = mne.viz.plot_topomap(
    peaks,
    raw.info,
    axes=ax,
    show=False,
    cmap="viridis",
    vlim=(np.nanmin(peaks), np.nanmax(peaks)),
)
ax.set_title(f"Peak frequency (Hz) in {FMIN}-{FMAX} Hz")
plt.colorbar(im, ax=ax, shrink=0.7, label="Hz")
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, f"{stem}_peak_freq_topomap.png")
fig.savefig(out, dpi=150)
plt.close(fig)
print(f"Saved {out}")
