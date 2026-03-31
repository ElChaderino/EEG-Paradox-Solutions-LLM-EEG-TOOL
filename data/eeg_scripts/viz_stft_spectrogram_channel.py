"""Tier: advanced — SciPy STFT spectrogram (dB) for one EEG channel — high-res time–freq without Morlet bank.
Adapt CHANNEL (name or index 0-based).
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
from scipy.signal import stft
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
import warnings

warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
CHANNEL = "Cz"  # or integer index
NPERSEG = 1024
NOVERLAP = 768
FMAX_PLOT = 45.0
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
raw.filter(0.5, FMAX_PLOT, fir_design="firwin", verbose=False)

if isinstance(CHANNEL, str):
    if CHANNEL not in raw.ch_names:
        CHANNEL = raw.ch_names[0]
    idx = raw.ch_names.index(CHANNEL)
else:
    idx = int(CHANNEL) % len(raw.ch_names)
    CHANNEL = raw.ch_names[idx]

sfreq = raw.info["sfreq"]
x = raw.get_data(picks=[idx])[0]
nperseg = min(NPERSEG, max(64, len(x) // 8))
noverlap = min(NOVERLAP, nperseg - 1)
f, t, Z = stft(x, fs=sfreq, nperseg=nperseg, noverlap=noverlap)
mag = np.abs(Z)
db = 20 * np.log10(mag + 1e-12)
mask = f <= FMAX_PLOT

stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
fig, ax = plt.subplots(figsize=(11, 4))
im = ax.pcolormesh(t, f[mask], db[mask], shading="gouraud", cmap="magma")
ax.set_ylabel("Hz")
ax.set_xlabel("Time (s)")
ax.set_title(f"STFT spectrogram — {CHANNEL}")
plt.colorbar(im, ax=ax, label="dB")
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, f"{stem}_stft_{CHANNEL}.png")
fig.savefig(out, dpi=150)
plt.close(fig)
print(f"Saved {out}")
