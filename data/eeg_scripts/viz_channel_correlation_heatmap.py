"""Tier: intermediate — Pearson correlation matrix between EEG channels (downsampled continuous data) heatmap.
Captures gross symmetry / coupling; not directional connectivity. Adapt DOWNSAMPLE_HZ.
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
DOWNSAMPLE_HZ = 128.0
MAX_SECONDS = 120.0
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
raw.filter(1.0, 40.0, fir_design="firwin", verbose=False)
if raw.times[-1] > MAX_SECONDS:
    raw.crop(tmax=MAX_SECONDS, verbose=False)
raw.resample(sfreq=DOWNSAMPLE_HZ, verbose=False)

data = raw.get_data()
c = np.corrcoef(data)
ch = raw.ch_names
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

fig, ax = plt.subplots(figsize=(9, 8))
im = ax.imshow(c, cmap="RdBu_r", vmin=-1, vmax=1, aspect="equal")
ax.set_xticks(range(len(ch)))
ax.set_yticks(range(len(ch)))
ax.set_xticklabels(ch, rotation=90, fontsize=6)
ax.set_yticklabels(ch, fontsize=6)
ax.set_title("Channel Pearson correlation (1–40 Hz, downsampled)")
plt.colorbar(im, ax=ax, shrink=0.8)
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, f"{stem}_channel_corr.png")
fig.savefig(out, dpi=150)
plt.close(fig)
print(f"Saved {out}")

try:
    import plotly.graph_objects as go
    pfig = go.Figure(
        data=go.Heatmap(
            z=c,
            x=ch,
            y=ch,
            zmin=-1,
            zmax=1,
            colorscale="RdBu",
            colorbar=dict(title="r"),
        )
    )
    pfig.update_layout(
        title="Channel Pearson correlation (1–40 Hz, downsampled)",
        template="plotly_dark",
        width=720,
        height=680,
        xaxis=dict(side="bottom"),
        yaxis=dict(autorange="reversed"),
    )
    html_out = os.path.join(OUTPUT_DIR, f"{stem}_channel_corr.html")
    pfig.write_html(html_out, include_plotlyjs=True, full_html=True)
    print(f"Saved {html_out} (interactive Plotly)")
except ImportError:
    print("Plotly not installed — skipped HTML export (pip install plotly)")
