"""Source Localization (sLORETA) — estimate cortical sources from scalp EEG.
Uses MNE sphere model (no FreeSurfer required). Generates source plots.
Requires at least 10 EEG channels with known 10-20 positions.
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
from mne.minimum_norm import make_inverse_operator, apply_inverse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
METHOD = "sLORETA"   # MNE, dSPM, sLORETA, eLORETA
SNR = 3.0
LAMBDA2 = 1.0 / SNR ** 2
EPOCH_DURATION = 2.0   # seconds per epoch
os.makedirs(OUTPUT_DIR, exist_ok=True)

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)

raw.filter(1.0, 40.0, verbose=False)
raw.notch_filter([60.0], verbose=False)

# Set montage
montage = mne.channels.make_standard_montage("standard_1020")
raw.set_montage(montage, on_missing="warn", verbose=False)

# Keep only channels with known positions
good_chs = [ch for ch in raw.ch_names if raw.info["chs"][raw.ch_names.index(ch)].get("loc") is not None
            and not all(raw.info["chs"][raw.ch_names.index(ch)]["loc"][:3] == 0)]
if len(good_chs) < 5:
    print(f"Only {len(good_chs)} channels with known positions. Need at least 5 for source localization.")
    exit()
raw.pick(good_chs)
raw.set_eeg_reference("average", projection=True, verbose=False)
print(f"Using {len(good_chs)} channels: {good_chs}")

stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")
sfreq = raw.info["sfreq"]

# Sphere model (no FreeSurfer needed)
print("Creating sphere forward model...")
sphere = mne.make_sphere_model(r0="auto", head_radius="auto", info=raw.info, verbose=False)

# Volume source space
src = mne.setup_volume_source_space(sphere=(0., 0., 0., 0.09), pos=10.0,
                                     exclude=0.0, verbose=False)
print(f"Source space: {src[0]['nuse']} sources")

# Forward solution
fwd = mne.make_forward_solution(raw.info, trans=None, src=src, bem=sphere,
                                 meg=False, eeg=True, mindist=5.0, verbose=False)
print(f"Forward solution: {fwd['nsource']} sources, {fwd['nchan']} channels")

# Create epochs for averaging
events = mne.make_fixed_length_events(raw, duration=EPOCH_DURATION)
epochs = mne.Epochs(raw, events, tmin=0, tmax=EPOCH_DURATION, baseline=None,
                     preload=True, verbose=False)
evoked = epochs.average()
print(f"Evoked from {len(epochs)} epochs of {EPOCH_DURATION}s each")

# Noise covariance (identity-based for resting state)
noise_cov = mne.make_ad_hoc_cov(raw.info, verbose=False)

# Inverse operator
inv = make_inverse_operator(raw.info, fwd, noise_cov, loose=1.0, depth=0.8, verbose=False)

# Apply inverse
stc = apply_inverse(evoked, inv, lambda2=LAMBDA2, method=METHOD, verbose=False)
print(f"\n{METHOD} source estimate:")
print(f"  Shape: {stc.data.shape}")
print(f"  Peak amplitude: {stc.data.max():.4f}")
print(f"  Mean amplitude: {stc.data.mean():.4f}")
peak_idx = np.argmax(np.abs(stc.data).max(axis=1))
print(f"  Peak source index: {peak_idx}")
peak_pos = src[0]["rr"][src[0]["vertno"][peak_idx]] * 1000
print(f"  Peak position (mm): x={peak_pos[0]:.1f}, y={peak_pos[1]:.1f}, z={peak_pos[2]:.1f}")

# Band-wise source power
BANDS = {"delta":(0.5,4),"theta":(4,8),"alpha":(8,13),"beta":(13,30)}
print(f"\nBand-wise source analysis:")
for bname, (fmin, fmax) in BANDS.items():
    raw_band = raw.copy().filter(fmin, fmax, verbose=False)
    events_b = mne.make_fixed_length_events(raw_band, duration=EPOCH_DURATION)
    epochs_b = mne.Epochs(raw_band, events_b, tmin=0, tmax=EPOCH_DURATION,
                           baseline=None, preload=True, verbose=False)
    evoked_b = epochs_b.average()
    stc_b = apply_inverse(evoked_b, inv, lambda2=LAMBDA2, method=METHOD, verbose=False)
    peak_b = np.argmax(np.abs(stc_b.data).max(axis=1))
    pos_b = src[0]["rr"][src[0]["vertno"][peak_b]] * 1000
    print(f"  {bname}: peak={stc_b.data.max():.4f} at ({pos_b[0]:.0f},{pos_b[1]:.0f},{pos_b[2]:.0f})mm")

# Source activation distribution plot
fig, axes = plt.subplots(2, 2, figsize=(12, 10))
for ax, (bname, (fmin, fmax)) in zip(axes.flat, BANDS.items()):
    raw_band = raw.copy().filter(fmin, fmax, verbose=False)
    events_b = mne.make_fixed_length_events(raw_band, duration=EPOCH_DURATION)
    epochs_b = mne.Epochs(raw_band, events_b, tmin=0, tmax=EPOCH_DURATION,
                           baseline=None, preload=True, verbose=False)
    evoked_b = epochs_b.average()
    stc_b = apply_inverse(evoked_b, inv, lambda2=LAMBDA2, method=METHOD, verbose=False)
    source_power = np.abs(stc_b.data).mean(axis=1)
    ax.hist(source_power, bins=50, alpha=0.7, color="steelblue")
    ax.set_title(f"{bname} ({fmin}-{fmax} Hz)")
    ax.set_xlabel(f"{METHOD} amplitude")
    ax.set_ylabel("Source count")
plt.suptitle(f"Source Activation Distribution — {stem}", fontsize=14)
plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_source_distribution.png"), dpi=150)
plt.close()
print(f"\nSource distribution plot: {OUTPUT_DIR}/{stem}_source_distribution.png")
