"""Orchestrator: runs all ported Decoder visualizations on pipeline output.

Designed to run as a **subprocess** (``python run_visualizations.py <edf> <job_dir> <stem> [condition]``)
so that it executes in the system Python with MNE / scipy / matplotlib / plotly installed,
rather than inside the PyInstaller-bundled exe which excludes those heavy libraries.

Can also be imported and called directly during development.
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

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("hexnode.eeg.viz")


def _compute_metrics_by_site(
    raw, bands: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Compute per-channel band power metrics in the flat format the Decoder viz modules expect.

    The Decoder's ``extract_band_values`` looks for capitalized band names as
    top-level keys: ``{ch: {"Delta": value, "Theta": value, ...}}``.
    We also store the full PSD array under ``"psd"`` / ``"freqs"`` for the
    spectrum generator.
    """
    if bands is None:
        bands = {
            "delta": (0.5, 4.0),
            "theta": (4.0, 8.0),
            "alpha": (8.0, 13.0),
            "smr": (12.0, 15.0),
            "beta": (13.0, 30.0),
            "hibeta": (20.0, 30.0),
            "gamma": (30.0, 40.0),
        }

    _trapz = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    from scipy.signal import welch
    import mne

    sfreq = raw.info["sfreq"]
    picks = mne.pick_types(raw.info, meg=False, eeg=True, exclude=[])
    data = raw.get_data(picks=picks)
    ch_names = [raw.ch_names[i] for i in picks]

    nperseg = min(int(sfreq * 2), data.shape[1])
    metrics: dict[str, Any] = {}

    for idx, ch in enumerate(ch_names):
        freqs, psd = welch(data[idx], fs=sfreq, nperseg=nperseg)
        total = float(_trapz(psd, freqs))

        _BAND_KEY = {"smr": "SMR", "hibeta": "HiBeta"}
        site: dict[str, Any] = {}
        for band_name, (fmin, fmax) in bands.items():
            mask = (freqs >= fmin) & (freqs <= fmax)
            val = float(_trapz(psd[mask], freqs[mask])) if mask.any() else 0.0
            site[_BAND_KEY.get(band_name, band_name.capitalize())] = val

        peak_mask = (freqs >= 1) & (freqs <= 40)
        peak_freq = float(freqs[peak_mask][np.argmax(psd[peak_mask])]) if peak_mask.any() else 0.0

        site["total_power"] = total
        site["peak_frequency"] = peak_freq
        site["psd"] = psd.tolist()
        site["freqs"] = freqs.tolist()
        metrics[ch] = site

    return metrics


def _load_raw(edf_path: Path, fif_dir: Path, stem: str):
    """Try to load cleaned .fif first, fall back to raw EDF."""
    import mne

    fif_candidates = [
        fif_dir / f"{stem}_cleaned.fif",
        fif_dir / f"{stem}_raw.fif",
    ]
    for fif in fif_candidates:
        if fif.is_file():
            try:
                return mne.io.read_raw_fif(str(fif), preload=True, verbose=False)
            except Exception:
                continue

    return mne.io.read_raw_edf(str(edf_path), preload=True, verbose=False)


