"""Tier: expert — debiased wPLI between all EEG pairs on fixed-length epochs (mne_connectivity; see mne.tools connectivity docs).
Requires: pip install mne-connectivity (included in project [eeg] extra). Adapt INPUT_FILE and frequency band.
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
FMIN, FMAX = 8.0, 13.0  # alpha example

try:
    from mne_connectivity import spectral_connectivity_epochs
except ImportError as e:
    raise ImportError(
        "Install mne-connectivity: pip install mne-connectivity"
    ) from e

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
if raw.info["nchan"] < 2:
    raise RuntimeError("Need at least 2 EEG channels for connectivity")

try:
    raw.set_montage("standard_1020", match_case=False, on_missing="ignore")
except Exception:
    pass
raw.filter(1.0, 45.0, fir_design="firwin", verbose=False)

events = mne.make_fixed_length_events(raw, id=1, duration=EPOCH_LEN_S, overlap=0.0)
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

con = spectral_connectivity_epochs(
    epochs,
    method="wpli2_debiased",
    mode="multitaper",
    sfreq=epochs.info["sfreq"],
    fmin=FMIN,
    fmax=FMAX,
    faverage=True,
    verbose=False,
)

arr = con.get_data(output="dense")
if arr.ndim == 3:
    mat = np.mean(arr, axis=-1)
else:
    mat = np.asarray(arr)
ch_names = epochs.ch_names

fig, ax = plt.subplots(figsize=(8, 7))
im = ax.imshow(mat, cmap="hot", vmin=0, vmax=np.percentile(mat, 99))
ax.set_xticks(range(len(ch_names)))
ax.set_yticks(range(len(ch_names)))
ax.set_xticklabels(ch_names, rotation=90, fontsize=6)
ax.set_yticklabels(ch_names, fontsize=6)
ax.set_title(f"wPLI ({FMIN}-{FMAX} Hz)")
fig.colorbar(im, ax=ax)
plt.tight_layout()
out = INPUT_FILE.rsplit(".", 1)[0] + "_wpli_matrix.png"
plt.savefig(out, dpi=150)
print(f"Saved {out}")
