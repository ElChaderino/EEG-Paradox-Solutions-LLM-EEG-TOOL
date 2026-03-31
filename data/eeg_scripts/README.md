# EEG / MNE script templates (`data/eeg_scripts`)

Bundled Python starters for **`run_python_analysis`**, the **Script / code** tab in the web UI, and the agent tool `list_eeg_scripts`. Working directory at run time is **`data/eeg_workspace/`**; most scripts write PNG (and sometimes FIF/JSON) under **`output/`** relative to that cwd (or `OUTPUT_DIR` if overridden).

**Docs:** [MNE-Python](https://mne.tools/stable/index.html)

## Interactive HTML (Plotly, optional)

These **`viz_*` scripts** also write a **`.html`** sibling next to the PNG when **`plotly`** is installed (included in the project **`[eeg]`** extra / EEG worker bundle):

| Script | HTML artifact |
|--------|----------------|
| `viz_psd_butterfly_channels.py` | `{stem}_psd_butterfly.html` — log-y multi-line PSD |
| `viz_channel_correlation_heatmap.py` | `{stem}_channel_corr.html` — correlation heatmap |
| `viz_windowed_rms_heatmap.py` | `{stem}_rms_heatmap.html` — RMS vs time × channel |
| `viz_tfr_fc_grid.py` | `{stem}_tfr_fc_grid.html` — Morlet TFR panels |

Exports use **`include_plotlyjs=True`** (Plotly.js is embedded in each file so HTML opens fully offline; files are larger than with a CDN link).

If Plotly is missing, scripts still save PNG and print `skipped HTML export`.

## Scripts by tier

### Basic

| File | Purpose |
|------|---------|
| `inspect_edf.py` | Header: channels, sfreq, duration, annotations, RMS |
| `basic_raw_psd_topomap.py` | Filter → Welch PSD → band RMS topomaps |
| `band_power_analysis.py` | Bands, relative power, topomaps, PSD |
| `quality_check.py` | Flatline, line noise, EMG, bridging, kurtosis |
| `channel_standardize.py` | Vendor channel names → 10-20 |
| `viz_sensors_2d_topology.py` | `plot_sensors` layout check |
| `viz_psd_butterfly_channels.py` | Per-channel PSD lines (+ optional Plotly HTML) |
| `viz_line_noise_before_after.py` | Notch PSD comparison |
| `viz_mne_psd_topo_grid.py` | Log-PSD topomaps at target Hz |

### Intermediate

| File | Purpose |
|------|---------|
| `intermediate_epochs_evoked.py` | Fixed-length epochs → evoked joint plot |
| `eo_ec_comparison.py` | EO vs EC band power |
| `alpha_asymmetry.py` | FAA / asymmetry |
| `ica_artifact_removal.py` | ICA + optional ICLabel → cleaned FIF |
| `prep_bad_channel_interpolate.py` | Flat bads → interpolate |
| `viz_epochs_image.py` | `epochs.plot_image` |
| `viz_evoked_topomap_grid.py` | Evoked topomap grid |
| `viz_evoked_butterfly_spatial.py` | Spatial-color butterfly |
| `viz_peak_frequency_topomap.py` | Peak freq in band → topomap |
| `viz_channel_correlation_heatmap.py` | Channel correlation (+ optional Plotly HTML) |

### Advanced

| File | Purpose |
|------|---------|
| `connectivity_analysis.py` | Coherence / PLV matrices |
| `phase_amplitude_coupling.py` | PAC / comodulogram |
| `spectral_features.py` | SEF, entropy, 1/f |
| `advanced_time_frequency_morlet.py` | Morlet TFR |
| `viz_tfr_fc_grid.py` | Fz/Cz/Pz TFR grid (+ optional Plotly HTML) |
| `viz_envelope_band_topomap.py` | Hilbert envelope topomap |
| `viz_windowed_rms_heatmap.py` | RMS heatmap (+ optional Plotly HTML) |
| `viz_ica_properties_batch.py` | ICA `plot_properties` PNGs |
| `viz_compare_two_halves_psd.py` | First vs second half PSD |
| `viz_stft_spectrogram_channel.py` | SciPy STFT spectrogram |
| `source_localization.py` | Sphere sLORETA |
| `clinical_report.py` | Narrative report |

### Expert

| File | Purpose |
|------|---------|
| `clinical_q_assessment.py` | Swingle-style Clinical Q |
| `vigilance_analysis.py` | Vigilance / state |
| `artifact_validation.py` | Multi-layer artifact validation |
| `csd_analysis.py` | Current source density |
| `expert_wpli_connectivity.py` | wPLI matrix (`mne_connectivity`) |
| `viz_connectivity_circle_wpli.py` | Circular connectivity graph |
| `viz_gfp_evoked_peaks.py` | GFP + peak topomaps |

## Usage

1. Set **`INPUT_FILE`** to a file under `eeg_workspace/` (or a path you have rights to).
2. Run via API **`POST /eeg/run-python`**, agent **`run_python_analysis`**, or the **Script / code** tab.
3. **`mne_connectivity`** / **`mne-icalabel`**: install project extras as needed (`pip install -e ".[eeg]"`).
