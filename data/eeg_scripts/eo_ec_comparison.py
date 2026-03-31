"""Eyes Open vs Eyes Closed Comparison — reactivity analysis.
Compares band power between EO and EC recordings (two files or split by annotation).
Adapt EO_FILE and EC_FILE before running.
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

EO_FILE = "recording_EO.edf"
EC_FILE = "recording_EC.edf"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BANDS = {"delta":(0.5,4),"theta":(4,8),"alpha":(8,13),"lo_alpha":(8,10),
         "hi_alpha":(10,13),"SMR":(12,15),"beta":(13,30),"gamma":(30,45)}

def load_and_prep(path):
    ext = "." + path.rsplit(".", 1)[-1].lower()
    loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
    raw = loaders.get(ext, mne.io.read_raw_edf)(path, preload=True, verbose=False)
    raw.filter(0.5, 45.0, verbose=False)
    raw.notch_filter([60.0], verbose=False)
    return raw

def band_power(data, sfreq, fmin, fmax):
    powers = np.zeros(data.shape[0])
    for i in range(data.shape[0]):
        f, p = sig.welch(data[i], fs=sfreq, nperseg=min(int(sfreq * 2), data.shape[1] // 4))
        mask = (f >= fmin) & (f <= fmax)
        if mask.any():
            powers[i] = np.sqrt(_trapz(p[mask], f[mask])) * 1e6
    return powers

raw_eo = load_and_prep(EO_FILE)
raw_ec = load_and_prep(EC_FILE)

# Align channels
common = [ch for ch in raw_eo.ch_names if ch in raw_ec.ch_names]
if not common:
    print("No common channels between EO and EC files!")
    exit()
raw_eo.pick(common)
raw_ec.pick(common)
ch_names = common
sfreq = raw_eo.info["sfreq"]

data_eo = raw_eo.get_data()
data_ec = raw_ec.get_data()

stem = "EO_vs_EC"

results = {}
print(f"\n{'Channel':>8s}", end="")
for b in BANDS:
    print(f" {b+'_EO':>10s} {b+'_EC':>10s} {'ratio':>7s}", end="")
print()

for ci, ch in enumerate(ch_names):
    ch_res = {}
    print(f"{ch:>8s}", end="")
    for bname, (fmin, fmax) in BANDS.items():
        eo_p = float(band_power(data_eo[ci:ci+1], sfreq, fmin, fmax)[0])
        ec_p = float(band_power(data_ec[ci:ci+1], sfreq, fmin, fmax)[0])
        ratio = ec_p / eo_p if eo_p > 0 else 0
        ch_res[bname] = {"eo_uV": eo_p, "ec_uV": ec_p, "ec_eo_ratio": ratio}
        print(f" {eo_p:10.2f} {ec_p:10.2f} {ratio:7.2f}", end="")
    results[ch] = ch_res
    print()

# Alpha reactivity
print("\n=== Alpha Reactivity ===")
for ci, ch in enumerate(ch_names):
    r = results[ch]["alpha"]
    reactivity = (r["ec_uV"] - r["eo_uV"]) / r["eo_uV"] * 100 if r["eo_uV"] > 0 else 0
    status = "NORMAL" if reactivity > 20 else ("REDUCED" if reactivity > 0 else "PARADOXICAL")
    print(f"  {ch}: EO={r['eo_uV']:.2f} EC={r['ec_uV']:.2f} µV  "
          f"reactivity={reactivity:+.0f}%  [{status}]")

# Comparison plot
fig, axes = plt.subplots(2, 3, figsize=(16, 10))
for ax, (bname, (fmin, fmax)) in zip(axes.flat, list(BANDS.items())[:6]):
    eo_vals = [results[ch][bname]["eo_uV"] for ch in ch_names]
    ec_vals = [results[ch][bname]["ec_uV"] for ch in ch_names]
    x = np.arange(len(ch_names))
    ax.bar(x - 0.2, eo_vals, 0.4, label="EO", color="steelblue", alpha=0.8)
    ax.bar(x + 0.2, ec_vals, 0.4, label="EC", color="coral", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(ch_names, rotation=90, fontsize=6)
    ax.set_ylabel("µV")
    ax.set_title(f"{bname} ({fmin}-{fmax} Hz)")
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)
plt.suptitle(f"Eyes Open vs Eyes Closed — Band Power", fontsize=14)
plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_comparison.png"), dpi=150)
plt.close()

with open(os.path.join(OUTPUT_DIR, f"{stem}_comparison.json"), "w") as f:
    json.dump(results, f, indent=2)
print(f"\nPlot: {OUTPUT_DIR}/{stem}_comparison.png")
print(f"Data: {OUTPUT_DIR}/{stem}_comparison.json")
