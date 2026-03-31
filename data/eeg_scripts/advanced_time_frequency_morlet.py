"""Tier: advanced — Morlet wavelet TFR on fixed-length epochs (mne.tools time-frequency tutorials).
Adapt INPUT_FILE, freq range, and n_cycles scaling. Saves average power plot for central EEG channels.
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
from mne.time_frequency import tfr_morlet
import numpy as np
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings("ignore")

INPUT_FILE = "recording.edf"
EPOCH_LEN_S = 2.0
FREQS = np.linspace(6.0, 35.0, 15)
N_CYCLES = FREQS / 3.0
LOW_HZ = 1.0
HIGH_HZ = 45.0

LOADERS = {
    ".edf": mne.io.read_raw_edf,
    ".bdf": mne.io.read_raw_bdf,
    ".fif": mne.io.read_raw_fif,
    ".vhdr": mne.io.read_raw_brainvision,
}

ext = "." + INPUT_FILE.rsplit(".", 1)[-1].lower()
loader = LOADERS.get(ext)
if not loader:
    raise ValueError(f"Unsupported format: {ext}")

raw = loader(INPUT_FILE, preload=True, verbose=False)
raw.pick(picks="eeg", exclude="bads")
try:
    raw.set_montage("standard_1020", match_case=False, on_missing="ignore")
except Exception:
    pass
raw.filter(LOW_HZ, HIGH_HZ, fir_design="firwin", verbose=False)

events = mne.make_fixed_length_events(raw, id=1, duration=EPOCH_LEN_S, overlap=0.0)
epochs = mne.Epochs(
    raw,
    events,
    event_id=1,
    tmin=0.0,
    tmax=EPOCH_LEN_S - 1.0 / raw.info["sfreq"],
    baseline=None,
    preload=True,
    verbose=False,
)

power = tfr_morlet(
    epochs,
    freqs=FREQS,
    n_cycles=N_CYCLES,
    average=True,
    return_itc=False,
    verbose=False,
)

# Plot one midline or centro-parietal channel if present
pick_names = ["Cz", "Pz", "C3", "Fz"]
ch_name = None
for p in pick_names:
    if p in power.ch_names:
        ch_name = p
        break
if ch_name is None:
    ch_name = power.ch_names[len(power.ch_names) // 2]

idx = power.ch_names.index(ch_name)
data = power.data[idx, :, :]  # (n_freqs, n_times)
fig, ax = plt.subplots(figsize=(8, 4))
im = ax.imshow(
    10 * np.log10(data + 1e-20),
    aspect="auto",
    origin="lower",
    extent=[epochs.times[0], epochs.times[-1], FREQS[0], FREQS[-1]],
    cmap="viridis",
)
ax.set_xlabel("Time (s)")
ax.set_ylabel("Frequency (Hz)")
ax.set_title(f"Log power TFR — {ch_name}")
fig.colorbar(im, ax=ax, label="dB")
plt.tight_layout()
out = INPUT_FILE.rsplit(".", 1)[0] + f"_tfr_{ch_name}.png"
plt.savefig(out, dpi=150)
print(f"Saved {out}")
