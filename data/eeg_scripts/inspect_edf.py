"""EDF/BDF Header Inspection — quick overview of a recording file.
Prints channel names, sampling rates, duration, annotations, and basic stats.
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
import warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"

LOADERS = {
    ".edf": mne.io.read_raw_edf,
    ".bdf": mne.io.read_raw_bdf,
    ".fif": mne.io.read_raw_fif,
    ".set": mne.io.read_raw_eeglab,
    ".vhdr": mne.io.read_raw_brainvision,
    ".cnt": mne.io.read_raw_cnt,
    ".gdf": mne.io.read_raw_gdf,
}

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loader = LOADERS.get(ext)
if not loader:
    raise ValueError(f"Unsupported format: {ext}")

raw = loader(INPUT_FILE, preload=False, verbose=False)
info = raw.info

print(f"File: {INPUT_FILE}")
print(f"Format: {ext.upper().strip('.')}")
print(f"Duration: {raw.times[-1]:.1f} s ({raw.times[-1]/60:.1f} min)")
print(f"Sampling rate: {info['sfreq']} Hz")
print(f"Channels: {info['nchan']}")
print(f"Channel names: {info['ch_names']}")
print()

ch_types = {}
for ch in info["chs"]:
    t = mne.channel_type(info, info["ch_names"].index(ch["ch_name"]))
    ch_types.setdefault(t, []).append(ch["ch_name"])
for t, names in ch_types.items():
    print(f"  {t}: {len(names)} — {', '.join(names[:10])}{'...' if len(names) > 10 else ''}")

anns = raw.annotations
if len(anns) > 0:
    print(f"\nAnnotations: {len(anns)}")
    for a in anns[:20]:
        print(f"  {a['onset']:.2f}s  dur={a['duration']:.2f}s  desc='{a['description']}'")
    if len(anns) > 20:
        print(f"  ... and {len(anns) - 20} more")
else:
    print("\nAnnotations: none")

raw.load_data(verbose=False)
data = raw.get_data()
print(f"\nBasic stats (all channels):")
print(f"  Mean amplitude: {np.mean(np.abs(data)) * 1e6:.2f} µV")
print(f"  Max amplitude:  {np.max(np.abs(data)) * 1e6:.2f} µV")
print(f"  Flatline channels: {sum(np.std(data[i]) < 1e-10 for i in range(data.shape[0]))}")

print("\nPer-channel RMS (µV):")
for i, ch in enumerate(info["ch_names"]):
    rms = np.sqrt(np.mean(data[i] ** 2)) * 1e6
    print(f"  {ch:>8s}: {rms:8.2f} µV")
