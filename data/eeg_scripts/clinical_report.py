"""Clinical EEG Report Generator — automated narrative from band power analysis.
Runs full spectral analysis and produces a structured clinical-style text report.
Adapt INPUT_FILE and CLIENT_INFO before running.
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
from datetime import datetime
import json, os, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CLIENT_INFO = {
    "name": "[Client Name]",
    "age": "[Age]",
    "condition": "EO",   # EO or EC
    "referral": "[Referral reason]",
}

BANDS = {"delta":(0.5,4),"theta":(4,8),"alpha":(8,13),"lo_alpha":(8,10),
         "hi_alpha":(10,13),"SMR":(12,15),"beta":(13,30),"hi_beta":(20,30),"gamma":(30,45)}

BAND_NORMS = {
    "delta": (2.0, 8.0), "theta": (3.0, 7.0), "alpha": (5.0, 15.0),
    "lo_alpha": (3.0, 10.0), "hi_alpha": (3.0, 10.0), "SMR": (2.0, 6.0),
    "beta": (3.0, 10.0), "hi_beta": (1.0, 5.0), "gamma": (0.5, 3.0),
}

BAND_FUNCTIONS = {
    "delta": "associated with deep sleep, healing, and cortical inhibition; excess in waking = slowing/injury",
    "theta": "linked to drowsiness, meditation, memory encoding; excess = poor attention/focus",
    "alpha": "relaxed wakefulness, posterior dominant rhythm; reduced = anxiety or cognitive effort",
    "lo_alpha": "thalamo-cortical idle; reflects attentional disengagement",
    "hi_alpha": "active inhibition and semantic processing",
    "SMR": "sensorimotor idle, focused calm; training target for attention protocols",
    "beta": "active cognition, focus; excess = anxiety, rumination",
    "hi_beta": "hypervigilance, anxiety marker; often elevated in stress/PTSD",
    "gamma": "higher-order binding, perception; difficult to record without artifact control",
}

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)
raw.filter(0.5, 45.0, verbose=False)
raw.notch_filter([60.0], verbose=False)
sfreq = raw.info["sfreq"]
data = raw.get_data()
ch_names = raw.ch_names
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

# Compute band power
results = {}
for i, ch in enumerate(ch_names):
    freqs, psd = signal.welch(data[i], fs=sfreq, nperseg=min(int(sfreq * 2), data.shape[1] // 4))
    total = _trapz(psd, freqs)
    ch_bands = {}
    for bname, (fmin, fmax) in BANDS.items():
        mask = (freqs >= fmin) & (freqs <= fmax)
        if not mask.any():
            continue
        abs_power = _trapz(psd[mask], freqs[mask])
        amp_uv = np.sqrt(abs_power) * 1e6
        rel = abs_power / total if total > 0 else 0
        ch_bands[bname] = {"amp_uV": float(amp_uv), "rel": float(rel)}
    results[ch] = ch_bands

# Theta/Beta ratios
tb_ratios = {}
for ch in ch_names:
    t = results[ch].get("theta", {}).get("amp_uV", 0)
    b = results[ch].get("beta", {}).get("amp_uV", 0)
    tb_ratios[ch] = t / b if b > 0 else 0

# Generate report
lines = []
lines.append("=" * 70)
lines.append("PARADOX SOLUTIONS — QUANTITATIVE EEG ANALYSIS REPORT")
lines.append("=" * 70)
lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
lines.append(f"Client: {CLIENT_INFO['name']}")
lines.append(f"Age: {CLIENT_INFO['age']}")
lines.append(f"Condition: {CLIENT_INFO['condition']}")
lines.append(f"Referral: {CLIENT_INFO['referral']}")
lines.append(f"Recording: {INPUT_FILE}")
lines.append(f"Duration: {data.shape[1]/sfreq:.0f}s, {len(ch_names)} channels, {sfreq} Hz")
lines.append("")

# Executive summary
lines.append("-" * 70)
lines.append("1. EXECUTIVE SUMMARY")
lines.append("-" * 70)
findings = []
global_tb = np.mean(list(tb_ratios.values()))
if global_tb > 3.0:
    findings.append(f"Elevated global theta/beta ratio ({global_tb:.1f}), suggesting attentional difficulties")
for ch in ch_names:
    for bname in ["delta", "theta", "hi_beta"]:
        amp = results[ch].get(bname, {}).get("amp_uV", 0)
        lo, hi = BAND_NORMS.get(bname, (0, 999))
        if amp > hi * 1.5:
            findings.append(f"Elevated {bname} at {ch} ({amp:.1f} µV)")
        elif amp < lo * 0.5 and bname == "alpha":
            findings.append(f"Reduced {bname} at {ch} ({amp:.1f} µV)")
if findings:
    lines.append("Key findings:")
    for f in findings[:10]:
        lines.append(f"  • {f}")
else:
    lines.append("No major deviations from expected norms detected.")
lines.append("")

# Technical analysis
lines.append("-" * 70)
lines.append("2. TECHNICAL EEG ANALYSIS")
lines.append("-" * 70)
lines.append("")
lines.append("Band Power Summary (amplitude in µV):")
lines.append(f"{'Channel':>8s}" + "".join(f" {b:>9s}" for b in BANDS))
for ch in ch_names:
    line = f"{ch:>8s}"
    for bname in BANDS:
        v = results[ch].get(bname, {}).get("amp_uV", 0)
        line += f" {v:9.2f}"
    lines.append(line)
lines.append("")

# Site-specific analysis
lines.append("-" * 70)
lines.append("3. SITE-SPECIFIC ANALYSIS")
lines.append("-" * 70)
for ch in ch_names:
    lines.append(f"\n  {ch}:")
    for bname, (fmin, fmax) in BANDS.items():
        amp = results[ch].get(bname, {}).get("amp_uV", 0)
        rel = results[ch].get(bname, {}).get("rel", 0)
        lo, hi = BAND_NORMS.get(bname, (0, 999))
        status = "NORMAL"
        if amp > hi * 1.5:
            status = "ELEVATED"
        elif amp < lo * 0.5:
            status = "REDUCED"
        func = BAND_FUNCTIONS.get(bname, "")
        lines.append(f"    {bname:>10s}: {amp:6.2f} µV ({rel:.0%} relative) [{status}]")
        if status != "NORMAL":
            lines.append(f"                {func}")
    tb = tb_ratios.get(ch, 0)
    lines.append(f"    {'T/B ratio':>10s}: {tb:.2f} {'(elevated)' if tb > 3 else ''}")

# Theta/Beta summary
lines.append("")
lines.append("-" * 70)
lines.append("4. CLINICAL RATIOS")
lines.append("-" * 70)
lines.append(f"  Global Theta/Beta: {global_tb:.2f}")
lines.append(f"  {'(Within normal range)' if global_tb < 3 else '(Elevated — associated with inattention)'}")

# Recommendations stub
lines.append("")
lines.append("-" * 70)
lines.append("5. RECOMMENDATIONS")
lines.append("-" * 70)
lines.append("  [To be completed by clinician based on clinical context]")
lines.append("")
lines.append("=" * 70)
lines.append("Generated by Paradox Solutions LLM — EEG Analysis Module")
lines.append("This report is intended for clinical review only.")
lines.append("=" * 70)

report = "\n".join(lines)
report_path = os.path.join(OUTPUT_DIR, f"{stem}_clinical_report.txt")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(report)

with open(os.path.join(OUTPUT_DIR, f"{stem}_report_data.json"), "w") as f:
    json.dump({"band_power": results, "tb_ratios": tb_ratios, "findings": findings}, f, indent=2)

print(report)
print(f"\nReport saved: {report_path}")
