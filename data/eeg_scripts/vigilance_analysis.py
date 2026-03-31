"""Vigilance / Arousal State Analysis — continuous state regulation scoring.
Computes vigilance index (0-100), discrete states (Alert to Deep Sleep),
engagement index, and instability metrics using sliding window analysis.
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
_trapz = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import signal as sig
import json, os, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
CONDITION = "EO"  # EO or EC (affects thresholds)
WINDOW_S = 4.0
STEP_S = 2.0
os.makedirs(OUTPUT_DIR, exist_ok=True)

REGIONS = {
    "frontal": ["Fp1", "Fp2", "F3", "F4", "F7", "F8", "Fz"],
    "central": ["C3", "C4", "Cz"],
    "temporal": ["T7", "T8", "P7", "P8"],
    "parietal": ["P3", "P4", "Pz"],
    "occipital": ["O1", "O2", "Oz"],
}
REGION_WEIGHTS = {"occipital": 0.30, "parietal": 0.25, "central": 0.20, "frontal": 0.20, "temporal": 0.05}

if CONDITION == "EO":
    SFI_MID, PAI_MID, HFTI_MID = 1.15, 0.90, 0.85
else:
    SFI_MID, PAI_MID, HFTI_MID = 1.30, 1.10, 0.85

def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))

def band_power(data, sfreq, fmin, fmax):
    freqs, psd = sig.welch(data, fs=sfreq, nperseg=min(int(sfreq * 2), len(data) // 2))
    mask = (freqs >= fmin) & (freqs <= fmax)
    return float(_trapz(psd[mask], freqs[mask])) if mask.any() else 0.0

def emg_proxy(data, sfreq):
    total = band_power(data, sfreq, 1, 45)
    hf = band_power(data, sfreq, 30, 45)
    return hf / total if total > 0 else 0

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)
raw.filter(0.5, 45.0, verbose=False)
raw.notch_filter([60.0], verbose=False)
sfreq = raw.info["sfreq"]
data = raw.get_data()
ch_names = raw.ch_names
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

ch_to_region = {}
for region, sites in REGIONS.items():
    for s in sites:
        for ch in ch_names:
            if ch.upper() == s.upper():
                ch_to_region[ch] = region

win_samples = int(WINDOW_S * sfreq)
step_samples = int(STEP_S * sfreq)
n_windows = max(1, (data.shape[1] - win_samples) // step_samples + 1)

window_results = []
for wi in range(n_windows):
    start = wi * step_samples
    end = start + win_samples
    if end > data.shape[1]:
        break
    t_center = (start + end) / 2 / sfreq

    region_indices = {}
    for ci, ch in enumerate(ch_names):
        r = ch_to_region.get(ch)
        if r:
            region_indices.setdefault(r, []).append(ci)

    region_vigilance = {}
    for region, ch_idxs in region_indices.items():
        sfis, pais, hftis = [], [], []
        for ci in ch_idxs:
            seg = data[ci, start:end]
            delta = band_power(seg, sfreq, 0.5, 4)
            theta = band_power(seg, sfreq, 4, 8)
            alpha = band_power(seg, sfreq, 8, 13)
            beta = band_power(seg, sfreq, 13, 30)
            hibeta = band_power(seg, sfreq, 20, 30)

            sfi = (delta + theta) / (alpha + beta + 1e-20)
            hfti = (beta + hibeta) / (alpha + theta + 1e-20)
            sfis.append(sfi)
            hftis.append(hfti)

        sfi_avg = np.mean(sfis) if sfis else SFI_MID
        hfti_avg = np.mean(hftis) if hftis else HFTI_MID

        e_drowsy = sigmoid(2.0 * (sfi_avg - SFI_MID))
        e_hyper = sigmoid(2.5 * (hfti_avg - HFTI_MID))

        emg_vals = [emg_proxy(data[ci, start:end], sfreq) for ci in ch_idxs]
        emg_avg = np.mean(emg_vals) if emg_vals else 0
        if emg_avg >= 0.30:
            e_hyper = 0
        elif emg_avg >= 0.20:
            e_hyper *= 0.5

        vi = max(0, min(100, 50 - 40 * e_drowsy + 25 * e_hyper))
        region_vigilance[region] = vi

    global_vi = sum(region_vigilance.get(r, 50) * REGION_WEIGHTS.get(r, 0) for r in REGION_WEIGHTS)
    total_w = sum(REGION_WEIGHTS.get(r, 0) for r in region_vigilance)
    if total_w > 0:
        global_vi /= total_w

    if global_vi >= 80:
        level = "V1-Alert"
    elif global_vi >= 60:
        level = "V2-Relaxed"
    elif global_vi >= 40:
        level = "V3-Drowsy"
    elif global_vi >= 20:
        level = "V4-Microsleep"
    else:
        level = "V5-Sleep"

    window_results.append({"time": t_center, "vigilance": global_vi, "level": level, "regions": region_vigilance})

# Summary
indices = [w["vigilance"] for w in window_results]
levels = [w["level"] for w in window_results]
level_counts = {}
for l in levels:
    level_counts[l] = level_counts.get(l, 0) + 1

print(f"\n=== Vigilance Analysis — {stem} ({CONDITION}) ===")
print(f"Windows: {len(window_results)} ({WINDOW_S}s window, {STEP_S}s step)")
print(f"Mean vigilance index: {np.mean(indices):.1f} / 100")
print(f"Std:  {np.std(indices):.1f}")
print(f"Min:  {np.min(indices):.1f}  Max: {np.max(indices):.1f}")
print(f"\nState distribution:")
for level, count in sorted(level_counts.items()):
    pct = count / len(levels) * 100
    print(f"  {level}: {count} ({pct:.0f}%)")

# Instability
if len(indices) > 1:
    transitions = sum(1 for i in range(1, len(levels)) if levels[i] != levels[i - 1])
    lability = float(np.mean(np.abs(np.diff(indices))))
    duration_min = len(indices) * STEP_S / 60
    trans_rate = transitions / duration_min if duration_min > 0 else 0
    print(f"\nInstability:")
    print(f"  Transitions: {transitions} ({trans_rate:.1f}/min)")
    print(f"  Lability (mean |Δindex|): {lability:.1f}")

# Plot
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
times = [w["time"] for w in window_results]
ax1.plot(times, indices, color="steelblue", linewidth=1.5)
ax1.fill_between(times, indices, alpha=0.3, color="steelblue")
ax1.axhline(80, color="green", linestyle="--", alpha=0.5, label="V1/V2 boundary")
ax1.axhline(60, color="orange", linestyle="--", alpha=0.5, label="V2/V3 boundary")
ax1.axhline(40, color="red", linestyle="--", alpha=0.5, label="V3/V4 boundary")
ax1.set_ylabel("Vigilance Index")
ax1.set_title(f"Vigilance — {stem} ({CONDITION})")
ax1.legend(fontsize=7)
ax1.set_ylim(0, 100)
ax1.grid(alpha=0.3)

for region in REGION_WEIGHTS:
    rvals = [w["regions"].get(region, 50) for w in window_results]
    ax2.plot(times, rvals, label=region, alpha=0.7)
ax2.set_xlabel("Time (s)")
ax2.set_ylabel("Regional Vigilance")
ax2.legend(fontsize=7)
ax2.set_ylim(0, 100)
ax2.grid(alpha=0.3)
plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_vigilance.png"), dpi=150)
plt.close()

with open(os.path.join(OUTPUT_DIR, f"{stem}_vigilance.json"), "w") as f:
    json.dump({"summary": {"mean": float(np.mean(indices)), "std": float(np.std(indices)),
               "level_counts": level_counts}, "windows": window_results}, f, indent=2)
print(f"\nPlot: {OUTPUT_DIR}/{stem}_vigilance.png")
print(f"Data: {OUTPUT_DIR}/{stem}_vigilance.json")
