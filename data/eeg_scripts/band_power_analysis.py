"""Band Power Analysis — Welch PSD, absolute/relative power, topomaps.
Produces per-channel band tables, PSD plot, and band topomaps.
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
from scipy import signal
import json, os, re, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BANDS = {
    "delta":    (0.5, 4.0),
    "theta":    (4.0, 8.0),
    "alpha":    (8.0, 13.0),
    "lo_alpha": (8.0, 10.0),
    "hi_alpha": (10.0, 13.0),
    "SMR":      (12.0, 15.0),
    "beta":     (13.0, 30.0),
    "hi_beta":  (20.0, 30.0),
    "gamma":    (30.0, 45.0),
}

STANDARD_1020 = [
    "Fp1","Fp2","F7","F3","Fz","F4","F8",
    "T7","C3","Cz","C4","T8",
    "P7","P3","Pz","P4","P8","O1","O2","Oz",
]
OLD_TO_NEW = {"T3":"T7","T4":"T8","T5":"P7","T6":"P8"}

def clean_ch(name):
    name = re.sub(r"^EEG[\s\-]+", "", name.strip(), flags=re.IGNORECASE)
    for sfx in ["-REF","-LE","-RE","-M1","-M2","-A1","-A2","-Av","-AV"]:
        name = re.sub(re.escape(sfx), "", name, flags=re.IGNORECASE)
    name = name.strip()
    u = name.upper()
    if u == "FPZ": return "Fpz"
    if u.startswith("FP"): return "Fp" + u[2:]
    if len(u) == 2 and u[1] == "Z": return u[0] + "z"
    if len(u) >= 2:
        r = u[0] + u[1:].lower()
        return OLD_TO_NEW.get(r, r)
    return name

# Load
ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf,
            ".fif": mne.io.read_raw_fif, ".set": mne.io.read_raw_eeglab}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)

# Standardize channel names
mapping = {}
for ch in raw.ch_names:
    cleaned = clean_ch(ch)
    if cleaned != ch:
        mapping[ch] = cleaned
if mapping:
    raw.rename_channels(mapping)

# Pick EEG channels that match 10-20
eeg_picks = [ch for ch in raw.ch_names if ch in STANDARD_1020 or ch in ["Fpz","Oz","Fz","Cz","Pz"]]
if not eeg_picks:
    eeg_picks = raw.ch_names[:19]
    print(f"Warning: no 10-20 channels found, using first {len(eeg_picks)} channels")
raw.pick(eeg_picks)

# Filter
raw.filter(0.5, 45.0, verbose=False)
raw.notch_filter([60.0], verbose=False)

sfreq = raw.info["sfreq"]
data = raw.get_data()
n_ch = data.shape[0]
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

# Compute band power per channel
results = {}
for i, ch in enumerate(raw.ch_names):
    freqs, psd = signal.welch(data[i], fs=sfreq, nperseg=min(int(sfreq * 2), data.shape[1] // 4))
    total = _trapz(psd, freqs)
    ch_bands = {}
    for bname, (fmin, fmax) in BANDS.items():
        mask = (freqs >= fmin) & (freqs <= fmax)
        if not mask.any():
            continue
        abs_power = _trapz(psd[mask], freqs[mask])
        amp_uv = np.sqrt(abs_power) * 1e6
        rel_power = abs_power / total if total > 0 else 0
        ch_bands[bname] = {"abs_uV2": float(abs_power * 1e12), "amp_uV": float(amp_uv),
                           "rel": float(rel_power)}
    results[ch] = ch_bands

# Print table
print(f"\n{'Channel':>8s}", end="")
for b in BANDS:
    print(f" {b:>10s}", end="")
print()
for ch in raw.ch_names:
    print(f"{ch:>8s}", end="")
    for b in BANDS:
        v = results.get(ch, {}).get(b, {}).get("amp_uV", 0)
        print(f" {v:10.2f}", end="")
    print(" µV")

# Ratios
print("\nKey Ratios:")
for ch in raw.ch_names:
    tb = results[ch].get("theta", {}).get("amp_uV", 0)
    bb = results[ch].get("beta", {}).get("amp_uV", 0)
    ratio = tb / bb if bb > 0 else 0
    print(f"  {ch}: Theta/Beta = {ratio:.2f}")

# PSD plot
fig, ax = plt.subplots(figsize=(12, 6))
for i, ch in enumerate(raw.ch_names):
    freqs, psd = signal.welch(data[i], fs=sfreq, nperseg=min(int(sfreq * 2), data.shape[1] // 4))
    ax.semilogy(freqs, psd * 1e12, alpha=0.6, label=ch)
ax.set_xlabel("Frequency (Hz)")
ax.set_ylabel("PSD (µV²/Hz)")
ax.set_title(f"Power Spectral Density — {stem}")
ax.set_xlim(0.5, 45)
ax.legend(fontsize=6, ncol=4)
ax.grid(True, alpha=0.3)
for bname, (fmin, fmax) in [("delta",(0.5,4)),("theta",(4,8)),("alpha",(8,13)),("beta",(13,30)),("gamma",(30,45))]:
    ax.axvspan(fmin, fmax, alpha=0.05, color="gray")
    ax.text((fmin+fmax)/2, ax.get_ylim()[1]*0.8, bname, ha="center", fontsize=7, alpha=0.5)
plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_psd.png"), dpi=150)
plt.close()

# Topomaps
try:
    montage = mne.channels.make_standard_montage("standard_1020")
    raw.set_montage(montage, on_missing="warn", verbose=False)
    for bname, (fmin, fmax) in [("delta",(0.5,4)),("theta",(4,8)),("alpha",(8,13)),("beta",(13,30)),("gamma",(30,45))]:
        powers = np.array([results[ch].get(bname, {}).get("amp_uV", 0) for ch in raw.ch_names])
        fig, ax = plt.subplots(figsize=(4, 4))
        v0, v1 = float(np.percentile(powers, 5)), float(np.percentile(powers, 95))
        if v1 <= v0:
            v1 = v0 + 1e-30
        mne.viz.plot_topomap(
            powers, raw.info, axes=ax, show=False,
            cmap="viridis", vlim=(v0, v1),
        )
        ax.set_title(f"{bname} ({fmin}-{fmax} Hz) µV")
        fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_topo_{bname}.png"), dpi=150)
        plt.close()
    print(f"\nTopomaps saved to {OUTPUT_DIR}/")
except Exception as e:
    print(f"Topomap generation skipped: {e}")

# Save JSON
with open(os.path.join(OUTPUT_DIR, f"{stem}_band_power.json"), "w") as f:
    json.dump(results, f, indent=2)
print(f"Results saved to {OUTPUT_DIR}/{stem}_band_power.json")
print(f"PSD plot saved to {OUTPUT_DIR}/{stem}_psd.png")
