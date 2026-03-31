"""ICA Artifact Removal — automatic ICA with optional ICLabel classification.
Detects and removes eye/muscle/heart artifacts, saves cleaned data.
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
import os, warnings
warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
OUTPUT_DIR = "output"
ICA_METHOD = "fastica"      # fastica, infomax, picard
ICA_N_COMPONENTS = None     # None = auto (based on data rank)
ICALABEL_THRESHOLD = 0.7    # confidence threshold for auto-rejection
os.makedirs(OUTPUT_DIR, exist_ok=True)

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loaders = {".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf, ".fif": mne.io.read_raw_fif}
raw = loaders.get(ext, mne.io.read_raw_edf)(INPUT_FILE, preload=True, verbose=False)

raw.filter(1.0, 45.0, verbose=False)
raw.notch_filter([60.0], verbose=False)

sfreq = raw.info["sfreq"]
data = raw.get_data()
stem = os.path.splitext(os.path.basename(INPUT_FILE))[0].replace(" ", "_")

# Determine ICA component count from data rank
n_components = ICA_N_COMPONENTS
if n_components is None:
    rank = np.linalg.matrix_rank(data)
    n_components = min(rank - 1, raw.info["nchan"] - 1, 20)
    print(f"Data rank: {rank}, using {n_components} ICA components")

# Run ICA
ica = mne.preprocessing.ICA(n_components=n_components, method=ICA_METHOD,
                             max_iter="auto", random_state=42)
ica.fit(raw, verbose=False)
print(f"ICA fitted: {ica.n_components_} components")

# Classify components
excluded = []
labels_info = {}

try:
    from mne_icalabel import label_components
    ic_labels = label_components(raw, ica, method="iclabel")
    labels = ic_labels["labels"]
    probs = ic_labels["y_pred_proba"]
    print(f"\nICLabel classification:")
    for i, (label, prob) in enumerate(zip(labels, probs)):
        confidence = max(prob) if hasattr(prob, "__len__") else prob
        status = ""
        if label != "brain" and confidence >= ICALABEL_THRESHOLD:
            excluded.append(i)
            status = " *** EXCLUDE ***"
        print(f"  IC{i:02d}: {label} (conf={confidence:.2f}){status}")
        labels_info[f"IC{i:02d}"] = {"label": label, "confidence": float(confidence)}
except ImportError:
    print("mne_icalabel not available, using EOG correlation method")
    eog_chs = [ch for ch in raw.ch_names if any(k in ch.upper() for k in ["EOG","VEOG","HEOG"])]
    if eog_chs:
        eog_idx, eog_scores = ica.find_bads_eog(raw, ch_name=eog_chs[0], verbose=False)
        excluded.extend(eog_idx)
        print(f"  EOG-correlated components: {eog_idx}")
    else:
        # Heuristic: exclude components with highest kurtosis (likely artifacts)
        sources = ica.get_sources(raw).get_data()
        kurtosis = np.array([float(np.mean((s - s.mean())**4) / (s.std()**4 + 1e-10) - 3) for s in sources])
        artifact_idx = np.where(kurtosis > 5)[0].tolist()
        excluded.extend(artifact_idx[:3])
        print(f"  High-kurtosis components (>5): {artifact_idx}")

ica.exclude = excluded
print(f"\nExcluding {len(excluded)} components: {excluded}")

# Save ICA component plots
try:
    fig = ica.plot_components(show=False)
    if isinstance(fig, list):
        for fi, f in enumerate(fig):
            f.savefig(os.path.join(OUTPUT_DIR, f"{stem}_ica_components_{fi}.png"), dpi=150)
            plt.close(f)
    else:
        fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_ica_components.png"), dpi=150)
        plt.close(fig)
except Exception as e:
    print(f"Component plot skipped: {e}")

# Apply ICA
raw_clean = ica.apply(raw.copy(), verbose=False)

# Before/after comparison
fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
t = np.arange(min(int(sfreq * 10), data.shape[1])) / sfreq
ch0 = 0
axes[0].plot(t, raw.get_data()[ch0, :len(t)] * 1e6, linewidth=0.5)
axes[0].set_ylabel("µV")
axes[0].set_title(f"Before ICA — {raw.ch_names[ch0]}")
axes[0].set_ylim(-100, 100)
axes[1].plot(t, raw_clean.get_data()[ch0, :len(t)] * 1e6, linewidth=0.5, color="green")
axes[1].set_ylabel("µV")
axes[1].set_xlabel("Time (s)")
axes[1].set_title(f"After ICA — {raw.ch_names[ch0]}")
axes[1].set_ylim(-100, 100)
plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, f"{stem}_ica_before_after.png"), dpi=150)
plt.close()

# Save cleaned data
out_fif = os.path.join(OUTPUT_DIR, f"{stem}_cleaned.fif")
raw_clean.save(out_fif, overwrite=True, verbose=False)
print(f"\nCleaned data saved: {out_fif}")

# Save ICA object
ica_fif = os.path.join(OUTPUT_DIR, f"{stem}_ica.fif")
ica.save(ica_fif, overwrite=True)
print(f"ICA solution saved: {ica_fif}")
print(f"Before/after plot: {OUTPUT_DIR}/{stem}_ica_before_after.png")
