#!/usr/bin/env python3
"""
Topo Sheet Generator

Generates RyHa-style multi-panel topomap sheets (3×5, 4×5, etc.) for EEG analysis.
Matrix layouts: rows = metrics (Absolute, Relative, Z-Score), cols = bands.
Separate from individual topomaps; outputs topo_sheet_*.png for gallery integration.

Licensed under GNU General Public License v3.0
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


import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import logging

from hexnode.eeg.viz.theme_manager import get_theme_manager
from hexnode.eeg.viz.visualization_config import get_visualization_config
try:
    from hexnode.eeg.viz.topomap_generator import TopomapGenerator, get_band_frequency_range
except ImportError:
    TopomapGenerator = None
    get_band_frequency_range = None
from hexnode.eeg.viz.utils import (
    clean_channel_name, is_nested_structure, extract_band_values,
    extract_all_sites, get_all_available_epochs,
)
from hexnode.eeg.viz.connectivity_renderer import (
    plot_connectivity_cell, compute_asymmetry_pairs,
    get_coherence_pairs_for_band, get_phase_lag_pairs_for_band,
)

logger = logging.getLogger(__name__)

# Sheet band subsets (5 bands for summary, full set for others)
SHEET_BANDS_5 = ['delta', 'theta', 'alpha', 'beta', 'hibeta']
SHEET_BANDS_ALL = ['delta', 'theta', 'alpha', 'smr', 'beta', 'hibeta', 'gamma']


class TopoSheetGenerator:
    """Generates multi-panel topomap sheets (matrix layouts)."""

    def __init__(self, config=None):
        self.config = config or get_visualization_config()
        self.theme = get_theme_manager()
        self._topomap_gen = TopomapGenerator(config) if TopomapGenerator else None
        self._sheet_bands_summary = self.config.get('topomaps.topo_sheets.summary_bands', SHEET_BANDS_5)
        self._sheet_bands_all = self.config.get_topomap_bands() or SHEET_BANDS_ALL

    def _plot_topomap_cell(
        self,
        ax,
        values: np.ndarray,
        channel_names: List[str],
        title: str,
        is_zscore: bool = False,
    ) -> bool:
        """Plot a single topomap into an existing axes. Delegates to TopomapGenerator for consistency."""
        if self._topomap_gen is None:
            ax.axis('off')
            ax.set_title(title, color=self.theme.get_foreground_color(), fontsize=9)
            return False
        ok = self._topomap_gen.plot_topomap_into_axes(
            ax, np.asarray(values, dtype=float), channel_names, title,
            is_zscore=is_zscore, allow_constant=True
        )
        if not ok:
            ax.axis('off')
            ax.set_title(title, color=self.theme.get_foreground_color(), fontsize=9)
        return ok

    def _compute_relative_power(
        self, metrics_by_site: Dict[str, Any], band: str, epoch: Optional[str], bands_all: List[str]
    ) -> Tuple[List[str], np.ndarray]:
        """Compute relative power (percent of total) per channel for a band."""
        ch_names, abs_vals = extract_band_values(metrics_by_site, band, epoch)
        if len(ch_names) < 4:
            return ch_names, np.array(abs_vals)
        abs_vals = np.array(abs_vals, dtype=float)
        total_power = np.zeros(len(ch_names))
        ch_to_idx = {c: i for i, c in enumerate(ch_names)}
        ch_to_idx_lower = {clean_channel_name(c): i for i, c in enumerate(ch_names)}
        for b in bands_all:
            ch_b, v = extract_band_values(metrics_by_site, b, epoch)
            for i, ch in enumerate(ch_b):
                idx = ch_to_idx.get(ch) if ch in ch_to_idx else ch_to_idx_lower.get(clean_channel_name(ch))
                if idx is not None:
                    val = float(v[i]) if i < len(v) else 0.0
                    total_power[idx] += val ** 2
        total_power = np.sqrt(np.maximum(total_power, 1e-12))
        rel_vals = 100.0 * (abs_vals ** 2) / (total_power ** 2 + 1e-12)
        rel_vals = np.nan_to_num(rel_vals, nan=0.0, posinf=0.0, neginf=0.0)
        return ch_names, rel_vals

    def _zscore_values(self, values: np.ndarray) -> np.ndarray:
        """Normalize values to z-scores."""
        vals = np.asarray(values, dtype=float)
        vals = np.nan_to_num(vals, nan=0.0, posinf=0.0, neginf=0.0)
        mean_val = float(np.mean(vals))
        std_val = float(np.std(vals))
        if std_val <= 0 or not np.isfinite(std_val):
            std_val = 1.0
        z = (vals - mean_val) / std_val
        return np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0)

    def _composite_sheet_from_existing_images(
        self, viz_dir: Path, file_pattern: str, bands: List[str], epochs: List[Optional[str]],
        out_filename: str, key_prefix: str
    ) -> Dict[str, Path]:
        """
        Build a topo sheet by compositing existing individual topomap images.
        file_pattern: e.g. 'topomap_zscore_{band}' -> looks for topomap_zscore_delta_eo.png
        """
        paths = {}
        for ep in epochs:
            suffix = f"_{ep.lower()}" if ep else ""
            out_path = viz_dir / f"{out_filename}{suffix}.png"
            key = f"{key_prefix}{suffix}"
            imgs = []
            for band in bands:
                stem = file_pattern.format(band=band)
                for cand in ([f"{stem}_{ep}.png", f"{stem}_{ep.lower()}.png"] if ep else [f"{stem}.png"]):
                    p = viz_dir / cand
                    if p.exists():
                        imgs.append((band, str(p)))
                        break
            if len(imgs) < 2:
                continue
            try:
                from PIL import Image
                band_order = [b for b in bands if any(b == x[0] for x in imgs)]
                img_objs = [Image.open(next(p for x, p in imgs if x == b)).convert('RGB') for b in band_order]
                if len(img_objs) < 2:
                    continue
                w, h = img_objs[0].size
                n_cols = len(img_objs)
                composite = Image.new('RGB', (w * n_cols, h), (10, 14, 39))
                for i, img in enumerate(img_objs):
                    composite.paste(img.resize((w, h)), (i * w, 0))
                composite.save(out_path)
                paths[key] = out_path
                logger.info("Composited topo sheet from existing images: %s", out_path.name)
            except Exception as e:
                logger.debug("Composite fallback failed for %s: %s", out_filename, e)
        return paths

    def generate_zscore_summary_sheet(
        self,
        metrics_by_site: Dict[str, Any],
        norm_violations: Dict[str, Any],
        output_dir: Path,
        subject_id: str,
        session_id: str,
    ) -> Dict[str, Path]:
        """
        Generate Z-Score Summary sheet (3×5): rows=Absolute Power Z, Relative Power Z, Band Power Z;
        cols=Delta, Theta, Alpha, Beta, HiBeta.
        """
        if not self.config.are_topomaps_enabled() or not self.config.get('topomaps.generate_z_scores', True):
            return {}
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        bands = [b for b in self._sheet_bands_summary if b in self.config.get_topomap_bands()]
        if len(bands) < 2:
            return {}
        is_nested = is_nested_structure(metrics_by_site)
        epochs = get_all_available_epochs(metrics_by_site) if is_nested else [None]
        if not epochs:
            epochs = [None]
        bands_all = ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma', 'SMR', 'HiBeta']
        bands_all_lower = [b.lower() for b in bands_all]

        for epoch in epochs:
            n_rows, n_cols = 3, len(bands)
            fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.5 * n_cols, 3.2 * n_rows),
                                    facecolor=self.theme.get_background_color())
            fig.patch.set_facecolor(self.theme.get_background_color())
            fig.text(0.02, 0.98, "EEG Paradox Decoder - Z-Score Summary Sheet",
                    fontsize=11, fontweight='bold', color=self.theme.NEON_CYAN, ha='left', va='top',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=self.theme.get_background_color(),
                             alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5), transform=fig.transFigure, zorder=100)
            if epoch:
                fig.text(0.98, 0.98, epoch, fontsize=10, color=self.theme.get_foreground_color(), ha='right', va='top', transform=fig.transFigure)

            row_labels = ['Absolute Power Z', 'Relative Power Z', 'Amplitude Asymmetry']
            channel_names = extract_all_sites(metrics_by_site)

            for row_idx, row_label in enumerate(row_labels):
                for col_idx, band in enumerate(bands):
                    ax = axes[row_idx, col_idx] if n_cols > 1 else axes[row_idx]
                    band_display = {'hibeta': 'HiBeta', 'smr': 'SMR'}.get(band.lower(), band.capitalize())
                    freq = get_band_frequency_range(band) if get_band_frequency_range else None
                    band_part = f"{band_display} ({freq})" if freq else band_display
                    title = f"{band_part}\n{row_label}"
                    try:
                        if row_idx == 0:
                            ch_names, abs_vals = extract_band_values(metrics_by_site, band, epoch)
                            vals = self._zscore_values(np.array(abs_vals))
                            if len(ch_names) >= 4:
                                self._plot_topomap_cell(ax, vals, ch_names, title, is_zscore=True)
                            else:
                                ax.axis('off')
                                ax.set_title(title, fontsize=10, color=self.theme.get_foreground_color())
                        elif row_idx == 1:
                            ch_names, rel_vals = self._compute_relative_power(
                                metrics_by_site, band, epoch, bands_all_lower
                            )
                            vals = self._zscore_values(np.array(rel_vals))
                            if len(ch_names) >= 4:
                                self._plot_topomap_cell(ax, vals, ch_names, title, is_zscore=True)
                            else:
                                ax.axis('off')
                                ax.set_title(title, fontsize=10, color=self.theme.get_foreground_color())
                        else:
                            pairs = compute_asymmetry_pairs(
                                metrics_by_site, band, epoch, extract_band_values
                            )
                            if pairs:
                                opts = self.config.get('connectivity', {}) or {}
                                plot_connectivity_cell(ax, pairs, title, mode='asymmetry', theme=self.theme, options=opts if opts else None)
                            else:
                                ax.axis('off')
                                ax.set_title(title, fontsize=10, color=self.theme.get_foreground_color())
                    except Exception as e:
                        logger.debug("Z-score sheet cell %s %s: %s", row_label, band, e)
                        ax.axis('off')
                        ax.set_title(title, fontsize=10, color=self.theme.get_foreground_color())

            plt.tight_layout()
            suffix = f"_{epoch.lower()}" if epoch else ""
            filename = f"topo_sheet_zscore_summary_3x5{suffix}.png"
            filepath = output_dir / filename
            fig.savefig(filepath, format='png', dpi=self.config.get('default_dpi', 150),
                       facecolor=self.theme.get_background_color(), bbox_inches='tight', pad_inches=0.1)
            plt.close(fig)
            key = f"sheet_zscore_summary{suffix}"
            paths[key] = filepath
            logger.info("Generated Z-Score summary sheet: %s", filepath)

        return paths

    def generate_zscore_extended_sheet(
        self,
        metrics_by_site: Dict[str, Any],
        norm_violations: Dict[str, Any],
        coherence_metrics: Dict[str, Any],
        output_dir: Path,
        subject_id: str,
        session_id: str,
    ) -> Dict[str, Path]:
        """
        Generate Z-Score Extended sheet (5×5): rows=Absolute Power Z, Relative Power Z,
        Amplitude Asymmetry, Coherence, Phase Lag; cols=Delta, Theta, Alpha, Beta, HiBeta.
        Coherence and Phase Lag use connectivity line diagrams when data available.
        """
        if not self.config.are_topomaps_enabled() or not self.config.get('topomaps.generate_z_scores', True):
            return {}
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        bands = [b for b in self._sheet_bands_summary if b in self.config.get_topomap_bands()]
        if len(bands) < 2:
            return {}
        is_nested = is_nested_structure(metrics_by_site)
        epochs = get_all_available_epochs(metrics_by_site) if is_nested else [None]
        if not epochs:
            epochs = [None]
        bands_all_lower = ['delta', 'theta', 'alpha', 'smr', 'beta', 'hibeta', 'gamma']
        all_pairs = coherence_metrics.get('all_pairs_coherence', {})
        all_pairs_phase = coherence_metrics.get('all_pairs_phase_lag', {})
        segments_info = coherence_metrics.get('segments', {})
        has_coherence = bool(all_pairs)
        has_phase_lag = bool(all_pairs_phase)

        for epoch in epochs:
            n_rows, n_cols = 5, len(bands)
            fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.5 * n_cols, 2.8 * n_rows),
                                    facecolor=self.theme.get_background_color())
            fig.patch.set_facecolor(self.theme.get_background_color())
            fig.text(0.02, 0.98, "EEG Paradox Decoder - Z-Score Extended (5×5)",
                    fontsize=11, fontweight='bold', color=self.theme.NEON_CYAN, ha='left', va='top',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=self.theme.get_background_color(),
                             alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5), transform=fig.transFigure, zorder=100)
            if epoch:
                fig.text(0.98, 0.98, epoch, fontsize=10, color=self.theme.get_foreground_color(), ha='right', va='top', transform=fig.transFigure)

            row_labels = ['Absolute Power Z', 'Relative Power Z', 'Amplitude Asymmetry', 'Coherence', 'Phase Lag']
            for row_idx, row_label in enumerate(row_labels):
                for col_idx, band in enumerate(bands):
                    ax = axes[row_idx, col_idx]
                    band_display = {'hibeta': 'HiBeta', 'smr': 'SMR'}.get(band.lower(), band.capitalize())
                    freq = get_band_frequency_range(band) if get_band_frequency_range else None
                    band_part = f"{band_display} ({freq})" if freq else band_display
                    title = f"{band_part}\n{row_label}"
                    try:
                        if row_idx == 0:
                            ch_names, abs_vals = extract_band_values(metrics_by_site, band, epoch)
                            vals = self._zscore_values(np.array(abs_vals))
                            if len(ch_names) >= 4:
                                self._plot_topomap_cell(ax, vals, ch_names, title, is_zscore=True)
                            else:
                                ax.axis('off')
                                ax.set_title(title, fontsize=9, color=self.theme.get_foreground_color())
                        elif row_idx == 1:
                            ch_names, rel_vals = self._compute_relative_power(
                                metrics_by_site, band, epoch, bands_all_lower
                            )
                            vals = self._zscore_values(np.array(rel_vals))
                            if len(ch_names) >= 4:
                                self._plot_topomap_cell(ax, vals, ch_names, title, is_zscore=True)
                            else:
                                ax.axis('off')
                                ax.set_title(title, fontsize=9, color=self.theme.get_foreground_color())
                        elif row_idx == 2:
                            pairs = compute_asymmetry_pairs(
                                metrics_by_site, band, epoch, extract_band_values
                            )
                            if pairs:
                                opts = self.config.get('connectivity', {}) or {}
                                plot_connectivity_cell(ax, pairs, title, mode='asymmetry', theme=self.theme, options=opts if opts else None)
                            else:
                                ax.axis('off')
                                ax.set_title(title, fontsize=9, color=self.theme.get_foreground_color())
                        elif row_idx == 3 and has_coherence:
                            coh_pairs = get_coherence_pairs_for_band(
                                all_pairs, band, epoch, segments_info, max_pairs=10
                            )
                            if coh_pairs:
                                opts = self.config.get('connectivity', {}) or {}
                                plot_connectivity_cell(ax, coh_pairs, title, mode='coherence', theme=self.theme, options=opts if opts else None)
                            else:
                                ax.axis('off')
                                ax.set_title(title + "\n(no data)", fontsize=9, color=self.theme.get_foreground_color())
                        elif row_idx == 4 and has_phase_lag:
                            phase_pairs = get_phase_lag_pairs_for_band(
                                all_pairs_phase, band, epoch, segments_info, max_pairs=10
                            )
                            if phase_pairs:
                                opts = self.config.get('connectivity', {}) or {}
                                plot_connectivity_cell(ax, phase_pairs, title, mode='phase', theme=self.theme, options=opts if opts else None)
                            else:
                                ax.axis('off')
                                ax.set_title(title + "\n(no data)", fontsize=9, color=self.theme.get_foreground_color())
                        elif row_idx == 4:
                            ax.axis('off')
                            ax.set_title(title + "\n(phase lag)", fontsize=9, color=self.theme.get_foreground_color())
                        else:
                            ax.axis('off')
                            ax.set_title(title, fontsize=9, color=self.theme.get_foreground_color())
                    except Exception as e:
                        logger.debug("Z-score extended cell %s %s: %s", row_label, band, e)
                        ax.axis('off')
                        ax.set_title(title, fontsize=9, color=self.theme.get_foreground_color())

            plt.tight_layout()
            suffix = f"_{epoch.lower()}" if epoch else ""
            filename = f"topo_sheet_zscore_extended_5x5{suffix}.png"
            filepath = output_dir / filename
            fig.savefig(filepath, format='png', dpi=self.config.get('default_dpi', 150),
                       facecolor=self.theme.get_background_color(), bbox_inches='tight', pad_inches=0.1)
            plt.close(fig)
            paths[f"sheet_zscore_extended{suffix}"] = filepath
            logger.info("Generated Z-Score extended sheet: %s", filepath)

        return paths

    def generate_zscore_power_ratio_sheet(
        self,
        metrics_by_site: Dict[str, Any],
        norm_violations: Dict[str, Any],
        output_dir: Path,
        subject_id: str,
        session_id: str,
    ) -> Dict[str, Path]:
        """Generate Z-Score Power Ratio sheet: ratio topomaps (Delta/Theta, Delta/Alpha, Alpha/Beta, etc.)."""
        if not self.config.are_topomaps_enabled() or not self.config.get('topomaps.generate_z_scores', True):
            return {}
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        ratio_pairs = [
            ('delta', 'theta'), ('delta', 'alpha'), ('theta', 'alpha'),
            ('alpha', 'beta'), ('theta', 'beta'), ('delta', 'beta'),
        ]
        ratio_pairs = [(a, b) for a, b in ratio_pairs
                       if a in self.config.get_topomap_bands() and b in self.config.get_topomap_bands()]
        if len(ratio_pairs) < 2:
            return {}
        is_nested = is_nested_structure(metrics_by_site)
        epochs = get_all_available_epochs(metrics_by_site) if is_nested else [None]
        if not epochs:
            epochs = [None]
        n_cols = min(4, len(ratio_pairs))
        n_rows = int(np.ceil(len(ratio_pairs) / n_cols))

        for epoch in epochs:
            fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.2 * n_cols, 3.0 * n_rows),
                                    facecolor=self.theme.get_background_color())
            fig.patch.set_facecolor(self.theme.get_background_color())
            fig.text(0.02, 0.98, "EEG Paradox Decoder - Z-Score Power Ratio Sheet",
                    fontsize=11, fontweight='bold', color=self.theme.NEON_CYAN, ha='left', va='top',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=self.theme.get_background_color(),
                             alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5), transform=fig.transFigure, zorder=100)
            if epoch:
                fig.text(0.98, 0.98, epoch, fontsize=10, color=self.theme.get_foreground_color(), ha='right', va='top', transform=fig.transFigure)

            if n_rows == 1:
                axes = axes.reshape(1, -1)
            flat_axes = axes.flatten()
            for idx, (b1, b2) in enumerate(ratio_pairs):
                ax = flat_axes[idx]
                ch1, v1 = extract_band_values(metrics_by_site, b1, epoch)
                ch2, v2 = extract_band_values(metrics_by_site, b2, epoch)
                ch_names = ch1 if len(ch1) >= len(ch2) else ch2
                v1_arr = np.array(v1, dtype=float)
                v2_arr = np.array(v2, dtype=float)
                ch_to_v1 = {c: v for c, v in zip(ch1, v1_arr)} if ch1 else {}
                ch_to_v2 = {c: v for c, v in zip(ch2, v2_arr)} if ch2 else {}
                ratio_vals = np.array([
                    ch_to_v1.get(c, 1e-12) / (ch_to_v2.get(c, 1e-12) + 1e-12)
                    for c in ch_names
                ])
                ratio_vals = np.nan_to_num(ratio_vals, nan=1.0, posinf=1.0, neginf=1.0)
                ratio_vals = self._zscore_values(ratio_vals)
                b1d = {'hibeta': 'HiBeta', 'smr': 'SMR'}.get(b1.lower(), b1.capitalize())
                b2d = {'hibeta': 'HiBeta', 'smr': 'SMR'}.get(b2.lower(), b2.capitalize())
                f1 = get_band_frequency_range(b1) if get_band_frequency_range else None
                f2 = get_band_frequency_range(b2) if get_band_frequency_range else None
                range_part = f" ({f1} / {f2})" if (f1 and f2) else ""
                title = f"{b1d}/{b2d}{range_part}\nZ-Score Ratio"
                if len(ch_names) >= 4:
                    self._plot_topomap_cell(ax, ratio_vals, ch_names, title, is_zscore=True)
                else:
                    ax.axis('off')
                    ax.set_title(title, fontsize=10, color=self.theme.get_foreground_color())
            for idx in range(len(ratio_pairs), len(flat_axes)):
                flat_axes[idx].axis('off')

            plt.tight_layout()
            suffix = f"_{epoch.lower()}" if epoch else ""
            filename = f"topo_sheet_zscore_ratio{suffix}.png"
            filepath = output_dir / filename
            fig.savefig(filepath, format='png', dpi=self.config.get('default_dpi', 150),
                       facecolor=self.theme.get_background_color(), bbox_inches='tight', pad_inches=0.1)
            plt.close(fig)
            paths[f"sheet_zscore_ratio{suffix}"] = filepath
            logger.info("Generated Z-Score power ratio sheet: %s", filepath)

        return paths

    def generate_bandpower_sheet(
        self,
        metrics_by_site: Dict[str, Any],
        output_dir: Path,
        subject_id: str,
        session_id: str,
    ) -> Dict[str, Path]:
        """Generate Band Power sheet: bands as columns, EO/EC as rows if both present."""
        if not self.config.are_topomaps_enabled():
            return {}
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        bands = [b for b in self.config.get_topomap_bands() if b in self._sheet_bands_all]
        if len(bands) < 2:
            return {}
        is_nested = is_nested_structure(metrics_by_site)
        epochs = get_all_available_epochs(metrics_by_site) if is_nested else [None]
        if not epochs:
            epochs = [None]

        for epoch in epochs:
            n_cols = len(bands)
            n_rows = 1
            fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.2 * n_cols, 3.5),
                                    facecolor=self.theme.get_background_color())
            fig.patch.set_facecolor(self.theme.get_background_color())
            fig.text(0.02, 0.98, "EEG Paradox Decoder - Band Power Sheet",
                    fontsize=11, fontweight='bold', color=self.theme.NEON_CYAN, ha='left', va='top',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=self.theme.get_background_color(),
                             alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5), transform=fig.transFigure, zorder=100)
            if epoch:
                fig.text(0.98, 0.98, epoch, fontsize=10, color=self.theme.get_foreground_color(), ha='right', va='top', transform=fig.transFigure)

            if n_cols == 1:
                axes = [axes]
            for col_idx, band in enumerate(bands):
                ax = axes[col_idx]
                ch_names, values = extract_band_values(metrics_by_site, band, epoch)
                band_display = {'hibeta': 'HiBeta', 'smr': 'SMR'}.get(band.lower(), band.capitalize())
                freq = get_band_frequency_range(band) if get_band_frequency_range else None
                band_part = f"{band_display} ({freq})" if freq else band_display
                title = f"{band_part}\nBand Power"
                self._plot_topomap_cell(ax, np.array(values), ch_names, title, is_zscore=False)

            plt.tight_layout()
            suffix = f"_{epoch.lower()}" if epoch else ""
            filename = f"topo_sheet_bandpower{suffix}.png"
            filepath = output_dir / filename
            fig.savefig(filepath, format='png', dpi=self.config.get('default_dpi', 150),
                       facecolor=self.theme.get_background_color(), bbox_inches='tight', pad_inches=0.1)
            plt.close(fig)
            key = f"sheet_bandpower{suffix}"
            paths[key] = filepath
            logger.info("Generated Band Power sheet: %s", filepath)

        return paths

    def generate_absolute_sheet(
        self,
        metrics_by_site: Dict[str, Any],
        output_dir: Path,
        subject_id: str,
        session_id: str,
    ) -> Dict[str, Path]:
        """Generate Absolute Power sheet: bands as columns."""
        if not self.config.are_topomaps_enabled():
            return {}
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        bands = [b for b in self.config.get_topomap_bands() if b in self._sheet_bands_all]
        if len(bands) < 2:
            return {}
        is_nested = is_nested_structure(metrics_by_site)
        epochs = get_all_available_epochs(metrics_by_site) if is_nested else [None]
        if not epochs:
            epochs = [None]

        for epoch in epochs:
            n_cols = len(bands)
            fig, axes = plt.subplots(1, n_cols, figsize=(3.2 * n_cols, 3.5), facecolor=self.theme.get_background_color())
            fig.patch.set_facecolor(self.theme.get_background_color())
            fig.text(0.02, 0.98, "EEG Paradox Decoder - Absolute Power Sheet",
                    fontsize=11, fontweight='bold', color=self.theme.NEON_CYAN, ha='left', va='top',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=self.theme.get_background_color(),
                             alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5), transform=fig.transFigure, zorder=100)
            if epoch:
                fig.text(0.98, 0.98, epoch, fontsize=10, color=self.theme.get_foreground_color(), ha='right', va='top', transform=fig.transFigure)

            if n_cols == 1:
                axes = [axes]
            for col_idx, band in enumerate(bands):
                ch_names, values = extract_band_values(metrics_by_site, band, epoch)
                band_display = {'hibeta': 'HiBeta', 'smr': 'SMR'}.get(band.lower(), band.capitalize())
                freq = get_band_frequency_range(band) if get_band_frequency_range else None
                band_part = f"{band_display} ({freq})" if freq else band_display
                title = f"{band_part}\nAbsolute Power"
                self._plot_topomap_cell(axes[col_idx], np.array(values), ch_names, title, is_zscore=False)

            plt.tight_layout()
            suffix = f"_{epoch.lower()}" if epoch else ""
            filename = f"topo_sheet_absolute{suffix}.png"
            filepath = output_dir / filename
            fig.savefig(filepath, format='png', dpi=self.config.get('default_dpi', 150),
                       facecolor=self.theme.get_background_color(), bbox_inches='tight', pad_inches=0.1)
            plt.close(fig)
            paths[f"sheet_absolute{suffix}"] = filepath

        return paths

    def generate_relative_sheet(
        self,
        metrics_by_site: Dict[str, Any],
        output_dir: Path,
        subject_id: str,
        session_id: str,
    ) -> Dict[str, Path]:
        """Generate Relative Power sheet: bands as columns."""
        if not self.config.are_topomaps_enabled():
            return {}
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        bands = [b for b in self.config.get_topomap_bands() if b in self._sheet_bands_all]
        if len(bands) < 2:
            return {}
        bands_all = ['delta', 'theta', 'alpha', 'smr', 'beta', 'hibeta', 'gamma']
        is_nested = is_nested_structure(metrics_by_site)
        epochs = get_all_available_epochs(metrics_by_site) if is_nested else [None]
        if not epochs:
            epochs = [None]

        for epoch in epochs:
            n_cols = len(bands)
            fig, axes = plt.subplots(1, n_cols, figsize=(3.2 * n_cols, 3.5), facecolor=self.theme.get_background_color())
            fig.patch.set_facecolor(self.theme.get_background_color())
            fig.text(0.02, 0.98, "EEG Paradox Decoder - Relative Power Sheet",
                    fontsize=11, fontweight='bold', color=self.theme.NEON_CYAN, ha='left', va='top',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=self.theme.get_background_color(),
                             alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5), transform=fig.transFigure, zorder=100)
            if epoch:
                fig.text(0.98, 0.98, epoch, fontsize=10, color=self.theme.get_foreground_color(), ha='right', va='top', transform=fig.transFigure)

            if n_cols == 1:
                axes = [axes]
            for col_idx, band in enumerate(bands):
                ch_names, values = self._compute_relative_power(metrics_by_site, band, epoch, bands_all)
                band_display = {'hibeta': 'HiBeta', 'smr': 'SMR'}.get(band.lower(), band.capitalize())
                freq = get_band_frequency_range(band) if get_band_frequency_range else None
                band_part = f"{band_display} ({freq})" if freq else band_display
                title = f"{band_part}\nRelative Power"
                self._plot_topomap_cell(axes[col_idx], np.array(values), ch_names, title, is_zscore=False)

            plt.tight_layout()
            suffix = f"_{epoch.lower()}" if epoch else ""
            filename = f"topo_sheet_relative{suffix}.png"
            filepath = output_dir / filename
            fig.savefig(filepath, format='png', dpi=self.config.get('default_dpi', 150),
                       facecolor=self.theme.get_background_color(), bbox_inches='tight', pad_inches=0.1)
            plt.close(fig)
            paths[f"sheet_relative{suffix}"] = filepath

        return paths

    def generate_diff_sheet(
        self,
        metrics_by_site: Dict[str, Any],
        output_dir: Path,
        subject_id: str,
        session_id: str,
    ) -> Dict[str, Path]:
        """Generate Difference (EO-EC) sheet when both EO and EC are present."""
        if not self.config.are_topomaps_enabled():
            return {}
        is_nested = is_nested_structure(metrics_by_site)
        epochs = get_all_available_epochs(metrics_by_site) if is_nested else []
        if 'EO' not in epochs or 'EC' not in epochs:
            return {}
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        bands = [b for b in self.config.get_topomap_bands() if b in self._sheet_bands_all]
        if len(bands) < 2:
            return {}

        n_cols = len(bands)
        fig, axes = plt.subplots(1, n_cols, figsize=(3.2 * n_cols, 3.5), facecolor=self.theme.get_background_color())
        fig.patch.set_facecolor(self.theme.get_background_color())
        fig.text(0.02, 0.98, "EEG Paradox Decoder - Difference Sheet (EO − EC)",
                fontsize=11, fontweight='bold', color=self.theme.NEON_CYAN, ha='left', va='top',
                bbox=dict(boxstyle='round,pad=0.3', facecolor=self.theme.get_background_color(),
                         alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5), transform=fig.transFigure, zorder=100)

        if n_cols == 1:
            axes = [axes]
        for col_idx, band in enumerate(bands):
            ch_eo, val_eo = extract_band_values(metrics_by_site, band, 'EO')
            ch_ec, val_ec = extract_band_values(metrics_by_site, band, 'EC')
            ch_names = ch_eo if len(ch_eo) >= len(ch_ec) else ch_ec
            val_eo = np.array(val_eo)
            val_ec = np.array(val_ec)
            ch_to_eo = {c: v for c, v in zip(ch_eo, val_eo)} if ch_eo else {}
            ch_to_ec = {c: v for c, v in zip(ch_ec, val_ec)} if ch_ec else {}
            diff_vals = np.array([ch_to_eo.get(c, 0) - ch_to_ec.get(c, 0) for c in ch_names])
            band_display = {'hibeta': 'HiBeta', 'smr': 'SMR'}.get(band.lower(), band.capitalize())
            freq = get_band_frequency_range(band) if get_band_frequency_range else None
            band_part = f"{band_display} ({freq})" if freq else band_display
            title = f"{band_part}\nEO − EC"
            self._plot_topomap_cell(axes[col_idx], diff_vals, ch_names, title, is_zscore=False)

        plt.tight_layout()
        filename = "topo_sheet_diff.png"
        filepath = output_dir / filename
        fig.savefig(filepath, format='png', dpi=self.config.get('default_dpi', 150),
                   facecolor=self.theme.get_background_color(), bbox_inches='tight', pad_inches=0.1)
        plt.close(fig)
        paths["sheet_diff"] = filepath
        logger.info("Generated Difference sheet: %s", filepath)
        return paths

    def generate_all_sheets(
        self,
        metrics_by_site: Dict[str, Any],
        norm_violations: Dict[str, Any],
        output_dir: Path,
        subject_id: str,
        session_id: str,
        coherence_metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Path]:
        """Generate all topo sheets. Returns dict of key -> Path."""
        all_paths = {}
        coherence_metrics = coherence_metrics or {}
        bands_5 = [b for b in self._sheet_bands_summary if b in self.config.get_topomap_bands()]
        bands_all = [b for b in self.config.get_topomap_bands() if b in self._sheet_bands_all]
        is_nested = is_nested_structure(metrics_by_site)
        epochs_list = get_all_available_epochs(metrics_by_site) if is_nested else [None]
        if not epochs_list:
            epochs_list = [None]

        def _composite_fallback(pattern: str, bands: List[str], out_name: str, key_prefix: str) -> Dict[str, Path]:
            return self._composite_sheet_from_existing_images(
                output_dir, pattern, bands, epochs_list, out_name, key_prefix
            )

        if self.config.get('topomaps.topo_sheets.enabled', True):
            try:
                if self.config.get('topomaps.topo_sheets.zscore_summary', True) and self.config.get('topomaps.generate_z_scores', True):
                    p = self.generate_zscore_summary_sheet(
                        metrics_by_site, norm_violations, output_dir, subject_id, session_id
                    )
                    if not p and len(bands_5) >= 2:
                        p = _composite_fallback('topomap_zscore_{band}', bands_5, 'topo_sheet_zscore_summary_3x5', 'sheet_zscore_summary')
                    all_paths.update(p)
            except Exception as e:
                logger.warning("Z-Score summary sheet failed: %s", e)
            try:
                if self.config.get('topomaps.topo_sheets.zscore_extended', True) and self.config.get('topomaps.generate_z_scores', True):
                    p = self.generate_zscore_extended_sheet(
                        metrics_by_site, norm_violations, coherence_metrics,
                        output_dir, subject_id, session_id
                    )
                    if not p and len(bands_5) >= 2:
                        p = _composite_fallback('topomap_zscore_{band}', bands_5, 'topo_sheet_zscore_extended_5x5', 'sheet_zscore_extended')
                    all_paths.update(p)
            except Exception as e:
                logger.warning("Z-Score extended sheet failed: %s", e)
            try:
                if self.config.get('topomaps.topo_sheets.zscore_ratio', True) and self.config.get('topomaps.generate_z_scores', True):
                    p = self.generate_zscore_power_ratio_sheet(
                        metrics_by_site, norm_violations, output_dir, subject_id, session_id
                    )
                    all_paths.update(p)
            except Exception as e:
                logger.warning("Z-Score power ratio sheet failed: %s", e)
            try:
                if self.config.get('topomaps.topo_sheets.bandpower', True):
                    p = self.generate_bandpower_sheet(metrics_by_site, output_dir, subject_id, session_id)
                    if not p and len(bands_all) >= 2:
                        p = _composite_fallback('topomap_{band}', bands_all, 'topo_sheet_bandpower', 'sheet_bandpower')
                    all_paths.update(p)
            except Exception as e:
                logger.warning("Band Power sheet failed: %s", e)
            try:
                if self.config.get('topomaps.topo_sheets.absolute', True):
                    p = self.generate_absolute_sheet(metrics_by_site, output_dir, subject_id, session_id)
                    if not p and len(bands_all) >= 2:
                        p = _composite_fallback('topomap_{band}', bands_all, 'topo_sheet_absolute', 'sheet_absolute')
                    all_paths.update(p)
            except Exception as e:
                logger.warning("Absolute Power sheet failed: %s", e)
            try:
                if self.config.get('topomaps.topo_sheets.relative', True):
                    p = self.generate_relative_sheet(metrics_by_site, output_dir, subject_id, session_id)
                    if not p and len(bands_all) >= 2:
                        p = _composite_fallback('topomap_relative_{band}', bands_all, 'topo_sheet_relative', 'sheet_relative')
                    all_paths.update(p)
            except Exception as e:
                logger.warning("Relative Power sheet failed: %s", e)
            try:
                if self.config.get('topomaps.topo_sheets.diff', True):
                    p = self.generate_diff_sheet(metrics_by_site, output_dir, subject_id, session_id)
                    all_paths.update(p)
            except Exception as e:
                logger.warning("Difference sheet failed: %s", e)
        return all_paths
