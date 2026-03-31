"""Tier: basic — Welch PSD line plot (butterfly-style): one curve per EEG channel, log frequency axis.
Good for line noise and global spectral shape. Adapt INPUT_FILE, FMAX.
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
MAX_CHANNELS_PLOT = 32
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
spectrum = raw.compute_psd(fmax=FMAX, verbose=False)
psd, freqs = spectrum.get_data(return_freqs=True)
ch_names = raw.ch_names
n_plot = min(len(ch_names), MAX_CHANNELS_PLOT)
cmap = plt.cm.viridis(np.linspace(0.15, 0.95, n_plot))

fig, ax = plt.subplots(figsize=(10, 6))
for i in range(n_plot):
    ax.semilogy(freqs, psd[i], color=cmap[i], lw=0.8, alpha=0.85, label=ch_names[i])
ax.set_xlabel("Frequency (Hz)")
ax.set_ylabel("PSD (V²/Hz)")
ax.set_title(f"Per-channel PSD (first {n_plot} channels)")
ax.grid(True, alpha=0.3)
ax.legend(loc="upper right", fontsize=5, ncol=2)
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, f"{stem}_psd_butterfly.png")
fig.savefig(out, dpi=150)
plt.close(fig)
print(f"Saved {out}")

try:
    import plotly.graph_objects as go
    traces = [
        go.Scatter(x=freqs, y=psd[i], mode="lines", name=ch_names[i], line=dict(width=1))
        for i in range(n_plot)
    ]
    pfig = go.Figure(traces)
    pfig.update_layout(
        title=f"Per-channel PSD (first {n_plot} channels)",
        xaxis_title="Frequency (Hz)",
        yaxis_title="PSD (V²/Hz)",
        yaxis_type="log",
        template="plotly_dark",
        height=520,
        legend=dict(font=dict(size=8), orientation="h", yanchor="bottom", y=1.02),
    )
    html_out = os.path.join(OUTPUT_DIR, f"{stem}_psd_butterfly.html")
    pfig.write_html(html_out, include_plotlyjs=True, full_html=True)
    print(f"Saved {html_out} (interactive Plotly)")
except ImportError:
    print("Plotly not installed — skipped HTML export (pip install plotly)")
