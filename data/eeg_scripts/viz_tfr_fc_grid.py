"""Tier: advanced — Morlet TFR for Fz, Cz, Pz (when present) in one figure; visualization-focused companion to advanced_time_frequency_morlet.py.
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
from mne.time_frequency import tfr_morlet
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
FREQS = np.linspace(4.0, 40.0, 19)
N_CYCLES = FREQS / 2.0
TARGETS = ["Fz", "Cz", "Pz"]
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
raw.filter(1.0, 45.0, fir_design="firwin", verbose=False)

events = mne.make_fixed_length_events(raw, id=1, duration=EPOCH_LEN_S, overlap=0.0)
tmax = EPOCH_LEN_S - 1.0 / raw.info["sfreq"]
epochs = mne.Epochs(
    raw, events, 1, tmin=0.0, tmax=tmax, baseline=None, preload=True, verbose=False
)

power = tfr_morlet(
    epochs,
    freqs=FREQS,
    n_cycles=N_CYCLES,
    average=True,
    return_itc=False,
    verbose=False,
)

present = [c for c in TARGETS if c in power.ch_names]
if not present:
    present = [power.ch_names[len(power.ch_names) // 2]]

stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
n = len(present)
fig, axes = plt.subplots(1, n, figsize=(4 * n, 4))
if n == 1:
    axes = [axes]

for ax, ch in zip(axes, present):
    idx = power.ch_names.index(ch)
    d = power.data[idx, :, :]
    im = ax.imshow(
        10 * np.log10(d + 1e-20),
        aspect="auto",
        origin="lower",
        extent=[epochs.times[0], epochs.times[-1], FREQS[0], FREQS[-1]],
        cmap="viridis",
    )
    ax.set_title(ch)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Hz")
    fig.colorbar(im, ax=ax, fraction=0.046, label="dB")
fig.suptitle("Morlet TFR — Fz/Cz/Pz (or fallback)")
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, f"{stem}_tfr_fc_grid.png")
fig.savefig(out, dpi=150)
plt.close(fig)
print(f"Saved {out}")

try:
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    ncols = len(present)
    pfig = make_subplots(rows=1, cols=ncols, subplot_titles=present, horizontal_spacing=0.06)
    for col, ch in enumerate(present, start=1):
        idx = power.ch_names.index(ch)
        z = 10 * np.log10(power.data[idx, :, :] + 1e-20)
        pfig.add_trace(
            go.Heatmap(
                x=epochs.times,
                y=FREQS,
                z=z,
                colorscale="Viridis",
                showscale=(col == ncols),
                colorbar=dict(title="dB", len=0.55, y=0.5) if col == ncols else None,
            ),
            row=1,
            col=col,
        )
        pfig.update_xaxes(title_text="Time (s)", row=1, col=col)
        pfig.update_yaxes(title_text="Hz", row=1, col=col)
    pfig.update_layout(
        title_text="Morlet TFR — Fz/Cz/Pz (or fallback)",
        template="plotly_dark",
        height=420,
        width=min(400 * ncols, 1400),
    )
    html_out = os.path.join(OUTPUT_DIR, f"{stem}_tfr_fc_grid.html")
    pfig.write_html(html_out, include_plotlyjs=True, full_html=True)
    print(f"Saved {html_out} (interactive Plotly)")
except ImportError:
    print("Plotly not installed — skipped HTML export (pip install plotly)")
