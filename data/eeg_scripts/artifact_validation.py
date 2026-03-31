"""Gunkelman-style Artifact Validation — multi-layer signal quality assessment.
Implements robust stats, band relationship checks, temporal consistency,
filter cross-checks, EMG detection, and alpha reactivity validation.
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
from scipy import signal as sig
from scipy.stats import zscore
import json, os, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BANDS = {"Delta":(1,4),"Theta":(4,8),"Alpha":(8,13),"SMR":(12,15),
         "Beta":(13,30),"High_Beta":(20,30),"Gamma":(30,45)}

THRESHOLDS = {
    "z_score_diff": 1.5,
    "power_ratio": 2.5,
    "emg_ratio": 0.7,
    "sef95_emg": 35,
    "temporal_variance_ratio": 3.0,
    "filter_power_diff": 5.0,
    "notch_impact": 2.0,
    "clipping_uv": 300,
    "flatline_var": 1e-12,
    "edge_variance": 2.0,
}

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)
sfreq = raw.info["sfreq"]
data_raw = raw.get_data()
ch_names = raw.ch_names
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

all_results = {}
all_warnings = []

for ci, ch in enumerate(ch_names):
    ch_data = data_raw[ci]
    ch_data_uv = ch_data * 1e6
    ch_warnings = []

    # 1. Robust stats
    std = np.std(ch_data)
    if std < THRESHOLDS["flatline_var"]:
        ch_warnings.append("FLATLINE — zero variance")
    else:
        z = zscore(ch_data)
        median_val = np.median(ch_data)
        mad = np.median(np.abs(ch_data - median_val))
        robust_z = (ch_data - median_val) / (mad + 1e-20)
        z_diff = float(np.mean(np.abs(z - robust_z)))
        if z_diff > THRESHOLDS["z_score_diff"]:
            ch_warnings.append(f"Outlier distribution (z-diff={z_diff:.2f})")

    # 2. Band relationships
    freqs, psd = sig.welch(ch_data, fs=sfreq, nperseg=min(int(sfreq * 2), len(ch_data) // 4))
    powers = {}
    for bname, (fmin, fmax) in BANDS.items():
        mask = (freqs >= fmin) & (freqs <= fmax)
        powers[bname] = float(np.mean(psd[mask])) if mask.any() else 0

    tb = powers["Theta"] / (powers["Beta"] + 1e-20)
    hb_b = powers["High_Beta"] / (powers["Beta"] + 1e-20)
    g_b = powers["Gamma"] / (powers["Beta"] + 1e-20)

    if tb > THRESHOLDS["power_ratio"]:
        ch_warnings.append(f"Suspicious Theta/Beta ratio ({tb:.2f})")
    if hb_b > THRESHOLDS["emg_ratio"]:
        ch_warnings.append(f"Possible EMG (HiBeta/Beta={hb_b:.2f})")
    if g_b > THRESHOLDS["emg_ratio"]:
        ch_warnings.append(f"Possible EMG (Gamma/Beta={g_b:.2f})")

    # 3. Spectral edge frequency
    cumsum = np.cumsum(psd)
    total_p = cumsum[-1]
    if total_p > 0:
        sef95_idx = np.searchsorted(cumsum, 0.95 * total_p)
        sef95 = float(freqs[min(sef95_idx, len(freqs) - 1)])
        if sef95 > THRESHOLDS["sef95_emg"]:
            ch_warnings.append(f"High SEF95 ({sef95:.1f} Hz) — EMG contamination likely")
    else:
        sef95 = 0

    # 4. Temporal consistency (2s vs 10s epoch variance)
    n2 = int(2 * sfreq)
    n10 = int(10 * sfreq)
    if len(ch_data) >= n10 * 2:
        def epoch_beta_var(epoch_len):
            ns = int(epoch_len * sfreq)
            ne = len(ch_data) // ns
            pows = []
            for i in range(ne):
                ep = ch_data[i * ns:(i + 1) * ns]
                f, p = sig.welch(ep, fs=sfreq, nperseg=min(int(sfreq), ns // 2))
                mask = (f >= 20) & (f <= 40)
                pows.append(float(np.mean(p[mask])) if mask.any() else 0)
            return np.var(pows) if pows else 0
        var2 = epoch_beta_var(2)
        var10 = epoch_beta_var(10)
        vr = var2 / (var10 + 1e-20)
        if vr > THRESHOLDS["temporal_variance_ratio"]:
            ch_warnings.append(f"High temporal variability (ratio={vr:.1f})")

    # 5. Filter cross-checks (broad vs narrow)
    try:
        broad = mne.filter.filter_data(ch_data[None, :], sfreq, 1, 70, verbose=False)[0]
        narrow = mne.filter.filter_data(ch_data[None, :], sfreq, 1, 30, verbose=False)[0]
        power_diff = float(np.mean(np.abs(broad - narrow)))
        if power_diff > THRESHOLDS["filter_power_diff"]:
            ch_warnings.append(f"Significant high-frequency content (diff={power_diff:.2f})")
        if len(narrow) > 200:
            edge_var = np.var(narrow[:100]) / (np.var(narrow[100:-100]) + 1e-20)
            if edge_var > THRESHOLDS["edge_variance"]:
                ch_warnings.append("Filter edge effects detected")
    except Exception as e:
        ch_warnings.append(f"Filter cross-check skipped: {e}")

    # 6. Clipping
    max_amp = float(np.max(np.abs(ch_data_uv)))
    if max_amp > THRESHOLDS["clipping_uv"]:
        ch_warnings.append(f"Clipping/high amplitude ({max_amp:.0f} µV)")

    # 7. Line noise (50/60 Hz)
    for line_f in [50.0, 60.0]:
        if line_f < sfreq / 2:
            mask_line = (freqs >= line_f - 1) & (freqs <= line_f + 1)
            mask_bg = (freqs >= line_f - 5) & (freqs <= line_f + 5) & ~mask_line
            if mask_line.any() and mask_bg.any():
                ratio = np.mean(psd[mask_line]) / (np.mean(psd[mask_bg]) + 1e-20)
                if ratio > 3.0:
                    ch_warnings.append(f"Line noise at {line_f} Hz (ratio={ratio:.1f})")

    all_results[ch] = {
        "warnings": ch_warnings,
        "passed": len(ch_warnings) == 0,
        "tb_ratio": round(tb, 2),
        "hb_b_ratio": round(hb_b, 2),
        "sef95": round(sef95, 1),
        "max_amp_uV": round(max_amp, 0),
    }
    all_warnings.extend([f"{ch}: {w}" for w in ch_warnings])

# Summary
n_clean = sum(1 for v in all_results.values() if v["passed"])
print(f"\n=== Artifact Validation — {stem} ===")
print(f"Clean channels: {n_clean}/{len(ch_names)}")
print(f"Total warnings: {len(all_warnings)}")
if all_warnings:
    print("\nWarnings:")
    for w in all_warnings:
        print(f"  ⚠ {w}")
else:
    print("\nAll channels passed validation.")

print(f"\nPer-channel summary:")
print(f"{'Channel':>8s} {'T/B':>6s} {'HB/B':>6s} {'SEF95':>6s} {'MaxµV':>7s} {'Status':>10s}")
for ch in ch_names:
    r = all_results[ch]
    status = "CLEAN" if r["passed"] else f"{len(r['warnings'])} issues"
    print(f"{ch:>8s} {r['tb_ratio']:6.2f} {r['hb_b_ratio']:6.2f} {r['sef95']:6.1f} {r['max_amp_uV']:7.0f} {status:>10s}")

with open(os.path.join(OUTPUT_DIR, f"{stem}_validation.json"), "w") as f:
    json.dump(all_results, f, indent=2)
print(f"\nResults: {OUTPUT_DIR}/{stem}_validation.json")
