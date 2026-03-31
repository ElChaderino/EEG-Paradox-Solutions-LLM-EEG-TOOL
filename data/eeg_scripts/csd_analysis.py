"""Current Source Density (CSD) Analysis — spatial filtering for better localization.
Applies CSD transformation (Laplacian) to enhance local cortical activity and
reduce volume conduction. Generates CSD topomaps and compares with raw topomaps.
Requires montage-compatible channel names. Adapt INPUT_FILE before running.
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
import json, os, re, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
CSD_STIFFNESS = 4
CSD_LAMBDA2 = 1e-5
os.makedirs(OUTPUT_DIR, exist_ok=True)

OLD_TO_NEW = {"T3": "T7", "T4": "T8", "T5": "P7", "T6": "P8"}

def clean_ch(name):
    name = re.sub(r"^EEG[\s\-]+", "", name.strip(), flags=re.IGNORECASE)
    for sfx in ["-REF", "-LE", "-RE", "-M1", "-M2", "-A1", "-A2", "-Av", "-AV"]:
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

BANDS = {"delta": (0.5, 4), "theta": (4, 8), "alpha": (8, 13), "beta": (13, 30), "gamma": (30, 45)}

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)

# Standardize channels
mapping = {ch: clean_ch(ch) for ch in raw.ch_names if clean_ch(ch) != ch}
if mapping:
    raw.rename_channels(mapping)

raw.filter(0.5, 45.0, verbose=False)
raw.notch_filter([60.0], verbose=False)

# Set montage
montage = mne.channels.make_standard_montage("standard_1020")
raw.set_montage(montage, on_missing="warn", verbose=False)

# Keep only channels with known positions
good_chs = []
for i, ch in enumerate(raw.ch_names):
    loc = raw.info["chs"][i].get("loc", np.zeros(3))
    if not all(loc[:3] == 0):
        good_chs.append(ch)
if len(good_chs) < 4:
    print(f"Only {len(good_chs)} channels with positions. Need at least 4 for CSD.")
    exit()
raw.pick(good_chs)

sfreq = raw.info["sfreq"]
data_raw = raw.get_data()
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

# Apply CSD
print(f"Applying CSD (stiffness={CSD_STIFFNESS}, lambda2={CSD_LAMBDA2})...")
try:
    raw_csd = mne.preprocessing.compute_current_source_density(
        raw.copy(), stiffness=CSD_STIFFNESS, lambda2=CSD_LAMBDA2, verbose=False)
    data_csd = raw_csd.get_data()
    print(f"CSD applied to {len(good_chs)} channels")
except Exception as e:
    print(f"CSD failed: {e}")
    exit()

# Compare raw vs CSD band power
results = {"raw": {}, "csd": {}}
for ci, ch in enumerate(raw.ch_names):
    for dataset_name, dataset in [("raw", data_raw), ("csd", data_csd)]:
        ch_bands = {}
        freqs, psd = sig.welch(dataset[ci], fs=sfreq, nperseg=min(int(sfreq * 2), dataset.shape[1] // 4))
        for bname, (fmin, fmax) in BANDS.items():
            mask = (freqs >= fmin) & (freqs <= fmax)
            if mask.any():
                ch_bands[bname] = float(np.sqrt(_trapz(psd[mask], freqs[mask])) * 1e6)
            else:
                ch_bands[bname] = 0
        results[dataset_name][ch] = ch_bands

# Print comparison
print(f"\n{'Channel':>8s}", end="")
for b in BANDS:
    print(f" {b+'_raw':>10s} {b+'_csd':>10s}", end="")
print()
for ch in raw.ch_names:
    print(f"{ch:>8s}", end="")
    for b in BANDS:
        r = results["raw"][ch].get(b, 0)
        c = results["csd"][ch].get(b, 0)
        print(f" {r:10.2f} {c:10.2f}", end="")
    print()

# Side-by-side topomaps (raw vs CSD)
fig, axes = plt.subplots(2, 5, figsize=(20, 8))
for bi, (bname, (fmin, fmax)) in enumerate(BANDS.items()):
    raw_powers = np.array([results["raw"][ch][bname] for ch in raw.ch_names])
    csd_powers = np.array([results["csd"][ch][bname] for ch in raw.ch_names])

    r0, r1 = float(np.percentile(raw_powers, 5)), float(np.percentile(raw_powers, 95))
    if r1 <= r0:
        r1 = r0 + 1e-30
    mne.viz.plot_topomap(
        raw_powers, raw.info, axes=axes[0, bi], show=False,
        cmap="viridis", vlim=(r0, r1),
    )
    axes[0, bi].set_title(f"Raw {bname}")

    c_mag = max(
        float(np.percentile(np.abs(csd_powers), 99)),
        float(np.max(np.abs(csd_powers))) if csd_powers.size else 1e-12,
        1e-12,
    )
    mne.viz.plot_topomap(
        csd_powers, raw_csd.info, axes=axes[1, bi], show=False,
        cmap="RdBu_r", vlim=(-c_mag, c_mag),
    )
    axes[1, bi].set_title(f"CSD {bname}")

plt.suptitle(f"Raw vs CSD Topomaps — {stem}", fontsize=14)
plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_csd_comparison.png"), dpi=150)
plt.close()

# Save CSD data
csd_fif = os.path.join(OUTPUT_DIR, f"{stem}_csd.fif")
raw_csd.save(csd_fif, overwrite=True, verbose=False)

with open(os.path.join(OUTPUT_DIR, f"{stem}_csd_results.json"), "w") as f:
    json.dump(results, f, indent=2)
print(f"\nTopomaps: {OUTPUT_DIR}/{stem}_csd_comparison.png")
print(f"CSD data: {csd_fif}")
print(f"Results: {OUTPUT_DIR}/{stem}_csd_results.json")
