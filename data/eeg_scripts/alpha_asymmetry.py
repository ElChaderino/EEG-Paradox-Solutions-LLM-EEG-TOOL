"""Alpha Asymmetry Analysis — interhemispheric asymmetry and clinical ratios.
Computes (L-R)/(L+R) asymmetry for homologous pairs across all bands,
with focus on frontal alpha asymmetry (FAA) for mood/motivation markers.
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
from mne.time_frequency import psd_array_welch
import json, os, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BANDS = {"delta":(0.5,4),"theta":(4,8),"alpha":(8,13),"lo_alpha":(8,10),
         "hi_alpha":(10,13),"SMR":(12,15),"beta":(13,30),"hi_beta":(20,30),"gamma":(30,45)}

HOMOLOGOUS_PAIRS = [
    ("Fp1","Fp2"), ("F7","F8"), ("F3","F4"), ("C3","C4"),
    ("T7","T8"), ("P7","P8"), ("P3","P4"), ("O1","O2"),
]

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)
raw.filter(0.5, 45.0, verbose=False)
raw.notch_filter([60.0], verbose=False)
sfreq = raw.info["sfreq"]
data = raw.get_data()
ch_names = raw.ch_names
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

def band_amplitude(sig, sfreq, fmin, fmax):
    psd, _ = psd_array_welch(sig.reshape(1, -1), sfreq=sfreq, fmin=fmin, fmax=fmax, n_fft=2048, verbose=False)
    return float(np.sqrt(np.mean(psd * 1e12)))

avail = [(l, r) for l, r in HOMOLOGOUS_PAIRS if l in ch_names and r in ch_names]
if not avail:
    print("No homologous pairs found in channel names. Available:", ch_names)
    exit()

results = {}
print(f"\n{'Pair':>10s}", end="")
for b in BANDS:
    print(f" {b:>10s}", end="")
print()

for left, right in avail:
    li, ri = ch_names.index(left), ch_names.index(right)
    pair_name = f"{left}-{right}"
    pair_results = {}
    print(f"{pair_name:>10s}", end="")
    for bname, (fmin, fmax) in BANDS.items():
        amp_l = band_amplitude(data[li], sfreq, fmin, fmax)
        amp_r = band_amplitude(data[ri], sfreq, fmin, fmax)
        asym = (amp_l - amp_r) / (amp_l + amp_r) if (amp_l + amp_r) > 0 else 0
        pair_results[bname] = {"left_uV": amp_l, "right_uV": amp_r, "asymmetry": float(asym)}
        print(f" {asym:10.3f}", end="")
    results[pair_name] = pair_results
    print()

# Clinical interpretation
print("\n=== Clinical Interpretation ===")
faa_pair = None
for l, r in [("F3","F4"),("F7","F8"),("Fp1","Fp2")]:
    if f"{l}-{r}" in results:
        faa_pair = f"{l}-{r}"
        break

if faa_pair:
    faa = results[faa_pair]["alpha"]["asymmetry"]
    print(f"\nFrontal Alpha Asymmetry ({faa_pair}): {faa:.3f}")
    if faa > 0.1:
        print("  → Greater LEFT alpha = relatively LESS left activation")
        print("  → Associated with withdrawal motivation, depression risk")
    elif faa < -0.1:
        print("  → Greater RIGHT alpha = relatively LESS right activation")
        print("  → Associated with approach motivation")
    else:
        print("  → Roughly symmetric — within normal range")

    # Log-transformed FAA (common in research)
    la = results[faa_pair]["alpha"]["left_uV"]
    ra = results[faa_pair]["alpha"]["right_uV"]
    if la > 0 and ra > 0:
        ln_faa = np.log(ra) - np.log(la)
        print(f"  Log-transformed FAA (ln R - ln L): {ln_faa:.3f}")
        print(f"  (Positive = greater relative left activation = approach)")

# Plot asymmetry
fig, ax = plt.subplots(figsize=(12, 6))
x = np.arange(len(avail))
width = 0.15
band_list = ["delta","theta","alpha","beta","gamma"]
for bi, bname in enumerate(band_list):
    vals = [results[f"{l}-{r}"][bname]["asymmetry"] for l, r in avail]
    ax.bar(x + bi * width, vals, width, label=bname, alpha=0.8)
ax.set_xticks(x + width * 2)
ax.set_xticklabels([f"{l}-{r}" for l, r in avail], rotation=45)
ax.set_ylabel("Asymmetry Index (L-R)/(L+R)")
ax.set_title(f"Interhemispheric Asymmetry — {stem}")
ax.axhline(0, color="black", linewidth=0.5)
ax.axhline(0.1, color="red", linewidth=0.5, linestyle="--", alpha=0.5)
ax.axhline(-0.1, color="red", linewidth=0.5, linestyle="--", alpha=0.5)
ax.legend()
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_asymmetry.png"), dpi=150)
plt.close()

with open(os.path.join(OUTPUT_DIR, f"{stem}_asymmetry.json"), "w") as f:
    json.dump(results, f, indent=2)
print(f"\nPlot: {OUTPUT_DIR}/{stem}_asymmetry.png")
print(f"Data: {OUTPUT_DIR}/{stem}_asymmetry.json")
