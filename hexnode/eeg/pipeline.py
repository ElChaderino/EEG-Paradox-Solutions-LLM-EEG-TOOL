"""Full EEG preprocessing + analysis pipeline using MNE-Python.

Generates a self-contained Python script that mirrors a 24-step EEGLAB-style
pipeline but uses MNE-Python, autoreject, mne-icalabel, and mne-connectivity.
The script is designed to run as a standalone subprocess in the eeg_workspace
directory via ``run_eeg_pipeline`` or ``run_python_analysis``.

Every step is wrapped in try/except so the pipeline continues and reports
partial results even when individual stages fail.
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


from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PipelineConfig:
    input_file: str
    output_prefix: str = ""
    # Recording condition / scan type
    condition: str = "EC"           # EC, EO, task, resting
    output_mode: str = "standard"   # standard, clinical, exploratory
    remontage_ref: str = ""         # average, linked_ears, cz, or empty=keep original
    # Filtering
    hp_freq: float = 0.5
    lp_freq: float = 40.0
    notch_freq: float = 60.0
    # ICA
    ica_method: str = "fastica"
    ica_n_components: float | int | None = None
    icalabel_threshold: float = 0.80
    # Epochs (set to empty string to skip event-based analysis)
    epoch_tmin: float = -0.2
    epoch_tmax: float = 0.8
    baseline: tuple[float | None, float] = (None, 0.0)
    epoch_reject_uv: float = 150.0
    # Spectral
    bands: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        "delta": (0.5, 4.0),
        "theta": (4.0, 8.0),
        "alpha": (8.0, 13.0),
        "beta": (13.0, 30.0),
        "gamma": (30.0, 40.0),
    })
    # Connectivity
    connectivity_method: str = "coh"
    connectivity_fmin: float = 4.0
    connectivity_fmax: float = 30.0
    # Pairwise mean/sd CSV for coherence z-scores. Empty + connectivity_bundled_norms
    # uses shipped tables under hexnode/eeg/norms/data/ (no DLC addon required).
    connectivity_norm_csv: str = ""
    connectivity_bundled_norms: bool = True
    # Output
    save_cleaned: bool = True
    save_figures: bool = True
    output_dir: str = "output"
    generate_report: bool = True


_NORMS_DATA = Path(__file__).resolve().parent / "norms" / "data"


def bundled_connectivity_norm_csv(condition: str = "EC") -> Path | None:
    """
    Shipped Cuban 2nd wave coherence norm CSV (10-channel pairs, coh 4–30 Hz rows).
    Lives next to this module; does not require addons/eeg-norms-dlc at runtime.
    """
    c = (condition or "EC").strip().upper()
    if c in ("EO", "EYES_OPEN"):
        name = "connectivity_norm_cuban2ndwave_eyes_open.csv"
    else:
        name = "connectivity_norm_cuban2ndwave_eyes_closed.csv"
    p = _NORMS_DATA / name
    return p if p.is_file() else None


def effective_connectivity_norm_csv(cfg: PipelineConfig) -> str:
    """Explicit connectivity_norm_csv if set; else bundled table when enabled and present."""
    explicit = (cfg.connectivity_norm_csv or "").strip()
    if explicit:
        return explicit
    if not cfg.connectivity_bundled_norms:
        return ""
    bp = bundled_connectivity_norm_csv(cfg.condition)
    return str(bp.resolve()) if bp is not None else ""


def generate_pipeline_script(cfg: PipelineConfig) -> str:
    """Return a complete, self-contained Python script string."""

    _eff_norm_csv = effective_connectivity_norm_csv(cfg)
    raw_prefix = cfg.output_prefix or cfg.input_file.rsplit(".", 1)[0]
    prefix = Path(raw_prefix).name

    bands_repr = repr(cfg.bands)
    baseline_repr = repr(cfg.baseline)

    script = textwrap.dedent(f'''\
    #!/usr/bin/env python
    """Paradox EEG Pipeline — auto-generated full preprocessing + analysis script."""

    import os, sys, json, traceback
    from pathlib import Path
    from datetime import datetime

    import warnings; warnings.filterwarnings("ignore")
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    OUTDIR = Path(r"{cfg.output_dir}")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    PREFIX = "{prefix}"
    INPUT_FILE = r"{cfg.input_file}"

    CONDITION = "{cfg.condition}"
    REMONTAGE_REF = "{cfg.remontage_ref}"

    report_lines = []
    quality = {{"condition": CONDITION}}
    step_status = {{}}

    def log(msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{{ts}}] {{msg}}"
        print(line, flush=True)
        report_lines.append(line)

    def step(name):
        def decorator(fn):
            def wrapper(*a, **kw):
                log(f"=== STEP: {{name}} ===")
                try:
                    result = fn(*a, **kw)
                    step_status[name] = "OK"
                    return result
                except Exception as e:
                    step_status[name] = f"FAILED: {{e}}"
                    log(f"  ERROR in {{name}}: {{e}}")
                    traceback.print_exc()
                    return None
            return wrapper
        return decorator

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1: LOAD DATA
    # ═══════════════════════════════════════════════════════════════════════
    @step("1_load_data")
    def load_data():
        import mne
        ext = Path(INPUT_FILE).suffix.lower()
        loaders = {{
            ".edf": mne.io.read_raw_edf,
            ".bdf": mne.io.read_raw_bdf,
            ".fif": mne.io.read_raw_fif,
            ".set": mne.io.read_raw_eeglab,
            ".vhdr": mne.io.read_raw_brainvision,
            ".cnt": mne.io.read_raw_cnt,
            ".gdf": mne.io.read_raw_gdf,
        }}
        loader = loaders.get(ext)
        if loader is None:
            raise ValueError(f"Unsupported format: {{ext}}")
        raw = loader(INPUT_FILE, preload=True, verbose=False)
        log(f"  Loaded: {{raw.info['nchan']}} channels, {{raw.info['sfreq']}} Hz, "
            f"{{raw.n_times / raw.info['sfreq']:.1f}} sec")
        log(f"  Channels: {{', '.join(raw.info['ch_names'][:20])}}"
            + (f" ... +{{raw.info['nchan']-20}} more" if raw.info['nchan'] > 20 else ""))

        # Standardize channel names (strip EEG prefix, reference suffixes, fix casing)
        import re as _re
        _OLD_NEW = {{"T3":"T7","T4":"T8","T5":"P7","T6":"P8"}}
        def _clean_ch(name):
            name = _re.sub(r"^EEG[\\s\\-]+", "", name.strip(), flags=_re.IGNORECASE)
            for sfx in ["-REF","-LE","-RE","-M1","-M2","-A1","-A2","-Av","-AV"]:
                name = _re.sub(_re.escape(sfx), "", name, flags=_re.IGNORECASE)
            name = name.strip()
            u = name.upper()
            if u == "FPZ": return "Fpz"
            if u.startswith("FP"): return "Fp" + u[2:]
            if len(u) == 2 and u[1] == "Z": return u[0] + "z"
            if len(u) >= 2:
                r = u[0] + u[1:].lower()
                return _OLD_NEW.get(r, r)
            return name
        ch_map = {{}}
        for ch in raw.ch_names:
            cleaned = _clean_ch(ch)
            if cleaned != ch:
                ch_map[ch] = cleaned
        if ch_map:
            raw.rename_channels(ch_map)
            log(f"  Standardized {{len(ch_map)}} channel names")

        # Attempt standard montage
        try:
            montage = mne.channels.make_standard_montage("standard_1020")
            raw.set_montage(montage, on_missing="warn", verbose=False)
            log("  Montage: standard_1020 applied")
        except Exception:
            log("  Montage: could not set standard_1020 (non-standard channel names)")

        quality["n_channels_original"] = raw.info["nchan"]
        quality["sfreq"] = raw.info["sfreq"]
        quality["duration_sec"] = raw.n_times / raw.info["sfreq"]
        log(f"  Condition: {{CONDITION}}")
        return raw

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1b: USER RE-REFERENCE (optional, before pipeline)
    # ═══════════════════════════════════════════════════════════════════════
    @step("1b_user_rereference")
    def user_rereference(raw):
        if not REMONTAGE_REF:
            log("  Re-reference: skipped (keeping original)")
            return raw
        import mne as _mne
        ref_map = {{
            "average": "average",
            "linked_ears": ["A1", "A2", "M1", "M2", "TP9", "TP10"],
            "cz": ["Cz"],
        }}
        ref = ref_map.get(REMONTAGE_REF, REMONTAGE_REF)
        if ref == "average":
            raw.set_eeg_reference("average", verbose=False)
            log("  Re-reference: average")
        elif isinstance(ref, list):
            avail = [r for r in ref if r in raw.ch_names]
            if avail:
                raw.set_eeg_reference(avail, verbose=False)
                log(f"  Re-reference: {{avail}}")
            else:
                log(f"  Re-reference: none of {{ref}} found, skipped")
        else:
            log(f"  Re-reference: unknown '{{REMONTAGE_REF}}', skipped")
        quality["remontage"] = REMONTAGE_REF
        return raw

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 2: QUALITY DIAGNOSTICS
    # ═══════════════════════════════════════════════════════════════════════
    @step("2_quality_diagnostics")
    def quality_diagnostics(raw):
        from scipy.stats import kurtosis as sp_kurt
        data = raw.get_data()
        ch_var = np.var(data, axis=1)
        ch_kurt = sp_kurt(data, axis=1)
        ch_range = np.max(data, axis=1) - np.min(data, axis=1)
        flatline = ch_var < 1e-12
        n_flat = int(flatline.sum())
        log(f"  Channel variance range: {{ch_var.min():.2e}} — {{ch_var.max():.2e}}")
        log(f"  Mean kurtosis: {{ch_kurt.mean():.2f}}")
        log(f"  Flatline channels: {{n_flat}}")
        quality["flatline_channels"] = n_flat
        quality["mean_kurtosis"] = float(ch_kurt.mean())
        if n_flat > 0:
            flat_names = [raw.ch_names[i] for i in np.where(flatline)[0]]
            raw.info["bads"].extend(flat_names)
            log(f"  Marked as bad: {{flat_names}}")
        return raw

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 3: BASELINE VISUALIZATION
    # ═══════════════════════════════════════════════════════════════════════
    @step("3_baseline_viz")
    def baseline_viz(raw):
        fig = raw.compute_psd(fmax=50, verbose=False).plot(show=False)
        fig.savefig(OUTDIR / f"{{PREFIX}}_01_psd_raw.png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        log("  Saved raw PSD plot")
        return raw

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 4: FILTERING
    # ═══════════════════════════════════════════════════════════════════════
    @step("4_filtering")
    def apply_filters(raw):
        raw.filter({cfg.hp_freq}, {cfg.lp_freq}, verbose=False)
        log(f"  Bandpass: {cfg.hp_freq} — {cfg.lp_freq} Hz")
        return raw

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 5: LINE NOISE SUPPRESSION
    # ═══════════════════════════════════════════════════════════════════════
    @step("5_notch_filter")
    def notch_filter(raw):
        freqs = [{cfg.notch_freq}]
        if {cfg.notch_freq} * 2 <= {cfg.lp_freq}:
            freqs.append({cfg.notch_freq} * 2)
        raw.notch_filter(freqs, verbose=False)
        log(f"  Notch: {{freqs}} Hz")
        return raw

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 6: AUTOMATED BAD CHANNEL DETECTION
    # ═══════════════════════════════════════════════════════════════════════
    @step("6_bad_channel_detection")
    def detect_bad_channels(raw):
        import mne as _mne
        eeg_picks = _mne.pick_types(raw.info, eeg=True, exclude=[])
        eeg_names = [raw.ch_names[i] for i in eeg_picks]
        data = raw.get_data(picks=eeg_picks)
        ch_var = np.var(data, axis=1)
        median_var = np.median(ch_var)
        bad_idx = np.where((ch_var > 10 * median_var) | (ch_var < 0.01 * median_var))[0]
        new_bads = [eeg_names[i] for i in bad_idx if eeg_names[i] not in raw.info["bads"]]
        raw.info["bads"].extend(new_bads)
        quality["bad_channels"] = list(raw.info["bads"])
        log(f"  Bad channels detected: {{raw.info['bads']}}")
        return raw

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 7: CHANNEL INTERPOLATION
    # ═══════════════════════════════════════════════════════════════════════
    @step("7_interpolate")
    def interpolate_bads(raw):
        if raw.info["bads"]:
            try:
                raw.interpolate_bads(reset_bads=True, verbose=False)
                log(f"  Interpolated {{len(quality.get('bad_channels', []))}} bad channels")
            except Exception as e:
                log(f"  Interpolation skipped (no montage?): {{e}}")
                raw.info["bads"] = []
        else:
            log("  No bad channels to interpolate")
        return raw

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 8: RE-REFERENCING
    # ═══════════════════════════════════════════════════════════════════════
    @step("8_rereference")
    def rereference(raw):
        raw.set_eeg_reference("average", projection=False, verbose=False)
        log("  Re-referenced to average")
        return raw

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 9: DATA RANK
    # ═══════════════════════════════════════════════════════════════════════
    @step("9_data_rank")
    def compute_rank(raw):
        rank = np.linalg.matrix_rank(raw.get_data())
        quality["data_rank"] = int(rank)
        quality["n_channels_clean"] = raw.info["nchan"]
        log(f"  Data rank: {{rank}} (channels: {{raw.info['nchan']}})")
        return raw, rank

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 10: ICA DECOMPOSITION
    # ═══════════════════════════════════════════════════════════════════════
    @step("10_ica")
    def run_ica(raw, rank):
        import mne
        n_components = min(rank - 1, raw.info["nchan"] - 1, 25)
        if n_components < 2:
            log("  Skipping ICA: not enough components")
            return raw, None
        ica = mne.preprocessing.ICA(
            n_components=n_components,
            method="{cfg.ica_method}",
            random_state=42,
            verbose=False,
        )
        ica.fit(raw, verbose=False)
        quality["ica_n_components"] = ica.n_components_
        log(f"  ICA fitted: {{ica.n_components_}} components")
        return raw, ica

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 11: COMPONENT CLASSIFICATION (ICLabel)
    # ═══════════════════════════════════════════════════════════════════════
    @step("11_classify_components")
    def classify_ica(raw, ica):
        if ica is None:
            return raw, ica
        try:
            from mne_icalabel import label_components
            labels = label_components(raw, ica, method="iclabel")
            pred_labels = labels["labels"]
            pred_proba = labels["y_pred_proba"]
            exclude = []
            for idx, (lbl, proba) in enumerate(zip(pred_labels, pred_proba)):
                max_p = float(max(proba))
                if lbl != "brain" and max_p >= {cfg.icalabel_threshold}:
                    exclude.append(idx)
            ica.exclude = exclude
            quality["ica_excluded"] = len(exclude)
            quality["ica_labels"] = {{i: l for i, l in enumerate(pred_labels)}}
            log(f"  ICLabel: excluding {{len(exclude)}} components: {{exclude}}")
        except Exception as e:
            log(f"  ICLabel unavailable ({{e}}); using EOG correlation fallback")
            try:
                eog_idx, eog_scores = ica.find_bads_eog(raw, verbose=False)
                ica.exclude = eog_idx[:3]
                quality["ica_excluded"] = len(ica.exclude)
                log(f"  EOG-based exclusion: {{ica.exclude}}")
            except Exception:
                log("  No automatic component rejection possible")
                quality["ica_excluded"] = 0
        return raw, ica

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 12: CLEAN RECONSTRUCTION
    # ═══════════════════════════════════════════════════════════════════════
    @step("12_reconstruct")
    def reconstruct(raw, ica):
        if ica is not None and ica.exclude:
            ica.apply(raw, verbose=False)
            log(f"  Reconstructed after removing {{len(ica.exclude)}} components")
        else:
            log("  No components removed")

        # Save ICA component plot
        try:
            fig = ica.plot_components(show=False)
            if isinstance(fig, list):
                for i, f in enumerate(fig):
                    f.savefig(OUTDIR / f"{{PREFIX}}_ica_components_{{i}}.png", dpi=120)
                    plt.close(f)
            else:
                fig.savefig(OUTDIR / f"{{PREFIX}}_ica_components.png", dpi=120)
                plt.close(fig)
            log("  Saved ICA component maps")
        except Exception as _ica_exc:
            log(f"  ICA component plot skipped: {{_ica_exc}}")
        return raw, ica

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 13: EVENT STRUCTURE
    # ═══════════════════════════════════════════════════════════════════════
    @step("13_events")
    def analyze_events(raw):
        import mne
        try:
            events = mne.find_events(raw, verbose=False)
            unique = np.unique(events[:, 2])
            log(f"  Found {{len(events)}} events, types: {{unique.tolist()}}")
            quality["n_events"] = len(events)
            quality["event_types"] = unique.tolist()
            return raw, events
        except Exception:
            events, event_id = mne.events_from_annotations(raw, verbose=False)
            log(f"  From annotations: {{len(events)}} events, ids: {{event_id}}")
            quality["n_events"] = len(events)
            return raw, events

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 14-15: EPOCH EXTRACTION + REJECTION
    # ═══════════════════════════════════════════════════════════════════════
    @step("14_epochs")
    def extract_epochs(raw, events):
        import mne
        if events is None or len(events) < 3:
            log("  Not enough events for epoching; using fixed-length epochs")
            epochs = mne.make_fixed_length_epochs(
                raw, duration=2.0, preload=True, verbose=False
            )
        else:
            epochs = mne.Epochs(
                raw, events,
                tmin={cfg.epoch_tmin}, tmax={cfg.epoch_tmax},
                baseline={baseline_repr},
                reject=dict(eeg={cfg.epoch_reject_uv}e-6),
                preload=True, verbose=False,
            )
        n_before = len(epochs)
        epochs.drop_bad(verbose=False)
        n_after = len(epochs)
        quality["epochs_total"] = n_before
        quality["epochs_kept"] = n_after
        quality["epochs_rejected_pct"] = round(100 * (1 - n_after / max(n_before, 1)), 1)
        log(f"  Epochs: {{n_after}}/{{n_before}} kept ({{quality['epochs_rejected_pct']}}% rejected)")
        return epochs

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 15: AUTOREJECT (if available)
    # ═══════════════════════════════════════════════════════════════════════
    @step("15_autoreject")
    def run_autoreject(epochs):
        try:
            from autoreject import AutoReject
            ar = AutoReject(n_interpolate=[1, 2, 4], random_state=42, verbose=False)
            epochs_clean = ar.fit_transform(epochs)
            n_before = len(epochs)
            n_after = len(epochs_clean)
            quality["autoreject_applied"] = True
            quality["autoreject_kept"] = n_after
            log(f"  AutoReject: {{n_after}}/{{n_before}} epochs kept")
            return epochs_clean
        except ImportError:
            log("  autoreject not installed; skipping (using amplitude rejection only)")
            quality["autoreject_applied"] = False
            return epochs
        except Exception as e:
            log(f"  autoreject failed: {{e}}; continuing with amplitude rejection")
            quality["autoreject_applied"] = False
            return epochs

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 16: ERP ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════
    @step("16_erp")
    def erp_analysis(epochs):
        evoked = epochs.average()
        fig = evoked.plot(show=False, spatial_colors=True)
        fig.savefig(OUTDIR / f"{{PREFIX}}_erp_waveform.png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        log("  Saved ERP waveform")
        # Topomap at peak
        try:
            fig2 = evoked.plot_topomap(times="auto", show=False)
            fig2.savefig(OUTDIR / f"{{PREFIX}}_erp_topomap.png", dpi=120, bbox_inches="tight")
            plt.close(fig2)
            log("  Saved ERP topomap")
        except Exception as _topo_exc:
            log(f"  ERP topomap skipped: {{_topo_exc}}")
        return evoked

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 17: ERP IMAGE
    # ═══════════════════════════════════════════════════════════════════════
    @step("17_erpimage")
    def erpimage(epochs):
        pick = "Cz" if "Cz" in epochs.ch_names else epochs.ch_names[0]
        fig = epochs.plot_image(picks=[pick], show=False)[0]
        fig.savefig(OUTDIR / f"{{PREFIX}}_erpimage_{{pick}}.png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        log(f"  Saved ERPimage for {{pick}}")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 18: TIME-FREQUENCY (ERSP)
    # ═══════════════════════════════════════════════════════════════════════
    @step("18_time_frequency")
    def time_frequency(epochs):
        import mne
        freqs = np.arange(2, 40, 1)
        pick = "Cz" if "Cz" in epochs.ch_names else epochs.ch_names[0]
        power = mne.time_frequency.tfr_morlet(
            epochs, freqs=freqs, n_cycles=freqs / 2.0,
            picks=[pick], return_itc=False, verbose=False, average=True,
        )
        figs = power.plot(picks=[pick], show=False)
        if isinstance(figs, list):
            for fi, fig in enumerate(figs):
                fig.savefig(OUTDIR / f"{{PREFIX}}_tfr_{{pick}}_{{fi}}.png", dpi=120, bbox_inches="tight")
                plt.close(fig)
        else:
            figs.savefig(OUTDIR / f"{{PREFIX}}_tfr_{{pick}}.png", dpi=120, bbox_inches="tight")
            plt.close(figs)
        log(f"  Saved TFR for {{pick}}")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 19: SPECTRAL BAND POWER
    # ═══════════════════════════════════════════════════════════════════════
    @step("19_spectral")
    def spectral_power(epochs):
        bands = {bands_repr}
        psd = epochs.compute_psd(method="welch", fmin=0.5, fmax=40, verbose=False)
        freqs_arr = psd.freqs
        psd_data = psd.get_data().mean(axis=0)  # avg over epochs
        band_power = {{}}
        for band, (fmin, fmax) in bands.items():
            idx = np.where((freqs_arr >= fmin) & (freqs_arr <= fmax))[0]
            bp = psd_data[:, idx].mean(axis=1)
            band_power[band] = {{ch: float(bp[i]) for i, ch in enumerate(epochs.ch_names)}}
        quality["band_power_mean"] = {{b: float(np.mean(list(v.values()))) for b, v in band_power.items()}}
        log(f"  Band power computed: {{list(bands.keys())}}")

        # Topomap per band
        try:
            import mne
            info = epochs.info.copy()
            fig, axes = plt.subplots(1, len(bands), figsize=(3*len(bands), 3))
            if len(bands) == 1:
                axes = [axes]
            for ax, (band, (fmin, fmax)) in zip(axes, bands.items()):
                idx = np.where((freqs_arr >= fmin) & (freqs_arr <= fmax))[0]
                bp = psd_data[:, idx].mean(axis=1)
                v0, v1 = float(np.percentile(bp, 5)), float(np.percentile(bp, 95))
                if v1 <= v0:
                    v1 = v0 + 1e-30
                mne.viz.plot_topomap(
                    bp, info, axes=ax, show=False,
                    cmap="viridis",
                    vlim=(v0, v1),
                )
                ax.set_title(band)
            fig.savefig(OUTDIR / f"{{PREFIX}}_band_topomaps.png", dpi=120, bbox_inches="tight")
            plt.close(fig)
            log("  Saved band power topomaps")
        except Exception as e:
            log(f"  Topomap skipped: {{e}}")
        return band_power

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 20: CONNECTIVITY
    # ═══════════════════════════════════════════════════════════════════════
    @step("20_connectivity")
    def connectivity(epochs):
        from mne_connectivity import spectral_connectivity_epochs
        con = spectral_connectivity_epochs(
            epochs, method="{cfg.connectivity_method}",
            fmin={cfg.connectivity_fmin}, fmax={cfg.connectivity_fmax},
            faverage=False, verbose=False,
        )
        con_full = con.get_data(output="dense")
        con_data = np.mean(con_full, axis=-1) if con_full.ndim == 3 else con_full[:, :, 0]
        quality["connectivity_mean"] = float(np.mean(con_data[np.triu_indices_from(con_data, k=1)]))

        fig, ax = plt.subplots(figsize=(8, 6))
        im = ax.imshow(con_data, cmap="hot", vmin=0, vmax=1)
        ax.set_xticks(range(len(epochs.ch_names)))
        ax.set_xticklabels(epochs.ch_names, rotation=90, fontsize=6)
        ax.set_yticks(range(len(epochs.ch_names)))
        ax.set_yticklabels(epochs.ch_names, fontsize=6)
        ax.set_title("{cfg.connectivity_method.upper()} connectivity ({cfg.connectivity_fmin}-{cfg.connectivity_fmax} Hz)")
        plt.colorbar(im, ax=ax)
        fig.savefig(OUTDIR / f"{{PREFIX}}_connectivity.png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        log("  Saved connectivity matrix")

        ch_list = list(epochs.ch_names)
        try:
            _jpath = OUTDIR / f"{{PREFIX}}_connectivity.json"
            _jpath.write_text(
                json.dumps({{
                    "method": "{cfg.connectivity_method}",
                    "fmin": {cfg.connectivity_fmin},
                    "fmax": {cfg.connectivity_fmax},
                    "ch_names": ch_list,
                    "matrix": con_data.astype(float).tolist(),
                }}, indent=2),
                encoding="utf-8",
            )
            log(f"  Saved {{_jpath.name}}")
        except Exception as _ejson:
            log(f"  Connectivity JSON skipped: {{_ejson}}")

        _ncsv = {repr(_eff_norm_csv)}
        if _ncsv:
            try:
                import csv as _csv
                from pathlib import Path as _Path
                _nf = _Path(_ncsv)
                if not _nf.is_file():
                    log(f"  Connectivity norm CSV not found: {{_nf}}")
                else:
                    _norms = {{}}
                    with open(_nf, newline="", encoding="utf-8-sig") as _cf:
                        for _row in _csv.DictReader(_cf):
                            _m = str(_row.get("method", "")).strip().lower()
                            _ca = str(_row.get("ch_a", "")).strip()
                            _cb = str(_row.get("ch_b", "")).strip()
                            if not _m or not _ca or not _cb:
                                continue
                            _f0 = float(_row["fmin"])
                            _f1 = float(_row["fmax"])
                            _mean = float(_row["mean"])
                            _sd = float(_row["sd"])
                            if _sd <= 0:
                                continue
                            _a, _b = sorted([_ca, _cb], key=lambda x: x.upper())
                            _norms[(_m, _f0, _f1, f"{{_a}}--{{_b}}")] = (_mean, _sd)
                    _meth = "{cfg.connectivity_method}".lower()
                    _f0p, _f1p = float({cfg.connectivity_fmin}), float({cfg.connectivity_fmax})
                    n = con_data.shape[0]
                    zmat = np.full((n, n), np.nan, dtype=float)
                    got = 0
                    tot = 0
                    for _i in range(n):
                        for _j in range(_i + 1, n):
                            tot += 1
                            _a, _b = sorted([ch_list[_i], ch_list[_j]], key=lambda x: str(x).upper())
                            _pk = (_meth, _f0p, _f1p, f"{{_a}}--{{_b}}")
                            _st = _norms.get(_pk)
                            if _st and _st[1] > 0:
                                _zv = (float(con_data[_i, _j]) - _st[0]) / _st[1]
                                zmat[_i, _j] = zmat[_j, _i] = _zv
                                got += 1
                    quality["connectivity_z_matched_pairs"] = got
                    quality["connectivity_z_total_pairs"] = tot
                    _zjson = OUTDIR / f"{{PREFIX}}_connectivity_z.json"
                    _zdata = []
                    for _ii in range(n):
                        _zr = []
                        for _jj in range(n):
                            _v = zmat[_ii, _jj]
                            _zr.append(None if (_v != _v) else round(float(_v), 4))
                        _zdata.append(_zr)
                    _zjson.write_text(
                        json.dumps({{
                            "method": "{cfg.connectivity_method}",
                            "fmin": {cfg.connectivity_fmin},
                            "fmax": {cfg.connectivity_fmax},
                            "ch_names": ch_list,
                            "norm_csv": str(_nf),
                            "z_matrix": _zdata,
                            "n_matched_pairs": got,
                            "n_upper_triangle_pairs": tot,
                        }}, indent=2),
                        encoding="utf-8",
                    )
                    log(f"  Saved {{_zjson.name}} ({{got}}/{{tot}} pair z-scores)")
                    try:
                        figz, axz = plt.subplots(figsize=(8, 6))
                        _vlim = float(np.nanmax(np.abs(zmat)))
                        if not np.isfinite(_vlim) or _vlim <= 0:
                            _vlim = 3.0
                        imz = axz.imshow(zmat, cmap="RdBu_r", vmin=-_vlim, vmax=_vlim, interpolation="nearest")
                        axz.set_xticks(range(n))
                        axz.set_xticklabels(ch_list, rotation=90, fontsize=6)
                        axz.set_yticks(range(n))
                        axz.set_yticklabels(ch_list, fontsize=6)
                        axz.set_title("Connectivity z-scores (normative)")
                        plt.colorbar(imz, ax=axz)
                        figz.savefig(OUTDIR / f"{{PREFIX}}_connectivity_z.png", dpi=120, bbox_inches="tight")
                        plt.close(figz)
                        log("  Saved connectivity_z.png")
                    except Exception as _ezfig:
                        log(f"  Connectivity z heatmap skipped: {{_ezfig}}")
            except Exception as _ezall:
                log(f"  Connectivity z-scoring failed: {{_ezall}}")

        return con_data

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 21: NETWORK METRICS
    # ═══════════════════════════════════════════════════════════════════════
    @step("21_network_metrics")
    def network_metrics(con_data, ch_names):
        if con_data is None:
            return
        n = con_data.shape[0]
        node_strength = con_data.sum(axis=1) / (n - 1)
        global_sync = float(np.mean(con_data[np.triu_indices(n, k=1)]))
        top_pairs = []
        triu = np.triu_indices(n, k=1)
        vals = con_data[triu]
        top_idx = np.argsort(vals)[-5:][::-1]
        for idx in top_idx:
            i, j = triu[0][idx], triu[1][idx]
            top_pairs.append(f"{{ch_names[i]}}-{{ch_names[j]}}: {{vals[idx]:.3f}}")
        quality["global_synchronization"] = global_sync
        quality["top_connected_pairs"] = top_pairs
        log(f"  Global sync: {{global_sync:.3f}}")
        log(f"  Top pairs: {{', '.join(top_pairs[:3])}}")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 22: QUALITY SUMMARY
    # ═══════════════════════════════════════════════════════════════════════
    @step("22_quality_summary")
    def quality_summary(raw):
        # Post-processing PSD for SNR estimate
        psd_clean = raw.compute_psd(fmax=50, verbose=False)
        quality["duration_after_sec"] = raw.n_times / raw.info["sfreq"]
        log(f"  Final duration: {{quality['duration_after_sec']:.1f}} sec")
        log(f"  Channels: {{raw.info['nchan']}}")
        log(f"  Bad channels removed: {{quality.get('bad_channels', [])}}")
        log(f"  ICA components excluded: {{quality.get('ica_excluded', 0)}}")
        log(f"  Epochs kept: {{quality.get('epochs_kept', 'N/A')}}")

        fig = psd_clean.plot(show=False)
        fig.savefig(OUTDIR / f"{{PREFIX}}_psd_clean.png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        log("  Saved clean PSD")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 23-24: EXPORT & REPORT
    # ═══════════════════════════════════════════════════════════════════════
    @step("23_export")
    def export_data(raw, ica, epochs):
        if {repr(cfg.save_cleaned)}:
            out_file = OUTDIR / f"{{PREFIX}}_cleaned.fif"
            raw.save(out_file, overwrite=True, verbose=False)
            log(f"  Saved cleaned raw: {{out_file.name}}")
        if ica is not None:
            ica_file = OUTDIR / f"{{PREFIX}}_ica.fif"
            ica.save(ica_file, overwrite=True)
            log(f"  Saved ICA: {{ica_file.name}}")
        if epochs is not None:
            ep_file = OUTDIR / f"{{PREFIX}}_epochs.fif"
            epochs.save(ep_file, overwrite=True, verbose=False)
            log(f"  Saved epochs: {{ep_file.name}}")

    @step("24_report")
    def create_report():
        report_path = OUTDIR / f"{{PREFIX}}_report.txt"
        lines = ["=" * 60, "PARADOX EEG PIPELINE REPORT", "=" * 60, ""]
        lines.append(f"Input: {{INPUT_FILE}}")
        lines.append(f"Generated: {{datetime.now().isoformat()}}")
        lines.append("")
        lines.append("--- STEP STATUS ---")
        for name, status in step_status.items():
            lines.append(f"  {{name}}: {{status}}")
        lines.append("")
        lines.append("--- QUALITY METRICS ---")
        for k, v in quality.items():
            lines.append(f"  {{k}}: {{v}}")
        lines.append("")
        lines.append("--- PROCESSING LOG ---")
        lines.extend(report_lines)
        report_text = "\\n".join(lines)
        report_path.write_text(report_text, encoding="utf-8")
        log(f"  Report: {{report_path.name}}")

        # JSON metrics
        json_path = OUTDIR / f"{{PREFIX}}_metrics.json"
        json_path.write_text(json.dumps({{
            "quality": quality,
            "step_status": step_status,
        }}, indent=2, default=str), encoding="utf-8")
        log(f"  Metrics JSON: {{json_path.name}}")

    # ═══════════════════════════════════════════════════════════════════════
    # MAIN PIPELINE
    # ═══════════════════════════════════════════════════════════════════════
    def main():
        log(f"Paradox EEG Pipeline starting: {{INPUT_FILE}}")

        raw = load_data()
        if raw is None:
            log("FATAL: could not load data"); return

        user_rereference(raw)
        quality_diagnostics(raw)
        baseline_viz(raw)
        apply_filters(raw)
        notch_filter(raw)
        detect_bad_channels(raw)
        interpolate_bads(raw)
        rereference(raw)

        result = compute_rank(raw)
        rank = result[1] if result else raw.info["nchan"] - 1

        result = run_ica(raw, rank)
        ica = result[1] if result else None

        result = classify_ica(raw, ica)
        ica = result[1] if result else ica

        reconstruct(raw, ica)

        result = analyze_events(raw)
        events = result[1] if result else None

        epochs = extract_epochs(raw, events)
        if epochs is not None:
            epochs = run_autoreject(epochs) or epochs

        if epochs is not None:
            erp_analysis(epochs)
            erpimage(epochs)
            time_frequency(epochs)
            band_power = spectral_power(epochs)
            con_data = connectivity(epochs)
            network_metrics(con_data, epochs.ch_names)

        quality_summary(raw)
        export_data(raw, ica, epochs)
        create_report()

        ok = sum(1 for v in step_status.values() if v == "OK")
        total = len(step_status)
        log(f"\\nPIPELINE COMPLETE: {{ok}}/{{total}} steps succeeded")
        print(f"\\n--- QUALITY METRICS ---")
        for k, v in quality.items():
            print(f"  {{k}}: {{v}}")

    if __name__ == "__main__":
        main()
    ''')
    return script
