"""Tier: advanced — Split recording at midpoint; mean PSD per half overlaid (drift / state change check).
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
FMAX = 45.0
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

mid = raw.times[len(raw.times) // 2]
a = raw.copy().crop(tmax=mid, verbose=False)
b = raw.copy().crop(tmin=mid, verbose=False)

def mean_psd(r):
    s = r.compute_psd(fmax=FMAX, verbose=False)
    p, f = s.get_data(return_freqs=True)
    return 10 * np.log10(np.mean(p, axis=0) + 1e-20), f

m0, f0 = mean_psd(a)
m1, f1 = mean_psd(b)
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

fig, ax = plt.subplots(figsize=(9, 4))
ax.plot(f0, m0, label=f"First half (0–{mid:.0f}s)")
ax.plot(f1, m1, label=f"Second half ({mid:.0f}s–end)")
ax.set_xlabel("Hz")
ax.set_ylabel("Mean log10 PSD (dB)")
ax.legend()
ax.grid(True, alpha=0.3)
ax.set_title("Global mean PSD — first vs second half")
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, f"{stem}_psd_two_halves.png")
fig.savefig(out, dpi=150)
plt.close(fig)
print(f"Saved {out}")
