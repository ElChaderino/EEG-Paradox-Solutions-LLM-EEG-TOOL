# EEG Software Compatibility Guide

## MNE-Python (primary analysis platform)

- **Type**: Open-source Python library for EEG/MEG analysis
- **Strengths**: Full pipeline from raw to source-level; excellent documentation; active community; integrates with scikit-learn for ML
- **Native format**: FIF (.fif)
- **Reads**: EDF, BDF, BrainVision (.vhdr), EGI (.mff), CNT, EEGLAB (.set), XDF, GDF, Nicolet, Persyst, Nihon Kohden, and dozens more
- **Key modules**: `mne.io` (I/O), `mne.preprocessing` (ICA, SSP), `mne.time_frequency` (TFR, PSD), `mne.minimum_norm` (source), `mne.viz` (plotting), `mne.decoding` (ML)
- **Installation**: `pip install mne` (base) or `pip install "mne[full]"` (with 3D viz)
- **Docs**: https://mne.tools/stable/

## EEGLAB (MATLAB)

- **Type**: MATLAB toolbox (open-source)
- **Strengths**: GUI-friendly preprocessing, huge plugin ecosystem (SIFT, BCILAB, LIMO, ICLabel)
- **Native formats**: .set (metadata) + .fdt (float data), or .set with embedded data
- **Export to MNE**: `mne.io.read_raw_eeglab('file.set')` or `mne.io.read_epochs_eeglab('file.set')`
- **Common workflow**: Import -> channel locations -> filter -> ICA (runica/infomax) -> ICLabel -> epoch -> STUDY
- **Docs**: https://sccn.ucsd.edu/eeglab/

## NeuroGuide

- **Type**: Commercial QEEG analysis software (Applied Neuroscience, Inc.)
- **Developer**: Robert W. Thatcher, Ph.D.
- **Strengths**: Largest lifespan normative database (FDA-cleared); surface and LORETA analysis; discriminant functions for TBI, LD, ADHD, depression; real-time z-score NFB interface
- **Native format**: Proprietary .ng files
- **Export**: EDF, ASCII text reports, LORETA files
- **Import to MNE**: Export as EDF from NeuroGuide, then `mne.io.read_raw_edf('file.edf')`
- **Key features**: z-score topomaps, coherence/phase maps, JTFA (Joint Time-Frequency Analysis), Brodmann area analysis via sLORETA/eLORETA
- **Normative DB**: 625+ subjects, 2 months -- 82 years, eyes-open and eyes-closed

## Cygnet (Planet Cygnet)

- **Type**: Neurofeedback delivery platform
- **Strengths**: Real-time z-score neurofeedback using NeuroGuide norms; surface and LORETA z-score training; swingle-style assessments
- **Native format**: Recordings stored as EDF
- **Export**: EDF
- **Import to MNE**: `mne.io.read_raw_edf('cygnet_recording.edf')`
- **Protocols**: Single-channel, 2-channel, 4-channel, and 19-channel z-score training; supports BrainMaster, Mitsar, Deymed hardware
- **Integration**: Direct link with NeuroGuide normative database for live z-score computation

## BrainMaster Technologies

- **Type**: EEG hardware manufacturer + software suite
- **Products**: Discovery 24E (24-channel), Atlantis II (4-channel), Freedom (wireless)
- **Software**: BrainMaster 3.0 (acquisition + NFB), Mini-Q (QEEG), BrainAvatar (3D real-time LORETA)
- **Native format**: .bm (proprietary), EDF export
- **Export**: EDF, BDF, ASCII/CSV
- **Import to MNE**: Export as EDF -> `mne.io.read_raw_edf('file.edf')`
- **Strengths**: Integrated hardware+software, live LORETA via BrainAvatar, z-score NFB, event-related potentials
- **Special**: BrainAvatar supports real-time 3D source imaging during NFB sessions

## BioExplorer

- **Type**: Biofeedback/neurofeedback software (CyberEvolution)
- **Strengths**: Highly flexible visual design environment; signal processing flowcharts; supports many hardware devices; multimedia feedback (video, audio, games)
- **Native format**: Session files (.bxs), design files (.bxd)
- **Export**: EDF, CSV, raw binary
- **Import to MNE**: Export as EDF -> `mne.io.read_raw_edf()`, or CSV -> `pandas.read_csv()` then create MNE Raw from array
- **Hardware support**: BrainMaster, Thought Technology, Pocket Neurobics, NeXus, OpenBCI, J&J Engineering
- **Key feature**: Visual signal-processing chain designer (drag-and-drop DSP blocks)

