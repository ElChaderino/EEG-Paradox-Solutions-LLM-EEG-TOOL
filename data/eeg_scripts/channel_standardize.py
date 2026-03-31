"""Channel Name Standardization — universal EDF channel mapping.
Maps vendor-specific channel names (Cygnet, BioExplorer, BrainMaster, generic)
to standard 10-20 nomenclature. Detects format, renames, drops non-EEG channels.
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
import re, json, os, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

STANDARD_1020 = [
    "Fp1","Fp2","F7","F3","Fz","F4","F8",
    "T7","C3","Cz","C4","T8",
    "P7","P3","Pz","P4","P8","O1","O2","Oz","Fpz",
]

OLD_TO_NEW = {"T3":"T7","T4":"T8","T5":"P7","T6":"P8"}
NEW_TO_OLD = {v: k for k, v in OLD_TO_NEW.items()}

VENDOR_MAPS = {
    "cygnet": {
        "Fp1-LE":"Fp1","Fp2-LE":"Fp2","F3-LE":"F3","F4-LE":"F4",
        "F7-LE":"F7","F8-LE":"F8","Fz-LE":"Fz",
        "C3-LE":"C3","C4-LE":"C4","Cz-LE":"Cz",
        "P3-LE":"P3","P4-LE":"P4","Pz-LE":"Pz",
        "O1-LE":"O1","O2-LE":"O2","Oz-LE":"Oz",
        "T3-LE":"T7","T4-LE":"T8","T5-LE":"P7","T6-LE":"P8",
        "T7-LE":"T7","T8-LE":"T8","P7-LE":"P7","P8-LE":"P8",
    },
    "av_reference": {
        "Fp1-Av":"Fp1","Fp2-Av":"Fp2","F3-Av":"F3","F4-Av":"F4",
        "F7-Av":"F7","F8-Av":"F8","Fz-Av":"Fz",
        "C3-Av":"C3","C4-Av":"C4","Cz-Av":"Cz",
        "P3-Av":"P3","P4-Av":"P4","Pz-Av":"Pz",
        "O1-Av":"O1","O2-Av":"O2","Oz-Av":"Oz",
        "T3-Av":"T7","T4-Av":"T8","T5-Av":"P7","T6-Av":"P8",
    },
    "generic_eeg_prefix": {
        "EEG Fp1":"Fp1","EEG Fp2":"Fp2","EEG F3":"F3","EEG F4":"F4",
        "EEG F7":"F7","EEG F8":"F8","EEG Fz":"Fz",
        "EEG C3":"C3","EEG C4":"C4","EEG Cz":"Cz",
        "EEG P3":"P3","EEG P4":"P4","EEG Pz":"Pz",
        "EEG O1":"O1","EEG O2":"O2","EEG Oz":"Oz",
        "EEG T3":"T7","EEG T4":"T8","EEG T5":"P7","EEG T6":"P8",
        "EEG T7":"T7","EEG T8":"T8","EEG P7":"P7","EEG P8":"P8",
    },
}

NON_EEG = {"LABEL","REF","REFERENCE","GROUND","GND","A1","A2","M1","M2",
           "ECG","EKG","EMG","EOG","VEOG","HEOG","RESP","TRIGGER","STATUS",
           "EVENT","STI","DC","SAO2","PHOTIC","ANNOTATIONS"}

def clean_ch(name):
    name = re.sub(r"^EEG[\s\-]+", "", name.strip(), flags=re.IGNORECASE)
    for sfx in ["-REF","-LE","-RE","-M1","-M2","-A1","-A2","-Av","-AV","-AVG"]:
        name = re.sub(re.escape(sfx)+"$", "", name, flags=re.IGNORECASE)
    name = name.strip()
    u = name.upper()
    if u == "FPZ": return "Fpz"
    if u.startswith("FP"): return "Fp" + u[2:]
    if len(u) == 2 and u[1] == "Z": return u[0] + "z"
    if len(u) >= 2:
        r = u[0] + u[1:].lower()
        return OLD_TO_NEW.get(r, r)
    return name

def detect_format(ch_names):
    if any("-LE" in ch for ch in ch_names): return "cygnet"
    if any("-Av" in ch for ch in ch_names): return "av_reference"
    if any(ch.startswith("EEG ") for ch in ch_names): return "generic_eeg_prefix"
    std_count = sum(1 for ch in ch_names if ch in STANDARD_1020)
    if std_count >= 5: return "standard"
    return "unknown"

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)

original_names = list(raw.ch_names)
fmt = detect_format(original_names)
print(f"File: {INPUT_FILE}")
print(f"Original channels ({len(original_names)}): {', '.join(original_names)}")
print(f"Detected format: {fmt}")

# Map channels
rename_map = {}
vendor_map = VENDOR_MAPS.get(fmt, {})
for ch in raw.ch_names:
    if ch in vendor_map:
        rename_map[ch] = vendor_map[ch]
    else:
        cleaned = clean_ch(ch)
        if cleaned != ch:
            rename_map[ch] = cleaned

if rename_map:
    # Avoid duplicate target names
    seen = set()
    final_map = {}
    for old, new in rename_map.items():
        if new in seen:
            continue
        seen.add(new)
        final_map[old] = new
    raw.rename_channels(final_map)
    print(f"\nRenamed {len(final_map)} channels:")
    for old, new in final_map.items():
        print(f"  {old:>20s} → {new}")

# Drop non-EEG
drop = [ch for ch in raw.ch_names if ch.upper() in NON_EEG]
if drop:
    raw.drop_channels(drop)
    print(f"\nDropped non-EEG: {', '.join(drop)}")

# Identify standard 10-20 matches
matched = [ch for ch in raw.ch_names if ch in STANDARD_1020]
unmatched = [ch for ch in raw.ch_names if ch not in STANDARD_1020]
print(f"\nFinal channels ({len(raw.ch_names)}):")
print(f"  Standard 10-20: {', '.join(matched)} ({len(matched)})")
if unmatched:
    print(f"  Non-standard: {', '.join(unmatched)} ({len(unmatched)})")

# Set montage
try:
    montage = mne.channels.make_standard_montage("standard_1020")
    raw.set_montage(montage, on_missing="warn", verbose=False)
    with_pos = sum(1 for i in range(len(raw.ch_names)) if not all(raw.info["chs"][i]["loc"][:3] == 0))
    print(f"\nMontage applied: {with_pos}/{len(raw.ch_names)} channels have positions")
except Exception as e:
    print(f"\nMontage failed: {e}")

# Save cleaned EDF
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
out_path = os.path.join(OUTPUT_DIR, f"{stem}_standardized.fif")
raw.save(out_path, overwrite=True, verbose=False)

report = {"original": original_names, "format": fmt, "renamed": rename_map,
          "dropped": drop, "final": list(raw.ch_names), "standard_matched": matched, "unmatched": unmatched}
with open(os.path.join(OUTPUT_DIR, f"{stem}_channel_report.json"), "w") as f:
    json.dump(report, f, indent=2)
print(f"\nStandardized file: {out_path}")
print(f"Report: {OUTPUT_DIR}/{stem}_channel_report.json")
