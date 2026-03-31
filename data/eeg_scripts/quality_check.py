"""Data Quality Check — comprehensive EEG recording quality assessment.
Detects artifacts, bad channels, line noise, flatlines, and data integrity issues.
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
from scipy import signal
import json, os, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)
sfreq = raw.info["sfreq"]
data = raw.get_data()
n_ch, n_samp = data.shape
ch_names = raw.ch_names
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
duration = n_samp / sfreq

print(f"File: {INPUT_FILE}")
print(f"Channels: {n_ch}, Duration: {duration:.1f}s ({duration/60:.1f} min), Fs: {sfreq} Hz")

issues = []
quality = {"channels": {}, "global": {}}

for i, ch in enumerate(ch_names):
    sig = data[i]
    ch_info = {}

    # Flatline
    std = float(np.std(sig))
    ch_info["std_uV"] = std * 1e6
    if std < 1e-10:
        ch_info["flatline"] = True
        issues.append(f"{ch}: FLATLINE (zero variance)")
    else:
        ch_info["flatline"] = False

    # Amplitude
    amp_uv = float(np.max(np.abs(sig))) * 1e6
    ch_info["max_amp_uV"] = amp_uv
    if amp_uv > 500:
        issues.append(f"{ch}: HIGH AMPLITUDE ({amp_uv:.0f} µV)")
    if amp_uv > 1000:
        ch_info["clipping_suspected"] = True

    # DC offset
    dc = float(np.mean(sig)) * 1e6
    ch_info["dc_offset_uV"] = dc
    if abs(dc) > 100:
        issues.append(f"{ch}: DC OFFSET ({dc:.1f} µV)")

    # Electrode pops (large sample-to-sample jumps)
    diff = np.diff(sig) * 1e6
    max_diff = float(np.max(np.abs(diff)))
    ch_info["max_diff_uV"] = max_diff
    if max_diff > 200:
        n_pops = int(np.sum(np.abs(diff) > 200e-6))
        ch_info["electrode_pops"] = n_pops
        issues.append(f"{ch}: ELECTRODE POPS ({n_pops} events, max {max_diff:.0f} µV)")

    # Kurtosis (>5 suggests non-gaussian artifacts)
    if std > 1e-10:
        kurt = float(np.mean((sig - sig.mean())**4) / (std**4) - 3)
        ch_info["kurtosis"] = kurt
        if kurt > 5:
            issues.append(f"{ch}: HIGH KURTOSIS ({kurt:.1f}) — artifacts likely")

    # Line noise (50/60 Hz)
    if std > 1e-10:
        freqs, psd = signal.welch(sig, fs=sfreq, nperseg=min(int(sfreq * 2), n_samp // 4))
        total_power = _trapz(psd, freqs)
        for line_freq in [50.0, 60.0]:
            if line_freq < sfreq / 2:
                mask = (freqs >= line_freq - 2) & (freqs <= line_freq + 2)
                if mask.any():
                    line_power = _trapz(psd[mask], freqs[mask])
                    ratio = line_power / total_power if total_power > 0 else 0
                    ch_info[f"line_noise_{int(line_freq)}Hz_ratio"] = float(ratio)
                    if ratio > 0.15:
                        issues.append(f"{ch}: LINE NOISE at {line_freq} Hz ({ratio:.1%} of power)")

        # EMG contamination (30-70 Hz)
        emg_mask = (freqs >= 30) & (freqs <= 70)
        low_mask = (freqs >= 1) & (freqs <= 30)
        if emg_mask.any() and low_mask.any():
            emg_power = _trapz(psd[emg_mask], freqs[emg_mask])
            low_power = _trapz(psd[low_mask], freqs[low_mask])
            emg_ratio = emg_power / low_power if low_power > 0 else 0
            ch_info["emg_ratio"] = float(emg_ratio)
            if emg_ratio > 0.5:
                issues.append(f"{ch}: EMG CONTAMINATION (30-70Hz ratio={emg_ratio:.2f})")

    quality["channels"][ch] = ch_info

# Global metrics
rms_all = float(np.sqrt(np.mean(data ** 2))) * 1e6
quality["global"]["rms_uV"] = rms_all
quality["global"]["duration_s"] = duration
quality["global"]["sfreq"] = sfreq
quality["global"]["n_channels"] = n_ch

# Channel correlation (detect bridged electrodes)
if n_ch > 1:
    corr = np.corrcoef(data)
    bridged = []
    for i in range(n_ch):
        for j in range(i + 1, n_ch):
            if abs(corr[i, j]) > 0.99:
                bridged.append((ch_names[i], ch_names[j], float(corr[i, j])))
    if bridged:
        for a, b, c in bridged:
            issues.append(f"{a}-{b}: BRIDGED (corr={c:.4f})")
    quality["global"]["bridged_pairs"] = bridged

# Inter-channel variance spread
stds = np.array([np.std(data[i]) for i in range(n_ch)])
if stds.max() > 0:
    spread = stds.max() / (np.median(stds) + 1e-20)
    quality["global"]["variance_spread"] = float(spread)
    if spread > 10:
        issues.append(f"VARIANCE SPREAD: max/median = {spread:.1f}x — suspect bad channel(s)")

# Summary
n_bad = sum(1 for ch_info in quality["channels"].values()
            if ch_info.get("flatline") or ch_info.get("max_amp_uV", 0) > 500)
quality["global"]["n_bad_channels"] = n_bad
quality["global"]["n_issues"] = len(issues)
quality["global"]["usable"] = n_bad < n_ch * 0.3 and duration > 30

print(f"\n=== Quality Summary ===")
print(f"Issues found: {len(issues)}")
print(f"Bad channels: {n_bad} / {n_ch}")
print(f"Data usable: {'YES' if quality['global']['usable'] else 'NO — too many issues'}")
if issues:
    print(f"\nIssue details:")
    for issue in issues:
        print(f"  ⚠ {issue}")
else:
    print("\nNo issues detected — recording looks clean.")

with open(os.path.join(OUTPUT_DIR, f"{stem}_quality.json"), "w") as f:
    json.dump(quality, f, indent=2)
print(f"\nFull report: {OUTPUT_DIR}/{stem}_quality.json")