## BioEra

- **Type**: Visual biofeedback design tool
- **Strengths**: Low-level signal processing design; supports custom protocol creation; scripting via VBScript; budget-friendly
- **Native format**: Proprietary design files (.ber)
- **Export**: EDF, raw data files
- **Import to MNE**: Export as EDF -> `mne.io.read_raw_edf()`
- **Hardware**: Supports serial/USB devices, BrainMaster, Pocket Neurobics, custom amplifiers
- **Use case**: Custom biofeedback protocol development, multi-modal feedback (EEG + EMG + HRV)

## OpenBCI

- **Type**: Open-source EEG hardware platform
- **Products**: Cyton (8-channel, ADS1299), Ganglion (4-channel), Daisy (16-channel expansion), Galea (research-grade)
- **Software**: OpenBCI GUI (processing + recording), BrainFlow (cross-platform streaming SDK)
- **Native format**: CSV (OpenBCI GUI), BDF (optional)
- **Export**: CSV with timestamps, BDF via BrainFlow
- **Import to MNE**: CSV -> pandas -> `mne.io.RawArray()`, or BDF -> `mne.io.read_raw_bdf()`
- **BrainFlow integration**: `pip install brainflow`; Python API streams directly to NumPy arrays for real-time processing
- **Strengths**: Affordable, hackable, well-documented, large community; great for research prototyping and home neurofeedback
- **Sample rates**: 250 Hz (Cyton default), configurable up to 16 kHz

## Other Notable Platforms

### Mitsar (WinEEG / qEEG-Pro)
- 19/24/32 channel EEG amplifiers
- WinEEG software for acquisition; qEEG-Pro for normative comparison
- Exports: EDF, WinEEG native
- Import to MNE: EDF export

### Deymed (TruScan)
- Clinical EEG systems, 32+ channels
- TruScan software for QEEG
- Exports: EDF
- Commonly used with Cygnet for z-score NFB

### Thought Technology (BioGraph Infiniti)
- ProComp series (2-10 channel)
- BioGraph Infiniti software (multi-modal biofeedback)
- Exports: CSV, text
- Import: pandas -> MNE RawArray

### NeurOptimal
- Nonlinear dynamical neurofeedback (Zengar Institute)
- Proprietary system, limited export
- Not directly compatible with standard QEEG analysis

### Brain Products (actiCHamp, BrainVision Recorder)
- Research-grade EEG amplifiers (up to 256 channels)
- BrainVision format: .vhdr (header) + .vmrk (markers) + .eeg (data)
- Direct MNE support: `mne.io.read_raw_brainvision('file.vhdr')`

### ANT Neuro (eego, ASA)
- Research/clinical EEG systems
- Exports: EDF, CNT
- MNE: `mne.io.read_raw_cnt()` or EDF import

## Quick Reference: Getting Data into MNE

```python
import mne

# EDF (NeuroGuide, BrainMaster, BioExplorer, Cygnet, BioEra, clinical)
raw = mne.io.read_raw_edf("recording.edf", preload=True)

# BDF (BrainMaster, OpenBCI via BrainFlow)
raw = mne.io.read_raw_bdf("recording.bdf", preload=True)

# BrainVision (Brain Products)
raw = mne.io.read_raw_brainvision("recording.vhdr", preload=True)

# EEGLAB .set
raw = mne.io.read_raw_eeglab("recording.set", preload=True)

# FIF (MNE native / Elekta / MEGIN)
raw = mne.io.read_raw_fif("recording.fif", preload=True)

# OpenBCI CSV (manual construction)
import numpy as np
import pandas as pd
df = pd.read_csv("recording.csv", comment="%")
data = df[channel_columns].values.T * 1e-6  # uV to V
info = mne.create_info(ch_names=channel_names, sfreq=250, ch_types="eeg")
raw = mne.io.RawArray(data, info)
raw.set_montage(mne.channels.make_standard_montage("standard_1020"))

# Inspect any recording
print(raw.info)  # channels, sfreq, duration
raw.plot(duration=10, n_channels=20)  # visual inspection
raw.compute_psd().plot()  # power spectral density
```