def run_all_visualizations(
    edf_path: Path,
    job_dir: Path,
    stem: str,
    condition: str = "EC",
) -> list[str]:
    """Run all available visualizations and return list of generated filenames."""

    generated: list[str] = []
    viz_dir = job_dir

    _dep_missing: list[str] = []
    for _dep_name, _dep_check in [
        ("plotly", "plotly.graph_objects"),
        ("mne", "mne"),
        ("scipy", "scipy.signal"),
        ("matplotlib", "matplotlib.pyplot"),
    ]:
        try:
            __import__(_dep_check)
        except ImportError:
            _dep_missing.append(_dep_name)
    if _dep_missing:
        logger.warning(
            "Missing packages in this Python: %s. Install them for full visualization output: "
            "pip install %s",
            ", ".join(_dep_missing),
            " ".join(_dep_missing),
        )

    try:
        raw = _load_raw(edf_path, job_dir, stem)
    except Exception as exc:
        logger.warning("Could not load EEG data for visualizations: %s", exc)
        return generated

    try:
        metrics_by_site = _compute_metrics_by_site(raw)
    except Exception as exc:
        logger.warning("Could not compute per-site metrics: %s", exc)
        metrics_by_site = {}

    try:
        from hexnode.eeg.norms.enrichment import enrich_metrics_with_normative_z

        enrich_metrics_with_normative_z(metrics_by_site)
    except Exception as exc:
        logger.debug("Normative z enrichment skipped: %s", exc)

    sfreq = raw.info["sfreq"]

    # Clear stale interpolation cache so topomaps are always freshly computed
    stale_cache = viz_dir / ".topomap_interp_cache.pkl"
    if stale_cache.is_file():
        try:
            stale_cache.unlink()
        except OSError:
            pass

    # ── 1. Topomaps (absolute + relative power) ──────────────────────────
    try:
        from hexnode.eeg.viz.topomap_generator import TopomapGenerator

        topo = TopomapGenerator()
        result = topo.generate_band_topomaps(
            metrics_by_site=metrics_by_site,
            output_dir=viz_dir,
            subject_id=stem,
            session_id=condition,
        )
        for path in result.values():
            generated.append(Path(path).name)
        logger.info("Topomaps: %d files", len(result))
    except Exception as exc:
        logger.warning("Topomap generation failed: %s", exc)

    # ── 2. Abs vs Rel pair topomaps ──────────────────────────────────────
    try:
        from hexnode.eeg.viz.topomap_generator import TopomapGenerator as TG2

        topo2 = TG2()
        result = topo2.generate_abs_rel_pair_topomaps(
            metrics_by_site=metrics_by_site,
            output_dir=viz_dir,
            subject_id=stem,
            session_id=condition,
        )
        for path in result.values():
            generated.append(Path(path).name)
    except Exception as exc:
        logger.warning("Abs/Rel pair topomaps failed: %s", exc)

    # ── 3. Spectrum / PSD ────────────────────────────────────────────────
    try:
        from hexnode.eeg.viz.spectrum_generator import SpectrumGenerator

        spec = SpectrumGenerator()
        result = spec.generate_power_spectra(
            metrics_by_site=metrics_by_site,
            raw_data=raw,
            sfreq=sfreq,
            output_dir=viz_dir,
            subject_id=stem,
            session_id=condition,
        )
        if isinstance(result, dict):
            for path in result.values():
                generated.append(Path(path).name)
        elif result:
            generated.append(Path(result).name)
        logger.info("PSD spectra generated")
    except Exception as exc:
        logger.warning("Spectrum generation failed: %s", exc)

    # ── 4. 3D Scalp HTML (interactive Plotly) — one per band ─────────────
    try:
        from hexnode.eeg.viz.scalp_3d_generator import generate_3d_scalp_html

        scalp_count = 0
        for band in ["alpha", "beta", "theta", "delta", "gamma"]:
            try:
                html_path = generate_3d_scalp_html(
                    metrics_by_site=metrics_by_site,
                    norm_violations=None,
                    output_dir=viz_dir,
                    subject_id=stem,
                    session_id=condition,
                    band=band,
                    epoch=None,
                )
                if html_path:
                    generated.append(Path(html_path).name)
                    scalp_count += 1
            except Exception as exc:
                logger.debug("3D scalp for %s failed: %s", band, exc)
        if scalp_count:
            logger.info("3D scalp HTML: %d band maps generated", scalp_count)
    except Exception as exc:
        logger.warning("3D scalp generation failed: %s", exc)

    # ── 5. Topo sheet (band power composite grid) ────────────────────────
    try:
        from hexnode.eeg.viz.topo_sheet_generator import TopoSheetGenerator

        sheet = TopoSheetGenerator()
        result = sheet.generate_bandpower_sheet(
            metrics_by_site=metrics_by_site,
            output_dir=viz_dir,
            subject_id=stem,
            session_id=condition,
        )
        if isinstance(result, dict):
            for path in result.values():
                generated.append(Path(path).name)
        elif result:
            generated.append(Path(result).name)
        logger.info("Topo sheet generated")
    except Exception as exc:
        logger.warning("Topo sheet generation failed: %s", exc)

    # ── 5b. Absolute + Relative power sheets ─────────────────────────────
    try:
        from hexnode.eeg.viz.topo_sheet_generator import TopoSheetGenerator as TS2

        sheet2 = TS2()
        for method in ("generate_absolute_sheet", "generate_relative_sheet"):
            try:
                fn = getattr(sheet2, method)
                r = fn(
                    metrics_by_site=metrics_by_site,
                    output_dir=viz_dir,
                    subject_id=stem,
                    session_id=condition,
                )
                if isinstance(r, dict):
                    for p in r.values():
                        generated.append(Path(p).name)
                elif r:
                    generated.append(Path(r).name)
            except Exception as exc:
                logger.debug("Sheet method %s failed: %s", method, exc)
    except Exception as exc:
        logger.warning("Abs/Rel sheets failed: %s", exc)

    # ── 6. Microstate visualizations ─────────────────────────────────────
    try:
        microstate_dict = _compute_microstates(raw)
        if microstate_dict:
            from hexnode.eeg.viz.microstate_visualizer import (
                generate_interactive_microstate_html,
                generate_microstate_visualizations,
            )

            result = generate_microstate_visualizations(
                microstate_dict=microstate_dict,
                viz_dir=viz_dir,
                subject_id=stem,
                session_id=condition,
            )
            for path in result.values():
                generated.append(Path(path).name)

            ms_html = generate_interactive_microstate_html(
                microstate_dict=microstate_dict,
                viz_dir=viz_dir,
                subject_id=stem,
                session_id=condition,
            )
            if ms_html:
                generated.append(Path(ms_html).name)
            logger.info("Microstate visualizations generated")
    except Exception as exc:
        logger.warning("Microstate generation failed: %s", exc)

    logger.info("Visualization orchestrator complete: %d files generated", len(generated))
    return generated


