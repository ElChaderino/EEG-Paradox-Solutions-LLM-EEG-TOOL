"""Tier: basic — Continuous EEG: band-pass filter, Welch PSD, band-limited RMS topomaps (mne.tools preprocessing + sensor-space patterns).
Adapt INPUT_FILE. Requires standard 10-20 channel names after optional renaming.
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
LOW_HZ = 1.0
HIGH_HZ = 40.0
BANDS = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
}

LOADERS = {
    ".edf": mne.io.read_raw_edf,
    ".bdf": mne.io.read_raw_bdf,
    ".fif": mne.io.read_raw_fif,
    ".vhdr": mne.io.read_raw_brainvision,
}

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loader = LOADERS.get(ext)
if not loader:
    raise ValueError(f"Unsupported format for this template: {ext}")

raw = loader(INPUT_FILE, preload=True, verbose=False)
raw.pick(picks="eeg", exclude="bads")
try:
    raw.set_montage("standard_1020", match_case=False, on_missing="ignore")
except Exception:
    pass

raw.filter(LOW_HZ, HIGH_HZ, fir_design="firwin", verbose=False)

spectrum = raw.compute_psd(fmin=LOW_HZ, fmax=HIGH_HZ, verbose=False)
psd, freqs = spectrum.get_data(return_freqs=True)

ch_names = raw.ch_names
band_rms = []
labels = []
for name, (lo, hi) in BANDS.items():
    idx = (freqs >= lo) & (freqs < hi)
    if not np.any(idx):
        continue
    rms = np.sqrt(np.mean(psd[:, idx], axis=1))
    band_rms.append(rms)
    labels.append(name)

band_rms = np.array(band_rms)
fig, axes = plt.subplots(1, len(labels), figsize=(4 * len(labels), 4))
if len(labels) == 1:
    axes = [axes]
for ax, label, vec in zip(axes, labels, band_rms):
    im, _ = mne.viz.plot_topomap(vec, raw.info, axes=ax, show=False)
    ax.set_title(f"{label} RMS")
plt.suptitle(f"Band power topomaps — {INPUT_FILE}")
plt.tight_layout()
out_png = INPUT_FILE.rsplit(".", 1)[0] + "_bands_topomap.png"
plt.savefig(out_png, dpi=150)
print(f"Saved {out_png}")
