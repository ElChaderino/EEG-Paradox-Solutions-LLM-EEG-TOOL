"""Tier: advanced — Sliding-window RMS per channel → heatmap (time × channel). Quick artifact / drift overview.
Adapt WIN_S, HOP_S. Uses raw data (wideband after light high-pass).
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
WIN_S = 2.0
HOP_S = 1.0
HP_HZ = 0.5
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
raw.filter(HP_HZ, None, fir_design="firwin", verbose=False)

sfreq = raw.info["sfreq"]
data = raw.get_data()
win = int(WIN_S * sfreq)
hop = int(HOP_S * sfreq)
n_ch = data.shape[0]
rms_mat = []
t_centers = []
for start in range(0, data.shape[1] - win, hop):
    seg = data[:, start : start + win]
    rms_mat.append(np.sqrt(np.mean(seg**2, axis=1)))
    t_centers.append((start + win / 2) / sfreq)
if not rms_mat:
    raise RuntimeError("Recording too short for WIN_S or increase file length")
rms_mat = np.array(rms_mat).T
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

fig, ax = plt.subplots(figsize=(12, max(4, n_ch * 0.15)))
im = ax.imshow(
    rms_mat,
    aspect="auto",
    cmap="magma",
    extent=[t_centers[0], t_centers[-1], n_ch - 0.5, -0.5],
)
ax.set_yticks(range(n_ch))
ax.set_yticklabels(raw.ch_names, fontsize=6)
ax.set_xlabel("Time (s)")
ax.set_title(f"Windowed RMS ({WIN_S}s win, {HOP_S}s hop)")
plt.colorbar(im, ax=ax, label="RMS (V)")
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, f"{stem}_rms_heatmap.png")
fig.savefig(out, dpi=150)
plt.close(fig)
print(f"Saved {out}")

try:
    import plotly.graph_objects as go
    pfig = go.Figure(
        data=go.Heatmap(
            z=rms_mat,
            x=t_centers,
            y=raw.ch_names,
            colorscale="Magma",
            colorbar=dict(title="RMS (V)"),
        )
    )
    pfig.update_layout(
        title=f"Windowed RMS ({WIN_S}s win, {HOP_S}s hop)",
        xaxis_title="Time (s)",
        template="plotly_dark",
        height=max(360, min(900, 40 * n_ch)),
        yaxis=dict(autorange="reversed"),
    )
    html_out = os.path.join(OUTPUT_DIR, f"{stem}_rms_heatmap.html")
    pfig.write_html(html_out, include_plotlyjs=True, full_html=True)
    print(f"Saved {html_out} (interactive Plotly)")
except ImportError:
    print("Plotly not installed — skipped HTML export (pip install plotly)")