# ── Helper functions ─────────────────────────────────────────────────────


def _compute_microstates(raw) -> dict[str, Any] | None:
    """Compute basic microstate clustering using k-means on GFP peaks.

    Returns a dict matching the contract expected by
    ``microstate_visualizer.generate_microstate_visualizations`` and
    ``generate_interactive_microstate_html``:

        maps            – list of arrays (n_states x n_channels)
        state_labels    – ["A", "B", …]
        ch_names        – channel name list
        labels_downsampled / gfp_downsampled – for interactive timeline
    """
    try:
        from sklearn.cluster import KMeans

        data = raw.get_data(picks="eeg")
        sfreq = raw.info["sfreq"]
        gfp = np.std(data, axis=0)
        threshold = np.percentile(gfp, 95)
        peak_indices = np.where(gfp > threshold)[0]

        if len(peak_indices) < 20:
            return None

        peak_maps = data[:, peak_indices].T
        n_states = min(4, len(peak_indices) // 5)
        if n_states < 2:
            return None

        kmeans = KMeans(n_clusters=n_states, n_init=10, random_state=42)
        labels_peaks = kmeans.fit_predict(peak_maps)

        state_labels = ["A", "B", "C", "D"][:n_states]
        maps = [kmeans.cluster_centers_[i].tolist() for i in range(n_states)]

        ch_names = [raw.ch_names[i] for i in range(min(data.shape[0], len(raw.ch_names)))]

        # Back-fit all time-points to nearest centroid for the segmentation timeline
        all_labels = kmeans.predict(data.T)

        # Downsample labels + GFP to ~50 Hz for the interactive panel
        ds_hz = 50.0
        step = max(1, int(round(sfreq / ds_hz)))
        labels_ds = all_labels[::step].tolist()
        gfp_ds = gfp[::step].tolist()

        # Transition matrix (n_states x n_states, row-normalised probabilities)
        trans = np.zeros((n_states, n_states), dtype=float)
        for a, b in zip(all_labels[:-1], all_labels[1:]):
            trans[a, b] += 1
        row_sums = trans.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        trans = (trans / row_sums).tolist()

        # Per-state statistics
        stats: dict[str, Any] = {}
        duration_s = data.shape[1] / sfreq
        for si, name in enumerate(state_labels):
            mask = all_labels == si
            coverage = float(np.sum(mask) / len(all_labels))
            segments = np.diff(np.concatenate(([0], mask.astype(int), [0])))
            n_seg = int(np.sum(segments == 1))
            mean_dur = (coverage * duration_s / n_seg) if n_seg else 0
            stats[name] = {
                "coverage": round(coverage, 4),
                "mean_duration_ms": round(mean_dur * 1000, 1),
                "occurrences_per_s": round(n_seg / duration_s, 2) if duration_s else 0,
                "mean_gfp": round(float(np.mean(gfp[mask])), 4) if np.any(mask) else 0,
            }

        return {
            "n_states": n_states,
            "maps": maps,
            "state_labels": state_labels,
            "ch_names": ch_names,
            "labels": all_labels.tolist(),
            "labels_downsampled": labels_ds,
            "labels_downsample_hz": ds_hz,
            "gfp_downsampled": gfp_ds,
            "gfp_peaks": peak_indices.tolist(),
            "transition_matrix": trans,
            "stats": stats,
        }
    except Exception as exc:
        logger.warning("Microstate computation failed: %s", exc)
        return None


# ── CLI entry point (for subprocess invocation) ─────────────────────────

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")

    import matplotlib
    matplotlib.use("Agg")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 4:
        print("Usage: python run_visualizations.py <edf_path> <job_dir> <stem> [condition]", file=sys.stderr)
        sys.exit(1)

    edf_path = Path(sys.argv[1])
    job_dir = Path(sys.argv[2])
    stem = sys.argv[3]
    condition = sys.argv[4] if len(sys.argv) > 4 else "EC"

    job_dir.mkdir(parents=True, exist_ok=True)
    generated = run_all_visualizations(edf_path, job_dir, stem, condition)

    manifest = job_dir / "_viz_manifest.json"
    manifest.write_text(json.dumps({"files": generated, "count": len(generated)}), encoding="utf-8")

    print(f"VIZ_COMPLETE: {len(generated)} files generated", flush=True)
    if not generated:
        print(
            "VIZ_HINT: No visualization files were written — check that mne, scipy, matplotlib, "
            "and plotly are installed in this Python (pip install mne scipy matplotlib plotly scikit-learn).",
            flush=True,
        )
    sys.exit(0)
