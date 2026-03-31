"""Tier: expert — debiased wPLI + circular graph (mne_connectivity.viz.plot_connectivity_circle). Strong visual summary of strongest links.
Requires mne-connectivity. Adapt FMIN, FMAX, N_LINES.
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
FMIN, FMAX = 8.0, 13.0
N_LINES = 40
os.makedirs(OUTPUT_DIR, exist_ok=True)

try:
    from mne_connectivity import spectral_connectivity_epochs
    from mne_connectivity.viz import plot_connectivity_circle
    from mne.viz import circular_layout
except ImportError as e:
    raise ImportError("pip install mne-connectivity") from e

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
if raw.info["nchan"] < 4:
    raise RuntimeError("Need ≥4 channels for readable circle plot")

events = mne.make_fixed_length_events(raw, id=1, duration=EPOCH_LEN_S, overlap=0.0)
tmax = EPOCH_LEN_S - 1.0 / raw.info["sfreq"]
epochs = mne.Epochs(
    raw, events, 1, tmin=0.0, tmax=tmax, baseline=None, preload=True, verbose=False
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
    mat = np.mean(arr, axis=-1).astype(float)
else:
    mat = np.asarray(arr, dtype=float)

labels = list(epochs.ch_names)
node_order = list(range(len(labels)))
node_angles = circular_layout(labels, node_order=node_order, start_pos=90)

stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
fig, _ = plot_connectivity_circle(
    mat,
    labels,
    n_lines=N_LINES,
    node_order=node_order,
    node_angles=node_angles,
    title=f"wPLI {FMIN}-{FMAX} Hz",
    facecolor="white",
    textcolor="black",
    node_edgecolor="black",
    linewidth=1.2,
    colormap="hot",
    ax=None,
    show=False,
    interactive=False,
)
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_connectivity_circle.png"), dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Saved {OUTPUT_DIR}/{stem}_connectivity_circle.png")
