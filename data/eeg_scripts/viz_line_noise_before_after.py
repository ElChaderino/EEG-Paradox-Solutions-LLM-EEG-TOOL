"""Tier: basic — Compare global mean PSD before vs after notch (50/60 Hz) to visualize line noise reduction.
Set LINE_FREQS to match your region (e.g. [50] EU, [60] US, or both). Adapt INPUT_FILE.
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
LINE_FREQS = [60.0, 120.0]  # add 50.0 for EU mains
FMAX = 80.0
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
raw.filter(0.5, FMAX, fir_design="firwin", verbose=False)

stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
spec0 = raw.compute_psd(fmax=FMAX, verbose=False)
psd0, freqs = spec0.get_data(return_freqs=True)
mean0 = 10 * np.log10(np.mean(psd0, axis=0) + 1e-20)

raw_notch = raw.copy()
raw_notch.notch_filter(LINE_FREQS, verbose=False)
spec1 = raw_notch.compute_psd(fmax=FMAX, verbose=False)
psd1, _ = spec1.get_data(return_freqs=True)
mean1 = 10 * np.log10(np.mean(psd1, axis=0) + 1e-20)

fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(freqs, mean0, label="Before notch", lw=1.2)
ax.plot(freqs, mean1, label=f"After notch {LINE_FREQS} Hz", lw=1.2)
ax.set_xlabel("Frequency (Hz)")
ax.set_ylabel("Mean log10 PSD (dB re V²/Hz)")
ax.set_title("Line noise — mean PSD across channels")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, f"{stem}_psd_notch_compare.png")
fig.savefig(out, dpi=150)
plt.close(fig)
print(f"Saved {out}")
