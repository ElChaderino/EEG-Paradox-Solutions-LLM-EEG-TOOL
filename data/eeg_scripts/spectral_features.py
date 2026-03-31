"""Advanced Spectral Features — entropy, spectral edge, peak frequency, slopes.
Computes per-channel advanced spectral metrics useful for phenotyping and
clinical assessment beyond simple band power.
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
from scipy import signal as sig
import json, os, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)
raw.filter(0.5, 45.0, verbose=False)
raw.notch_filter([60.0], verbose=False)

sfreq = raw.info["sfreq"]
data = raw.get_data()
ch_names = raw.ch_names
n_ch = data.shape[0]
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

def spectral_entropy(psd):
    psd_norm = psd / (psd.sum() + 1e-20)
    psd_norm = psd_norm[psd_norm > 0]
    return float(-np.sum(psd_norm * np.log2(psd_norm)))

def spectral_edge(freqs, psd, percentile=0.95):
    cumsum = np.cumsum(psd)
    total = cumsum[-1]
    if total == 0:
        return 0.0
    idx = np.searchsorted(cumsum, total * percentile)
    return float(freqs[min(idx, len(freqs) - 1)])

def peak_frequency(freqs, psd, fmin=1.0, fmax=30.0):
    mask = (freqs >= fmin) & (freqs <= fmax)
    if not mask.any():
        return 0.0
    return float(freqs[mask][np.argmax(psd[mask])])

def spectral_slope(freqs, psd, fmin=2.0, fmax=40.0):
    mask = (freqs >= fmin) & (freqs <= fmax)
    if not mask.any() or np.all(psd[mask] <= 0):
        return 0.0
    log_f = np.log10(freqs[mask])
    log_p = np.log10(psd[mask] + 1e-20)
    coeffs = np.polyfit(log_f, log_p, 1)
    return float(coeffs[0])

results = {}
for i, ch in enumerate(ch_names):
    freqs, psd = sig.welch(data[i], fs=sfreq, nperseg=min(int(sfreq * 2), data.shape[1] // 4))

    # Entropy in different bands
    full_mask = (freqs >= 0.5) & (freqs <= 45)
    low_mask = (freqs >= 0.5) & (freqs <= 8)
    mid_mask = (freqs >= 8) & (freqs <= 30)

    ch_res = {
        "spectral_entropy_full": spectral_entropy(psd[full_mask]),
        "spectral_entropy_low": spectral_entropy(psd[low_mask]),
        "spectral_entropy_mid": spectral_entropy(psd[mid_mask]),
        "SEF50": spectral_edge(freqs[full_mask], psd[full_mask], 0.50),
        "SEF90": spectral_edge(freqs[full_mask], psd[full_mask], 0.90),
        "SEF95": spectral_edge(freqs[full_mask], psd[full_mask], 0.95),
        "peak_freq_alpha": peak_frequency(freqs, psd, 7, 14),
        "peak_freq_full": peak_frequency(freqs, psd, 1, 40),
        "spectral_slope": spectral_slope(freqs, psd),
    }
    results[ch] = ch_res

# Print results
print(f"\n{'Channel':>8s} {'Entropy':>8s} {'SEF50':>6s} {'SEF90':>6s} {'SEF95':>6s} "
      f"{'AlphaPk':>8s} {'Slope':>7s}")
for ch in ch_names:
    r = results[ch]
    print(f"{ch:>8s} {r['spectral_entropy_full']:8.3f} {r['SEF50']:6.1f} {r['SEF90']:6.1f} "
          f"{r['SEF95']:6.1f} {r['peak_freq_alpha']:8.1f} {r['spectral_slope']:7.2f}")

# Clinical insights
print("\n=== Clinical Markers ===")
for ch in ch_names:
    r = results[ch]
    notes = []
    if r["peak_freq_alpha"] < 8.5:
        notes.append("slow alpha peak (may indicate slowing)")
    if r["SEF90"] < 15:
        notes.append("low SEF90 (dominated by slow activity)")
    if r["spectral_slope"] > -0.5:
        notes.append("flat spectral slope (diffuse slowing pattern)")
    if r["spectral_entropy_full"] < 3.0:
        notes.append("low spectral entropy (narrow-band dominated)")
    if notes:
        print(f"  {ch}: {'; '.join(notes)}")

# Visualization
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# SEF distribution
sef90 = [results[ch]["SEF90"] for ch in ch_names]
axes[0, 0].barh(ch_names, sef90, color="steelblue")
axes[0, 0].set_xlabel("SEF90 (Hz)")
axes[0, 0].set_title("Spectral Edge Frequency (90th percentile)")
axes[0, 0].axvline(20, color="red", linestyle="--", alpha=0.5, label="typical ~20Hz")
axes[0, 0].legend()

# Alpha peak
apk = [results[ch]["peak_freq_alpha"] for ch in ch_names]
axes[0, 1].barh(ch_names, apk, color="coral")
axes[0, 1].set_xlabel("Peak α Frequency (Hz)")
axes[0, 1].set_title("Alpha Peak Frequency")
axes[0, 1].axvline(10, color="green", linestyle="--", alpha=0.5, label="typical ~10Hz")
axes[0, 1].legend()

# Entropy
ent = [results[ch]["spectral_entropy_full"] for ch in ch_names]
axes[1, 0].barh(ch_names, ent, color="mediumpurple")
axes[1, 0].set_xlabel("Spectral Entropy (bits)")
axes[1, 0].set_title("Spectral Entropy (Full Band)")

# Spectral slope
slopes = [results[ch]["spectral_slope"] for ch in ch_names]
axes[1, 1].barh(ch_names, slopes, color="seagreen")
axes[1, 1].set_xlabel("Slope (1/f exponent)")
axes[1, 1].set_title("Spectral Slope (log-log)")
axes[1, 1].axvline(-1, color="red", linestyle="--", alpha=0.5, label="1/f noise = -1")
axes[1, 1].legend()

plt.suptitle(f"Advanced Spectral Features — {stem}", fontsize=14)
plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_spectral_features.png"), dpi=150)
plt.close()

with open(os.path.join(OUTPUT_DIR, f"{stem}_spectral_features.json"), "w") as f:
    json.dump(results, f, indent=2)
print(f"\nPlot: {OUTPUT_DIR}/{stem}_spectral_features.png")
print(f"Data: {OUTPUT_DIR}/{stem}_spectral_features.json")
