"""Tier: basic — Topomaps of log-PSD at several target frequencies (MNE-native spectrum → topomap).
Adapt INPUT_FILE, FREQS_TO_PLOT. Requires sensible montage for EEG locations.
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
FREQS_TO_PLOT = [6.0, 10.0, 18.0, 24.0]  # Hz — spectral “snapshots”
FMIN, FMAX = 1.0, 45.0
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
raw.filter(FMIN, FMAX, fir_design="firwin", verbose=False)

spectrum = raw.compute_psd(fmin=FMIN, fmax=FMAX, verbose=False)
psd, freqs = spectrum.get_data(return_freqs=True)
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

n = len(FREQS_TO_PLOT)
fig, axes = plt.subplots(1, n, figsize=(3.2 * n, 4))
if n == 1:
    axes = [axes]
for ax, f0 in zip(axes, FREQS_TO_PLOT):
    idx = int(np.argmin(np.abs(freqs - f0)))
    band = (freqs >= f0 - 1.0) & (freqs <= f0 + 1.0)
    if np.any(band):
        vec = np.mean(psd[:, band], axis=1)
    else:
        vec = psd[:, idx]
    vec_db = 10 * np.log10(vec + 1e-20)
    im, _ = mne.viz.plot_topomap(vec_db, raw.info, axes=ax, show=False, vlim=(None, None))
    ax.set_title(f"~{freqs[idx]:.1f} Hz (dB)")
plt.suptitle(f"log PSD topomaps — {stem}")
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, f"{stem}_psd_topo_grid.png")
fig.savefig(out, dpi=150)
plt.close(fig)
print(f"Saved {out}")
