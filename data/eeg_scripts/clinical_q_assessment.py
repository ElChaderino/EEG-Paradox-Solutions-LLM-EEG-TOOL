"""Clinical Q Assessment (Swingle-style) — systematic QEEG evaluation.
Computes clinical ratios, thresholds, and flags per Swingle's Clinical Q protocol.
Sites: Cz, O1, F3, F4, Fz with EO/EC/UT conditions.
Requires a single EDF file; uses 2-second epochs for metric extraction.
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
from scipy import signal as sig
import json, os, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
CONDITION = "EC"   # EC or EO (affects interpretation)
os.makedirs(OUTPUT_DIR, exist_ok=True)

BANDS = {
    "DELTA": (1.0, 4.0), "THETA": (4.0, 8.0), "ALPHA": (8.0, 12.0),
    "LO-ALPHA": (8.0, 10.0), "HI-ALPHA": (10.0, 12.0),
    "SMR": (12.0, 15.0), "BETA": (15.0, 20.0), "HI-BETA-GAMMA": (20.0, 40.0),
}

def band_rms(data, sfreq, fmin, fmax):
    try:
        sos = sig.butter(2, [fmin, fmax], btype="band", fs=sfreq, output="sos")
        filtered = sig.sosfiltfilt(sos, data)
        return float(np.sqrt(np.mean(filtered ** 2))) * 1e6
    except Exception:
        return 0.0

def band_rms_three_means(data, sfreq, fmin, fmax, nseg=3):
    n = len(data)
    if n < nseg:
        return band_rms(data, sfreq, fmin, fmax)
    seg_size = n // nseg
    vals = [band_rms(data[i * seg_size:(i + 1) * seg_size if i < nseg - 1 else n], sfreq, fmin, fmax) for i in range(nseg)]
    return float(np.mean(vals))

def peak_frequency(data, sfreq, fmin, fmax):
    freqs, psd = sig.welch(data, fs=sfreq, nperseg=min(256, len(data) // 2))
    mask = (freqs >= fmin) & (freqs <= fmax)
    if not mask.any():
        return (fmin + fmax) / 2
    return float(freqs[mask][np.argmax(psd[mask])])

def mean_frequency(data, sfreq, fmin, fmax):
    freqs, psd = sig.welch(data, fs=sfreq, nperseg=min(256, len(data) // 2))
    mask = (freqs >= fmin) & (freqs <= fmax)
    if not mask.any():
        return (fmin + fmax) / 2
    f, p = freqs[mask], psd[mask]
    total = _trapz(p, f)
    return float(_trapz(f * p, f) / total) if total > 0 else (fmin + fmax) / 2

import re

OLD_TO_NEW = {"T3":"T7","T4":"T8","T5":"P7","T6":"P8"}
def _clean_ch(name):
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

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)

mapping = {ch: _clean_ch(ch) for ch in raw.ch_names if _clean_ch(ch) != ch}
if mapping:
    raw.rename_channels(mapping)

raw.filter(0.5, 45.0, verbose=False)
raw.notch_filter([60.0], verbose=False)
sfreq = raw.info["sfreq"]
ch_names = raw.ch_names
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

def compute_site_metrics(ch_data, sfreq):
    metrics = {}
    for bname, (fmin, fmax) in BANDS.items():
        metrics[f"{bname}_MEAN"] = band_rms_three_means(ch_data, sfreq, fmin, fmax)
        metrics[f"{bname}_MODFRQ"] = peak_frequency(ch_data, sfreq, fmin, fmax)
        metrics[f"{bname}_MEANF"] = mean_frequency(ch_data, sfreq, fmin, fmax)
        try:
            sos = sig.butter(2, [fmin, fmax], btype="band", fs=sfreq, output="sos")
            metrics[f"{bname}_STDDEV"] = float(np.std(sig.sosfiltfilt(sos, ch_data))) * 1e6
        except Exception:
            metrics[f"{bname}_STDDEV"] = 0.0
    return metrics

results = {}
findings = []

def flag(name, value, direction, threshold, summary):
    is_sig = False
    if value is not None:
        if direction == "Greater" and value > threshold:
            is_sig = True
        elif direction == "Lower" and value < threshold:
            is_sig = True
    findings.append({"name": name, "value": round(value, 2) if value else None,
                     "threshold": f"{direction} {threshold}", "significant": is_sig, "summary": summary})
    if is_sig:
        print(f"  *** {name}: {value:.2f} [{direction} {threshold}] — {summary}")
    else:
        print(f"      {name}: {value:.2f} [{direction} {threshold}]")

print("=" * 70)
print("CLINICAL Q ASSESSMENT (Swingle Protocol)")
print("=" * 70)

for ci, ch in enumerate(ch_names):
    data_ch = raw.get_data()[ci]
    m = compute_site_metrics(data_ch, sfreq)
    results[ch] = m

    print(f"\n--- {ch} ---")
    for bname in BANDS:
        print(f"  {bname}: {m[f'{bname}_MEAN']:.2f} µV  peak={m[f'{bname}_MODFRQ']:.1f} Hz")

    theta = m["THETA_MEAN"]
    beta = m["BETA_MEAN"]
    alpha = m["ALPHA_MEAN"]
    smr = m["SMR_MEAN"]
    delta = m["DELTA_MEAN"]
    hibeta = m["HI-BETA-GAMMA_MEAN"]
    lo_alpha = m["LO-ALPHA_MEAN"]
    hi_alpha = m["HI-ALPHA_MEAN"]
    total_amp = sum(m[f"{b}_MEAN"] for b in BANDS)
    tb = theta / beta if beta > 0 else None
    ta = theta / alpha if alpha > 0 else None
    ts = theta / smr if smr > 0 else None
    hb_b = hibeta / beta if beta > 0 else None
    la_ha = lo_alpha / hi_alpha if hi_alpha > 0 else None
    apf = m["ALPHA_MODFRQ"]

    ch_upper = ch.upper()
    if ch_upper in ["CZ", "C3", "C4"]:
        if tb:
            flag(f"{ch} Theta/Beta", tb, "Greater", 2.2, "If >2.2 attention; >3.0 consider AD(H)D (Swingle p.24)")
        if ts:
            flag(f"{ch} Theta/SMR", ts, "Greater", 3.0, "If >3 restlessness, sleep disturbance (Swingle p.24)")
        flag(f"{ch} Total Amplitude", total_amp, "Greater", 60.0, "If >60 developmental/ASD/cognitive (Swingle p.24)")
        flag(f"{ch} Alpha Peak Freq", apf, "Lower", 9.5, "If <9.5 mental sluggishness")
    elif ch_upper in ["O1", "O2", "OZ"]:
        if tb:
            flag(f"{ch} Theta/Beta", tb, "Greater", 2.2, "<1.8 anxiety; >2.2 cognitive (Swingle p.24)")
        if ts:
            flag(f"{ch} Theta/SMR", ts, "Greater", 2.0, "Balance T/S for rest and motor (Swingle p.24)")
    elif ch_upper in ["F3", "F4"]:
        if tb:
            flag(f"{ch} Theta/Beta", tb, "Greater", 2.0, "Retrieval, impulse, emotional (Swingle p.25)")
        if ta:
            flag(f"{ch} Theta/Alpha", ta, "Lower", 1.0, "Target 1.2-1.6; <1.0 flagged (Swingle p.25)")
        flag(f"{ch} Total Amplitude", total_amp, "Greater", 60.0, "If >60 developmental/ASD (Swingle p.25)")
    elif ch_upper in ["FZ"]:
        flag(f"{ch} Delta", delta, "Greater", 9.0, "Elevated: concentration, developmental, pain (Swingle p.25)")
        if hb_b:
            if hb_b < 0.45 or hb_b > 0.55:
                flag(f"{ch} HiBeta/Beta", hb_b, "Greater", 0.55, "0.45-0.55 target; low=passive, high=OC/anxiety (Swingle p.25)")
        flag(f"{ch} Sum HiBeta+Beta", hibeta + beta, "Greater", 15.0, "Overarousal if >15 (Swingle p.25)")
        if la_ha:
            flag(f"{ch} LoAlpha/HiAlpha", la_ha, "Greater", 1.5, "Target 1.0-1.5; >1.5 flagged (Swingle p.25)")

# F3 vs F4 asymmetry
if "F3" in ch_names and "F4" in ch_names:
    print("\n--- F3 vs F4 Asymmetry ---")
    for bname in ["THETA", "ALPHA", "BETA"]:
        f3 = results["F3"][f"{bname}_MEAN"]
        f4 = results["F4"][f"{bname}_MEAN"]
        denom = min(f3, f4)
        pct = ((f4 - f3) / denom * 100) if denom > 0 else 0
        status = "ASYMMETRIC" if abs(pct) > 15 else "OK"
        print(f"  {bname}: F3={f3:.2f} F4={f4:.2f}  diff={pct:+.1f}% [{status}]")
        if abs(pct) > 15:
            findings.append({"name": f"F3-F4 {bname} asymmetry", "value": round(pct, 1),
                             "significant": True, "summary": f">15% asymmetry: consider lateralization"})

with open(os.path.join(OUTPUT_DIR, f"{stem}_clinicalq.json"), "w") as f:
    json.dump({"metrics": results, "findings": findings}, f, indent=2, default=str)
print(f"\nResults: {OUTPUT_DIR}/{stem}_clinicalq.json")
print(f"Flagged findings: {sum(1 for f in findings if f.get('significant'))}/{len(findings)}")
