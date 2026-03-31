"""Phase-Amplitude Coupling (PAC) — modulation index analysis.
Computes cross-frequency coupling between phase of low bands and amplitude
of high bands. Key marker for cortical communication and cognitive function.
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

PHASE_BANDS = {"theta": (4, 8), "alpha": (8, 13), "beta": (13, 30)}
AMP_BANDS = {"gamma": (30, 45), "hi_gamma": (45, 80)}
N_PHASE_BINS = 18

def bandpass(x, fs, fmin, fmax, order=4):
    nyq = fs / 2
    lo = max(fmin, 0.1) / nyq
    hi = min(fmax, nyq * 0.99) / nyq
    b, a = signal.butter(order, [lo, hi], btype="band")
    return signal.filtfilt(b, a, x)

def modulation_index(phase_sig, amp_sig, n_bins=N_PHASE_BINS):
    phase = np.angle(signal.hilbert(phase_sig))
    amp = np.abs(signal.hilbert(amp_sig))
    bin_edges = np.linspace(-np.pi, np.pi, n_bins + 1)
    mean_amp = np.zeros(n_bins)
    for b in range(n_bins):
        mask = (phase >= bin_edges[b]) & (phase < bin_edges[b + 1])
        if mask.any():
            mean_amp[b] = np.mean(amp[mask])
    total = mean_amp.sum()
    if total == 0:
        return 0.0, mean_amp
    p = mean_amp / total
    p = p[p > 0]
    kl = np.sum(p * np.log(p * n_bins))
    mi = kl / np.log(n_bins)
    return float(mi), mean_amp

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)
raw.filter(0.5, 80.0, verbose=False)
raw.notch_filter([60.0], verbose=False)

sfreq = raw.info["sfreq"]
data = raw.get_data()
ch_names = raw.ch_names
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

results = {}
for ci, ch in enumerate(ch_names):
    ch_results = {}
    for pname, (pfmin, pfmax) in PHASE_BANDS.items():
        for aname, (afmin, afmax) in AMP_BANDS.items():
            if afmin >= sfreq / 2:
                continue
            p_filt = bandpass(data[ci], sfreq, pfmin, pfmax)
            a_filt = bandpass(data[ci], sfreq, afmin, min(afmax, sfreq / 2 - 1))
            mi, amp_dist = modulation_index(p_filt, a_filt)
            key = f"{pname}_phase-{aname}_amp"
            ch_results[key] = {"MI": mi}
    results[ch] = ch_results

# Print results
print(f"\n{'Channel':>8s}", end="")
for pname in PHASE_BANDS:
    for aname in AMP_BANDS:
        print(f" {pname[:3]}-{aname[:3]:>8s}", end="")
print()
for ch in ch_names:
    print(f"{ch:>8s}", end="")
    for pname in PHASE_BANDS:
        for aname in AMP_BANDS:
            key = f"{pname}_phase-{aname}_amp"
            mi = results[ch].get(key, {}).get("MI", 0)
            print(f" {mi:11.4f}", end="")
    print()

# Highlight significant coupling
print("\n=== Significant PAC (MI > 0.01) ===")
for ch in ch_names:
    for key, vals in results[ch].items():
        if vals["MI"] > 0.01:
            print(f"  {ch} {key}: MI={vals['MI']:.4f}")

# Comodulogram for first channel with montage
ch0 = 0
phase_freqs = np.arange(2, 30, 1)
amp_freqs = np.arange(20, min(81, int(sfreq / 2)), 2)
comod = np.zeros((len(amp_freqs), len(phase_freqs)))

for pi, pf in enumerate(phase_freqs):
    p_filt = bandpass(data[ch0], sfreq, max(pf - 1, 0.5), pf + 1)
    for ai, af in enumerate(amp_freqs):
        if af + 2 >= sfreq / 2:
            continue
        a_filt = bandpass(data[ch0], sfreq, max(af - 2, 0.5), min(af + 2, sfreq / 2 - 1))
        mi, _ = modulation_index(p_filt, a_filt)
        comod[ai, pi] = mi

fig, ax = plt.subplots(figsize=(10, 6))
im = ax.pcolormesh(phase_freqs, amp_freqs, comod, cmap="hot", shading="auto")
ax.set_xlabel("Phase frequency (Hz)")
ax.set_ylabel("Amplitude frequency (Hz)")
ax.set_title(f"Comodulogram — {ch_names[ch0]} — {stem}")
plt.colorbar(im, ax=ax, label="Modulation Index")
plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_comodulogram.png"), dpi=150)
plt.close()

with open(os.path.join(OUTPUT_DIR, f"{stem}_pac.json"), "w") as f:
    json.dump(results, f, indent=2)
print(f"\nComodulogram: {OUTPUT_DIR}/{stem}_comodulogram.png")
print(f"Data: {OUTPUT_DIR}/{stem}_pac.json")
