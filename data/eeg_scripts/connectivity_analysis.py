"""Connectivity Analysis — coherence, PLV, and connectivity matrices.
Computes band-wise coherence between all channel pairs, phase-locking value,
and generates connectivity heatmaps.
Adapt INPUT_FILE before running.
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
from scipy import signal
import json, os, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BANDS = {"delta": (0.5, 4), "theta": (4, 8), "alpha": (8, 13), "beta": (13, 30), "gamma": (30, 45)}

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)
raw.filter(0.5, 45.0, verbose=False)
raw.notch_filter([60.0], verbose=False)

sfreq = raw.info["sfreq"]
data = raw.get_data()
n_ch = data.shape[0]
ch_names = raw.ch_names
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

def bandpass(x, fs, fmin, fmax, order=4):
    nyq = fs / 2
    b, a = signal.butter(order, [max(fmin, 0.1) / nyq, min(fmax, nyq * 0.99) / nyq], btype="band")
    return signal.filtfilt(b, a, x)

def compute_coherence(s1, s2, fs, fmin, fmax):
    f, coh = signal.coherence(s1, s2, fs=fs, nperseg=min(256, len(s1) // 4))
    mask = (f >= fmin) & (f <= fmax)
    return float(np.mean(coh[mask])) if mask.any() else 0.0

def compute_plv(s1, s2, fs, fmin, fmax):
    f1 = bandpass(s1, fs, fmin, fmax)
    f2 = bandpass(s2, fs, fmin, fmax)
    phase1 = np.angle(signal.hilbert(f1))
    phase2 = np.angle(signal.hilbert(f2))
    return float(np.abs(np.mean(np.exp(1j * (phase1 - phase2)))))

results = {}
for bname, (fmin, fmax) in BANDS.items():
    print(f"\n--- {bname} ({fmin}-{fmax} Hz) ---")

    coh_matrix = np.zeros((n_ch, n_ch))
    plv_matrix = np.zeros((n_ch, n_ch))
    for i in range(n_ch):
        for j in range(i + 1, n_ch):
            c = compute_coherence(data[i], data[j], sfreq, fmin, fmax)
            p = compute_plv(data[i], data[j], sfreq, fmin, fmax)
            coh_matrix[i, j] = coh_matrix[j, i] = c
            plv_matrix[i, j] = plv_matrix[j, i] = p
    np.fill_diagonal(coh_matrix, 1.0)
    np.fill_diagonal(plv_matrix, 1.0)

    # Top 10 coherence pairs
    pairs = []
    for i in range(n_ch):
        for j in range(i + 1, n_ch):
            pairs.append((ch_names[i], ch_names[j], coh_matrix[i, j], plv_matrix[i, j]))
    pairs.sort(key=lambda x: x[2], reverse=True)
    print(f"  Top coherence pairs:")
    for a, b, c, p in pairs[:10]:
        print(f"    {a:>6s} ↔ {b:<6s}  coh={c:.3f}  PLV={p:.3f}")

    # Global connectivity
    mean_coh = np.mean(coh_matrix[np.triu_indices(n_ch, k=1)])
    mean_plv = np.mean(plv_matrix[np.triu_indices(n_ch, k=1)])
    print(f"  Global coherence: {mean_coh:.3f}")
    print(f"  Global PLV: {mean_plv:.3f}")

    results[bname] = {
        "global_coherence": float(mean_coh), "global_plv": float(mean_plv),
        "top_pairs": [{"ch1": a, "ch2": b, "coherence": c, "plv": p} for a, b, c, p in pairs[:10]],
    }

    # Heatmaps
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    im1 = ax1.imshow(coh_matrix, cmap="RdYlBu_r", vmin=0, vmax=1, aspect="equal")
    ax1.set_xticks(range(n_ch)); ax1.set_xticklabels(ch_names, rotation=90, fontsize=6)
    ax1.set_yticks(range(n_ch)); ax1.set_yticklabels(ch_names, fontsize=6)
    ax1.set_title(f"Coherence — {bname}")
    plt.colorbar(im1, ax=ax1, shrink=0.8)

    im2 = ax2.imshow(plv_matrix, cmap="RdYlBu_r", vmin=0, vmax=1, aspect="equal")
    ax2.set_xticks(range(n_ch)); ax2.set_xticklabels(ch_names, rotation=90, fontsize=6)
    ax2.set_yticks(range(n_ch)); ax2.set_yticklabels(ch_names, fontsize=6)
    ax2.set_title(f"PLV — {bname}")
    plt.colorbar(im2, ax=ax2, shrink=0.8)

    plt.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_connectivity_{bname}.png"), dpi=150)
    plt.close()

# Homologous pair analysis
PAIRS = [("Fp1","Fp2"),("F3","F4"),("F7","F8"),("C3","C4"),("T7","T8"),("P3","P4"),("P7","P8"),("O1","O2")]
avail_pairs = [(a, b) for a, b in PAIRS if a in ch_names and b in ch_names]
if avail_pairs:
    print(f"\n--- Homologous Pair Coherence ---")
    for a, b in avail_pairs:
        ia, ib = ch_names.index(a), ch_names.index(b)
        for bname, (fmin, fmax) in BANDS.items():
            c = compute_coherence(data[ia], data[ib], sfreq, fmin, fmax)
            print(f"  {a}-{b} {bname}: {c:.3f}")

with open(os.path.join(OUTPUT_DIR, f"{stem}_connectivity.json"), "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {OUTPUT_DIR}/{stem}_connectivity.json")
