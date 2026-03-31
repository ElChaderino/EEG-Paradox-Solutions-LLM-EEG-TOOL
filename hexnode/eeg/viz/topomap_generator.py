#!/usr/bin/env python3
"""
Topomap Generator

Generates topographical brain maps for EEG analysis with support for
all frequency bands and z-score visualizations.

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
import pickle
import matplotlib
matplotlib.use('Agg')  # Non-GUI backend for thread-safe/server use (avoids Qt main-thread warnings)
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
import mne
from scipy.interpolate import griddata
from scipy.spatial.distance import cdist
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import logging
import base64

# Cache file for interpolated grids (palette-only regeneration skips interpolation)
_TOPOMAP_CACHE_FILENAME = ".topomap_interp_cache.pkl"

from hexnode.eeg.viz.theme_manager import get_theme_manager, CLINICAL_1020_POSITIONS
from hexnode.eeg.viz.visualization_config import get_visualization_config
from hexnode.eeg.viz.band_definitions import get_band_definitions, get_band_frequency_range_str
from hexnode.eeg.viz.utils import (
    clean_channel_name, is_nested_structure, extract_band_values,
    extract_band_instability, extract_all_sites, get_epochs_for_site,
    get_all_available_epochs, remove_overlapping_channels,
    format_qc_callout_plain,
)

logger = logging.getLogger(__name__)


def _power_topomap_colormap():
    """Sequential map for non-negative band power: visible on dark UI (viridis low end matched bg)."""
    try:
        return matplotlib.colormaps["turbo"]
    except (AttributeError, KeyError, TypeError):
        return plt.get_cmap("turbo")


def _expand_topomap_vlim_for_grid(
    vmin: float,
    vmax: float,
    Zi: np.ndarray,
    *,
    is_zscore: bool,
    zmin: float = -3.0,
    zmax: float = 3.0,
) -> tuple[float, float]:
    """Widen color limits to cover the interpolated field so contourf does not clip to one colormap end."""
    z = np.asarray(Zi, dtype=float)
    z = z[np.isfinite(z)]
    if z.size == 0:
        return vmin, vmax
    pcts = np.percentile(z, [2, 98])
    gz_lo, gz_hi = float(pcts[0]), float(pcts[1])
    if is_zscore:
        lo = min(float(zmin), float(vmin), gz_lo)
        hi = max(float(zmax), float(vmax), gz_hi)
        m = max(abs(lo), abs(hi), 1e-6)
        return -m, m
    lo = min(float(vmin), gz_lo)
    hi = max(float(vmax), gz_hi)
    if hi <= lo:
        hi = lo + 1e-12
    return lo, hi

def get_band_frequency_range(band: str, definitions: Optional[Dict[str, Tuple[float, float]]] = None) -> str:
    """
    Get frequency range string for a band (e.g., "4-8 Hz").
    Uses shared band_definitions; pass definitions for config-driven ranges.
    """
    return get_band_frequency_range_str(band, definitions)


class TopomapGenerator:
    """Generates topographical brain maps for EEG data"""
    
    def __init__(self, config=None):
        """
        Initialize topomap generator
        
        Args:
            config: VisualizationConfig instance (optional)
        """
        self.config = config or get_visualization_config()
        self.theme = get_theme_manager()
        # Z-score topomap color range from config (align with z_score_severity or keep ±3 for full range)
        zrange = self.config.get('topomaps.zscore_vmin_vmax', [-3.0, 3.0])
        if isinstance(zrange, (list, tuple)) and len(zrange) >= 2:
            self._zscore_vmin, self._zscore_vmax = float(zrange[0]), float(zrange[1])
        else:
            self._zscore_vmin, self._zscore_vmax = -3.0, 3.0
        self._band_ranges = get_band_definitions(self.config)

        # Initialize clinical interpretation database
        self._init_clinical_interpretations()
    
    def _clinical_interpolation(self, values: np.ndarray, positions: np.ndarray, 
                               resolution: int = 300) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        High-quality clinical interpolation matching NeuroGuide standards
        Uses higher resolution and Gaussian smoothing for smoother, more accurate topomaps
        
        Args:
            values: Array of values per channel
            positions: Array of (x, y) positions per channel
            resolution: Grid resolution (default 300 for high-res output)
            
        Returns:
            Tuple of (Xi, Yi, Zi) meshgrid arrays
        """
        # scipy griddata (cubic/linear) requires at least 4 points for Delaunay triangulation
        n_points = len(positions) if hasattr(positions, '__len__') else positions.shape[0]
        if n_points < 4:
            raise ValueError(
                f"Insufficient channels for topomap interpolation (have {n_points}, need at least 4). "
                "Single-site protocols (e.g. site_7) produce 1 channel; topomaps require multi-channel data."
            )

        # Check data sparsity before interpolation
        non_zero_count = np.sum(values != 0.0)
        non_zero_ratio = non_zero_count / len(values) if len(values) > 0 else 0
        
        # Create grid that matches axis limits and head outline
        # Grid extends to ±1.3 for interpolation buffer, but head circle is radius 1.0
        head_radius = 1.0
        grid_extent = 1.3  # Buffer for interpolation
        xi = np.linspace(-grid_extent, grid_extent, resolution)
        yi = np.linspace(-grid_extent, grid_extent, resolution)
        Xi, Yi = np.meshgrid(xi, yi)
        
        # Interpolate using cubic method (with fallback to linear for edge cases)
        Zi = griddata(positions, values, (Xi, Yi), method='cubic', fill_value=np.nan)
        
        # If cubic interpolation produces too many NaNs (especially near edges), use linear
        nan_ratio = np.sum(np.isnan(Zi)) / Zi.size if Zi.size > 0 else 0
        if nan_ratio > 0.3:  # More than 30% NaN suggests edge channel issues
            logger.debug(f"High NaN ratio ({nan_ratio:.2%}), using linear interpolation for better edge handling")
            Zi = griddata(positions, values, (Xi, Yi), method='linear', fill_value=np.nan)
        
        # Create circular mask (clinical head shape) - match head outline radius exactly (1.0)
        # T7 and T8 are at distance ~0.999, so they're just inside the head circle
        # P7 and P8 are at distance ~0.775, well within the circle
        head_mask = np.sqrt(Xi**2 + Yi**2) <= head_radius
        
        # Fill NaN values using nearest neighbor extrapolation (important for edge channels).
        if np.any(np.isnan(Zi)) and non_zero_count >= 3:
            nan_mask = np.isnan(Zi)
            if np.any(nan_mask):
                # Get coordinates of NaN positions (flattened for cdist)
                nan_coords = np.column_stack([Xi[nan_mask], Yi[nan_mask]])
                distances = cdist(nan_coords, positions)
                nearest_indices = np.argmin(distances, axis=1)
                nearest_values = values[nearest_indices]
                
                # Fill every NaN from nearest electrode (zeros are valid, e.g. relative band power)
                should_fill = np.ones(len(nearest_values), dtype=bool)
                
                if np.any(should_fill):
                    # Get coordinates of NaN positions that should be filled
                    fill_coords = nan_coords[should_fill]
                    fill_distances = cdist(fill_coords, positions)
                    fill_nearest = np.argmin(fill_distances, axis=1)
                    
                    # Create a flat array to fill, then reshape back to 2D
                    fill_values = values[fill_nearest]
                    
                    # Map back to 2D positions
                    # Find the indices in the flattened nan_mask where we should fill
                    nan_flat_indices = np.where(nan_mask.ravel())[0]
                    fill_flat_indices = nan_flat_indices[should_fill]
                    
                    # Fill in the flattened array, then reshape
                    Zi_flat = Zi.ravel()
                    Zi_flat[fill_flat_indices] = fill_values
                    Zi = Zi_flat.reshape(Zi.shape)
        elif non_zero_count < 3:
            logger.debug(f"Too few non-zero channels ({non_zero_count}), keeping NaNs to avoid misleading interpolation")
        
        # Apply Gaussian smoothing for smoother contours (reduces sharp edges)
        # CRITICAL: Don't let zeros leak into smoothing - use masked smoothing
        from scipy.ndimage import gaussian_filter
        
        # Create a mask for valid (non-NaN) data within the head
        valid_mask = head_mask & ~np.isnan(Zi)
        
        if np.any(valid_mask):
            # Use finite in-head count (relative power can be mostly zeros but still valid)
            n_finite_valid = int(np.sum(valid_mask))
            
            if n_finite_valid > 10:
                # Create smoothed array, preserving structure
                Zi_smoothed = Zi.copy()
                
                # Neutral fill outside valid_mask for the gaussian kernel (mean of in-head field)
                finite_vals = Zi[valid_mask]
                neutral_value = float(np.mean(finite_vals)) if finite_vals.size else 0.0
                if not np.isfinite(neutral_value):
                    neutral_value = 0.0
                
                Zi_for_smoothing = np.where(valid_mask, Zi, neutral_value)
                
                # Apply Gaussian filter
                Zi_smoothed = gaussian_filter(Zi_for_smoothing, sigma=1.5)
                
                # Restore NaN outside head
                Zi_smoothed[~head_mask] = np.nan
                
                # For regions that were originally NaN within head, restore them
                # (don't fill with smoothed values from neutral fill)
                original_nan = np.isnan(Zi) & head_mask
                if np.any(original_nan):
                    Zi_smoothed[original_nan] = np.nan
                    # Only fill if we have enough non-zero data
                    if non_zero_count >= 3:
                        # Get coordinates of original NaN positions (flattened for cdist)
                        original_nan_coords = np.column_stack([Xi[original_nan], Yi[original_nan]])
                        distances = cdist(original_nan_coords, positions)
                        nearest_indices = np.argmin(distances, axis=1)
                        nearest_values = values[nearest_indices]
                        should_fill_original = np.ones(len(nearest_values), dtype=bool)
                        if np.any(should_fill_original):
                            fill_coords = original_nan_coords[should_fill_original]
                            fill_distances = cdist(fill_coords, positions)
                            fill_nearest = np.argmin(fill_distances, axis=1)
                            fill_values = values[fill_nearest]
                            
                            # Map back to 2D positions
                            original_nan_flat_indices = np.where(original_nan.ravel())[0]
                            fill_flat_indices = original_nan_flat_indices[should_fill_original]
                            
                            # Fill in the flattened array, then reshape
                            Zi_smoothed_flat = Zi_smoothed.ravel()
                            Zi_smoothed_flat[fill_flat_indices] = fill_values
                            Zi_smoothed = Zi_smoothed_flat.reshape(Zi_smoothed.shape)
                
                Zi = Zi_smoothed
            else:
                logger.debug(
                    f"Too sparse for smoothing ({n_finite_valid} finite in-head points), skipping Gaussian filter"
                )
                Zi[~head_mask] = np.nan
        else:
            # No valid data, keep original
            Zi[~head_mask] = np.nan
        
        # matplotlib contourf does not shade NaN cells → blank "hole" topomaps on dark background.
        # Patch any remaining non-finite samples inside the head from nearest-neighbor field.
        mean_v = float(np.mean(values)) if len(values) else 0.0
        if not np.isfinite(mean_v):
            mean_v = 0.0
        Zi_nn = griddata(
            positions, values, (Xi, Yi), method="nearest", fill_value=mean_v
        )
        in_head_hole = head_mask & ~np.isfinite(Zi)
        if np.any(in_head_hole):
            Zi = np.where(in_head_hole, Zi_nn, Zi)

        # Final mask application
        Zi[~head_mask] = np.nan
        
        return Xi, Yi, Zi
    
    def _get_channel_positions(self, channel_names: List[str]) -> Tuple[np.ndarray, List[str]]:
        """
        Get clinical 10-20 positions for channels
        
        Args:
            channel_names: List of channel names
            
        Returns:
            Tuple of (positions_array, valid_channels_list)
        """
        positions = []
        valid_channels = []
        
        for ch in channel_names:
            clean_ch = clean_channel_name(ch)
            if clean_ch in CLINICAL_1020_POSITIONS:
                positions.append(CLINICAL_1020_POSITIONS[clean_ch])
                valid_channels.append(clean_ch)
            else:
                # Estimate position
                pos = self.theme._estimate_position(clean_ch)
                positions.append(pos)
                valid_channels.append(clean_ch)
        
        return np.array(positions), valid_channels
    
    def _resolve_epochs(self, metrics_by_site: Dict[str, Any]) -> List[Optional[str]]:
        """Return the list of epochs to iterate (handles nested vs flat)."""
        if is_nested_structure(metrics_by_site):
            epochs = get_all_available_epochs(metrics_by_site)
            return epochs if epochs else [None]
        return [None]

    def _iter_band_epochs(self, metrics_by_site: Dict[str, Any], output_dir: Path,
                         bands: Optional[List[str]] = None):
        """
        Yield (band, epoch, channel_names, values, positions, valid_channels)
        for every band x epoch combination that has plottable data.

        Centralises the config check, mkdir, nested/flat detection, epoch
        discovery, value extraction, zero-check, and position lookup that
        many generate_* methods duplicate.
        """
        if not self.config.are_topomaps_enabled():
            return
        output_dir.mkdir(parents=True, exist_ok=True)
        if bands is None:
            bands = self.config.get_topomap_bands()
        for epoch in self._resolve_epochs(metrics_by_site):
            for band in bands:
                channel_names, values = extract_band_values(metrics_by_site, band, epoch)
                if len(channel_names) == 0:
                    continue
                max_val = float(np.max(values)) if len(values) > 0 else 0.0
                if max_val <= 0:
                    continue
                positions, valid_channels = self._get_channel_positions(channel_names)
                if len(positions) == 0:
                    continue
                yield band, epoch, channel_names, values, positions, valid_channels

    def _get_interp_cache_path(self, cache_dir: Path) -> Path:
        """Path to interpolation cache file."""
        return cache_dir / _TOPOMAP_CACHE_FILENAME
    
    def _load_interp_cache(self, cache_dir: Path) -> Dict[str, Dict]:
        """Load interpolation cache if it exists (pickle). On corrupt/non-pickle file, remove and return empty."""
        p = self._get_interp_cache_path(cache_dir)
        if not p.exists():
            return {}
        try:
            with open(p, 'rb') as f:
                return pickle.load(f)
        except (UnicodeDecodeError, ValueError, pickle.UnpicklingError) as e:
            logger.warning("Topomap cache invalid or corrupted (%s), skipping: %s", type(e).__name__, e)
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
            return {}
        except Exception as e:
            logger.warning("Could not load topomap cache: %s", e)
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
            return {}
    
    def _save_interp_cache(self, cache_dir: Path, cache: Dict[str, Dict]) -> None:
        """Save interpolation cache."""
        try:
            p = self._get_interp_cache_path(cache_dir)
            with open(p, 'wb') as f:
                pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            logger.warning("Could not save topomap cache: %s", e)
    
    def _render_from_grid_entry(self, entry: Dict[str, Any]) -> Optional[plt.Figure]:
        """Render a topomap from cached grid data. Uses current theme colormap (palette)."""
        try:
            Xi = entry['Xi']
            Yi = entry['Yi']
            Zi = entry['Zi']
            vmin = entry['vmin']
            vmax = entry['vmax']
            positions = entry['positions']
            valid_channels = entry['valid_channels']
            values = entry['values']
            is_zscore = entry.get('is_zscore', False)
            title = entry.get('title', '')
            frequency_band = entry.get('frequency_band', '')
            condition = entry.get('condition', '')
            unit_label = entry.get('unit_label')
            vmin, vmax = _expand_topomap_vlim_for_grid(
                vmin, vmax, Zi, is_zscore=is_zscore,
                zmin=self._zscore_vmin, zmax=self._zscore_vmax,
            )
            cmap = (
                self.theme.get_diverging_colormap()
                if is_zscore
                else _power_topomap_colormap()
            )
            if vmax <= vmin:
                vals = np.asarray(values, dtype=float)
                mag = max(float(np.percentile(np.abs(vals), 95)), float(np.max(np.abs(vals))), 1e-30)
                vmax = vmin + max(mag * 0.02, 1e-30)
            levels = np.linspace(vmin, vmax, 64)
            levels = np.unique(levels)
            if len(levels) < 2:
                levels = np.array([vmin, vmax])
            fig, ax = plt.subplots(figsize=(12, 10), facecolor=self.theme.get_background_color())
            ax.set_facecolor(self.theme.get_background_color())
            grid_extent = 1.3
            ax.set_xlim(-grid_extent, grid_extent)
            ax.set_ylim(-grid_extent, grid_extent)
            ax.set_aspect('equal')
            ax.axis('off')
            plt.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.05)
            contour_filled = ax.contourf(Xi, Yi, Zi, levels=levels, cmap=cmap, vmin=vmin, vmax=vmax, extend='both', zorder=1)
            if self.config.get('topomaps.show_contours', True):
                contour_levels = np.linspace(vmin, vmax, 12)
                contour_color = '#aaaaaa' if is_zscore else '#1a2a44'
                ax.contour(Xi, Yi, Zi, levels=contour_levels, colors=contour_color,
                          linewidths=0.4, alpha=0.4, zorder=4)
            head_circle = plt.Circle((0, 0), 1.0, fill=False, color=self.theme.NEON_CYAN, linewidth=1.8, alpha=0.8, zorder=3)
            ax.add_patch(head_circle)
            ax.plot([0, -0.1, 0.1, 0], [1.0, 1.15, 1.15, 1.0], color=self.theme.NEON_CYAN, linewidth=1.8, alpha=0.8, zorder=3)
            for sx in (-1.0, 1.0):
                ear = plt.Circle((sx, 0), 0.10, fill=False, color=self.theme.NEON_CYAN, linewidth=1.4, alpha=0.8, zorder=3)
                ax.add_patch(ear)
            marker_sizes = [42 if np.sqrt(p[0]**2 + p[1]**2) > 0.8 else 36 for p in positions]
            ax.scatter(positions[:, 0], positions[:, 1], c=self.theme.get_foreground_color(),
                      s=marker_sizes, edgecolors=self.theme.get_background_color(), linewidths=0.8, zorder=10, alpha=0.85)
            for i, (pos, ch) in enumerate(zip(positions, valid_channels)):
                color = self.theme.get_severity_color(values[i]) if is_zscore else self.theme.get_region_color(ch)
                dist = np.sqrt(pos[0]**2 + pos[1]**2)
                label_offset = -0.12 if dist > 0.8 else -0.08
                ha = ('right' if pos[0] < 0 else 'left') if abs(pos[0]) > 0.8 else 'center'
                ax.text(pos[0], pos[1] + label_offset, ch, ha=ha, va='top', color=color, fontsize=10, fontweight='bold', zorder=11)
            cbar = ax.get_figure().colorbar(contour_filled, ax=ax, shrink=0.84, aspect=28, pad=0.02)
            txt_color = self.theme.get_foreground_color()
            cbar.ax.tick_params(colors=txt_color, labelsize=11)
            cbar.outline.set_edgecolor(self.theme.NEON_CYAN)
            cbar.outline.set_linewidth(1.5)
            ul = unit_label or ('Z-Score' if is_zscore else 'Power (µV²)')
            if frequency_band:
                fr = get_band_frequency_range(frequency_band, self._band_ranges)
                if fr:
                    ul += f" ({fr})"
            cbar.set_label(ul, color=txt_color, fontsize=13, fontweight='bold', labelpad=10)
            if frequency_band or condition:
                label_text = (frequency_band or '') + (f" - {condition}" if condition else '')
                ax.text(-1.2, 1.0, label_text, fontsize=12, fontweight='bold', color=txt_color, ha='left', va='top',
                       bbox=dict(boxstyle='round,pad=0.3', facecolor=self.theme.get_background_color(),
                               alpha=0.8, edgecolor=txt_color, linewidth=1), zorder=10)
            ax.text(-1.2, 1.25, "EEG Paradox Decoder Topo Generator", fontsize=10, fontweight='bold',
                   color=self.theme.NEON_CYAN, ha='left', va='top',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor=self.theme.get_background_color(),
                           alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5), zorder=12)
            enhanced_title = f"{title}\n{frequency_band} - {condition}" if (frequency_band and condition) else (f"{title}\n{frequency_band}" if frequency_band else (f"{title}\n{condition}" if condition else title))
            ax.set_title(enhanced_title, color=txt_color, fontsize=18, fontweight='bold', pad=18)
            plt.tight_layout()
            return fig
        except Exception as e:
            logger.error("Error rendering from cache: %s", e, exc_info=True)
            return None
    
    def _plot_topomap(self, values: np.ndarray, channel_names: List[str],
                     title: str, is_zscore: bool = False,
                     frequency_band: str = '', condition: str = '',
                     unit_label: Optional[str] = None,
                     return_cache_entry: bool = False) -> Optional[plt.Figure]:
        """
        Plot a clinical-grade topomap
        
        Args:
            values: Array of values per channel
            channel_names: List of channel names
            title: Plot title
            is_zscore: Whether values are z-scores
            frequency_band: Frequency band label
            condition: Condition label (EC/EO)
            
        Returns:
            Matplotlib figure or None
        """
        try:
            # Get positions
            positions, valid_channels = self._get_channel_positions(channel_names)
            
            if len(positions) == 0:
                logger.warning("No valid channel positions found")
                return None
            
            # Ensure values match channels - critical validation
            # Create a mapping from cleaned channel names to original channel names
            # This handles case mismatches (e.g., "CZ" vs "Cz")
            channel_name_map = {}
            for orig_name in channel_names:
                cleaned = clean_channel_name(orig_name)
                # If multiple original names map to same cleaned name, use first one
                if cleaned not in channel_name_map:
                    channel_name_map[cleaned] = orig_name
            
            if len(values) != len(channel_names):
                logger.warning(f"Values length ({len(values)}) doesn't match channel_names length ({len(channel_names)})")
                # Try to match by channel name
                matched_values = []
                problematic_sites = ['Oz', 'Cz', 'Pz', 'Fz', 'OZ', 'CZ', 'PZ', 'FZ']
                for ch in valid_channels:
                    # Try to find the original channel name that maps to this cleaned name
                    orig_name = channel_name_map.get(ch, ch)
                    is_problematic_ch = ch.upper() in [s.upper() for s in problematic_sites]
                    matched = False
                    
                    if orig_name in channel_names:
                        idx = channel_names.index(orig_name)
                        if idx < len(values):
                            matched_values.append(values[idx])
                            matched = True
                            if is_problematic_ch:
                                logger.debug(f"Individual topomap (len mismatch) {ch} -> {orig_name} (idx {idx}) = {values[idx]:.4f}")
                        else:
                            matched_values.append(0.0)
                            if is_problematic_ch:
                                logger.debug(f"Individual topomap (len mismatch) {ch} -> {orig_name} index {idx} out of range")
                    elif ch in channel_names:
                        # Also try direct match in case names are already cleaned
                        idx = channel_names.index(ch)
                        if idx < len(values):
                            matched_values.append(values[idx])
                            matched = True
                            if is_problematic_ch:
                                logger.debug(f"Individual topomap (len mismatch) {ch} direct match (idx {idx}) = {values[idx]:.4f}")
                        else:
                            matched_values.append(0.0)
                            if is_problematic_ch:
                                logger.debug(f"Individual topomap (len mismatch) {ch} direct match index {idx} out of range")
                    else:
                        # Final fallback: case-insensitive search
                        ch_upper = ch.upper()
                        for i, cn in enumerate(channel_names):
                            if cn.upper() == ch_upper:
                                if i < len(values):
                                    matched_values.append(values[i])
                                    matched = True
                                    if is_problematic_ch:
                                        logger.debug(f"Individual topomap (len mismatch) {ch} -> {cn} (case-insensitive, idx {i}) = {values[i]:.4f}")
                                break
                        
                        if not matched:
                            matched_values.append(0.0)
                            if is_problematic_ch:
                                logger.debug(f"Individual topomap (len mismatch) {ch} not found. Available: {channel_names[:15]}")
                values = np.array(matched_values, dtype=float)
            elif len(values) != len(valid_channels):
                # Values match channel_names but not valid_channels (some channels filtered out)
                matched_values = []
                problematic_sites = ['Oz', 'Cz', 'Pz', 'Fz', 'OZ', 'CZ', 'PZ', 'FZ']
                for ch in valid_channels:
                    # Try to find the original channel name that maps to this cleaned name
                    orig_name = channel_name_map.get(ch, ch)
                    is_problematic_ch = ch.upper() in [s.upper() for s in problematic_sites]
                    matched = False
                    
                    if orig_name in channel_names:
                        idx = channel_names.index(orig_name)
                        if idx < len(values):
                            matched_values.append(values[idx])
                            matched = True
                            if is_problematic_ch:
                                logger.debug(f"Individual topomap {ch} -> {orig_name} (idx {idx}) = {values[idx]:.4f}")
                        else:
                            matched_values.append(0.0)
                            if is_problematic_ch:
                                logger.debug(f"Individual topomap {ch} -> {orig_name} index {idx} out of range")
                    elif ch in channel_names:
                        # Also try direct match in case names are already cleaned
                        idx = channel_names.index(ch)
                        if idx < len(values):
                            matched_values.append(values[idx])
                            matched = True
                            if is_problematic_ch:
                                logger.debug(f"Individual topomap {ch} direct match (idx {idx}) = {values[idx]:.4f}")
                        else:
                            matched_values.append(0.0)
                            if is_problematic_ch:
                                logger.debug(f"Individual topomap {ch} direct match index {idx} out of range")
                    else:
                        # Final fallback: case-insensitive search
                        ch_upper = ch.upper()
                        for i, cn in enumerate(channel_names):
                            if cn.upper() == ch_upper:
                                if i < len(values):
                                    matched_values.append(values[i])
                                    matched = True
                                    if is_problematic_ch:
                                        logger.debug(f"Individual topomap {ch} -> {cn} (case-insensitive, idx {i}) = {values[i]:.4f}")
                                break
                        
                        if not matched:
                            matched_values.append(0.0)
                            if is_problematic_ch:
                                logger.debug(f"Individual topomap {ch} not found. Available: {channel_names[:15]}")
                values = np.array(matched_values, dtype=float)
            else:
                values = np.array(values, dtype=float)
            
            # Final validation: ensure positions and values match
            if len(values) != len(positions):
                logger.error(f"Critical mismatch: {len(values)} values but {len(positions)} positions after matching")
                return None
            
            logger.debug(f"Plotting topomap: {len(valid_channels)} channels, "
                        f"value range=[{np.min(values):.4f}, {np.max(values):.4f}], "
                        f"non-zero={np.sum(values != 0.0)}/{len(values)}")
            
            # Check for NaN values and replace with 0.0
            nan_count = np.sum(np.isnan(values))
            if nan_count > 0:
                logger.warning(f"Found {nan_count} NaN values in topomap data, replacing with 0.0")
                values = np.nan_to_num(values, nan=0.0)
            
            # Check for too many zeros (indicates missing data)
            zero_count = np.sum(values == 0.0)
            zero_ratio = zero_count / len(values) if len(values) > 0 else 1.0
            if zero_ratio > 0.5:  # More than 50% zeros
                min_val = np.min(values) if len(values) > 0 else 0.0
                max_val = np.max(values) if len(values) > 0 else 0.0
                logger.warning(f"High zero ratio ({zero_ratio:.1%}) in topomap data. "
                             f"Range: [{min_val:.4f}, {max_val:.4f}]. "
                             f"This may indicate missing channel data.")
            
            # Set color limits with consistent scaling
            if is_zscore:
                vmin, vmax = self._zscore_vmin, self._zscore_vmax
            else:
                # Check if data is sparse (many zeros)
                non_zero_values = values[values != 0.0]
                non_zero_ratio = len(non_zero_values) / len(values) if len(values) > 0 else 0
                
                if len(non_zero_values) > 0 and non_zero_ratio < 0.5:
                    # Sparse data: use actual range of non-zero values for better visibility
                    vmin = np.min(non_zero_values)
                    vmax = np.max(non_zero_values)
                    logger.debug(f"Sparse data ({non_zero_ratio:.1%} non-zero), using actual range [{vmin:.4f}, {vmax:.4f}]")
                else:
                    # Normal data: use 2nd and 98th percentiles to avoid outlier scaling
                    # This ensures consistent color scales across similar map types
                    vmin = np.percentile(values, 2)
                    vmax = np.percentile(values, 98)
                
                # Expand near-degenerate ranges. A fixed floor of 1e-6 breaks Welch band
                # power (~1e-12): all pixels map to the bottom of the colormap.
                rng = float(vmax - vmin)
                mag = max(float(np.percentile(np.abs(values), 95)), float(np.max(np.abs(values))), 1e-30)
                if not np.isfinite(rng) or rng <= 0:
                    vmin, vmax = float(np.min(values)), float(np.max(values))
                    rng = vmax - vmin
                if rng <= 0:
                    vmax = vmin + max(mag * 0.05, 1e-30)
                elif rng < mag * 1e-4:
                    vmin, vmax = float(np.min(values)), float(np.max(values))
                    rng = vmax - vmin
                    pad = max(rng * 0.3, mag * 0.04, 1e-30)
                    vmin, vmax = vmin - pad * 0.5, vmax + pad * 0.5
                elif rng < 1e-6:
                    vmax = vmin + max(rng, mag * 0.02)
            
            # Check data sparsity before interpolation
            non_zero_count = np.sum(values != 0.0)
            non_zero_ratio = non_zero_count / len(values) if len(values) > 0 else 0
            
            if non_zero_ratio < 0.1:  # Less than 10% of channels have data
                logger.warning(f"Too sparse data ({non_zero_ratio:.1%} non-zero, {non_zero_count}/{len(values)} channels), "
                             f"skipping topomap to avoid misleading visualization")
                return None

            # Topomap interpolation requires at least 4 channels (Delaunay triangulation)
            if len(positions) < 4:
                logger.debug(f"Skipping topomap: need at least 4 channels, have {len(positions)} (single-site/site_7 protocols)")
                return None
            
            # Perform interpolation with high resolution for smooth contours
            resolution = getattr(self.config, 'get_topomap_resolution', lambda: self.config.get('topomaps.resolution', 128))()
            Xi, Yi, Zi = self._clinical_interpolation(values, positions, resolution)
            
            # Create contour plot with smoother, more levels for high-res output
            if vmax <= vmin:
                mag = max(float(np.max(np.abs(values))), 1e-30)
                vmax = vmin + max(mag * 0.02, 1e-30)
            
            # Build cache entry and delegate to render (avoids duplication with _render_from_grid_entry)
            cache_entry = {
                'Xi': Xi, 'Yi': Yi, 'Zi': Zi, 'vmin': vmin, 'vmax': vmax,
                'positions': positions, 'valid_channels': list(valid_channels), 'values': np.array(values),
                'is_zscore': is_zscore, 'title': title, 'frequency_band': frequency_band,
                'condition': condition, 'unit_label': unit_label
            }
            logger.info(f"Created topomap with {len(valid_channels)} channels")
            fig = self._render_from_grid_entry(cache_entry)
            if return_cache_entry and fig:
                return (fig, cache_entry)
            return fig
            
        except Exception as e:
            logger.error(f"Error creating topomap: {e}", exc_info=True)
            return None

    def plot_topomap_into_axes(self, ax, values: np.ndarray, channel_names: List[str],
                              title: str, is_zscore: bool = False,
                              allow_constant: bool = True) -> bool:
        """
        Plot a topomap into an existing axes. Used by topo sheets.
        When allow_constant=True, plots constant/zero data with symmetric range (for z-score, relative power).
        """
        try:
            positions, valid_channels = self._get_channel_positions(channel_names)
            if len(positions) < 4:
                return False
            channel_name_map = {}
            for orig_name in channel_names:
                cleaned = clean_channel_name(orig_name)
                if cleaned not in channel_name_map:
                    channel_name_map[cleaned] = orig_name
            matched_values = []
            for ch in valid_channels:
                orig_name = channel_name_map.get(ch, ch)
                if orig_name in channel_names:
                    idx = channel_names.index(orig_name)
                    matched_values.append(float(values[idx]) if idx < len(values) else 0.0)
                elif ch in channel_names:
                    idx = channel_names.index(ch)
                    matched_values.append(float(values[idx]) if idx < len(values) else 0.0)
                else:
                    ch_upper = ch.upper()
                    for i, cn in enumerate(channel_names):
                        if cn.upper() == ch_upper and i < len(values):
                            matched_values.append(float(values[i]))
                            break
                    else:
                        matched_values.append(0.0)
            values = np.array(matched_values, dtype=float)
            values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
            valid_mask = ~np.isnan(values) & np.isfinite(values)
            if np.sum(valid_mask) < 4:
                return False
            vmin, vmax = np.percentile(values[valid_mask], [2, 98])
            if vmax <= vmin or not np.isfinite(vmin) or not np.isfinite(vmax):
                vmin = float(np.min(values[valid_mask]))
                vmax = float(np.max(values[valid_mask]))
            if vmax <= vmin and allow_constant:
                center = float(np.mean(values[valid_mask]))
                mag = max(float(np.max(np.abs(values[valid_mask]))), abs(center), 1e-30)
                half_range = 0.5 if is_zscore else max(abs(center) * 0.1, mag * 0.02, 1e-30)
                vmin = center - half_range
                vmax = center + half_range
            if vmax <= vmin:
                mag = max(float(np.max(np.abs(values[valid_mask]))), 1e-30)
                vmax = vmin + max(mag * 0.02, 1e-30)
            resolution = getattr(self.config, 'get_topomap_resolution', lambda: self.config.get('topomaps.resolution', 128))()
            Xi, Yi, Zi = self._clinical_interpolation(values, positions, resolution)
            vmin, vmax = _expand_topomap_vlim_for_grid(
                vmin, vmax, Zi, is_zscore=is_zscore,
                zmin=self._zscore_vmin, zmax=self._zscore_vmax,
            )
            levels = np.linspace(vmin, vmax, 12)
            levels = np.unique(levels)
            if len(levels) < 2:
                levels = np.array([vmin, vmax])
            cmap = (
                self.theme.get_diverging_colormap()
                if is_zscore
                else _power_topomap_colormap()
            )
            ax.contourf(Xi, Yi, Zi, levels=levels, cmap=cmap, vmin=vmin, vmax=vmax, extend='both')
            if self.config.get('topomaps.show_contours', True):
                ax.contour(Xi, Yi, Zi, levels=np.linspace(vmin, vmax, 6),
                          colors='#1a2a44', linewidths=0.4, alpha=0.5)
            head_circle = plt.Circle((0, 0), 1.0, fill=False, color=self.theme.NEON_CYAN, linewidth=1.2, alpha=0.8)
            ax.add_patch(head_circle)
            ax.scatter(positions[:, 0], positions[:, 1], c=self.theme.get_foreground_color(),
                      s=20, edgecolors=self.theme.get_background_color(), linewidths=0.5, zorder=10, alpha=0.85)
            ax.set_xlim(-1.3, 1.3)
            ax.set_ylim(-1.3, 1.3)
            ax.set_aspect('equal')
            ax.axis('off')
            ax.set_title(title, color=self.theme.get_foreground_color(), fontsize=10, fontweight='bold')
            return True
        except Exception as e:
            logger.debug("plot_topomap_into_axes failed for %s: %s", title, e)
            return False

    def _plot_and_save_topomap_with_fallback(self, values: np.ndarray, channel_names: List[str],
                                             title: str, filepath: Path,
                                             cache_dir: Optional[Path] = None, cache_key: Optional[str] = None,
                                             **plot_kwargs) -> bool:
        """Plot and save one topomap; on failure retry once. Uses interpolation cache when available."""
        cache = self._load_interp_cache(cache_dir) if cache_dir else {}
        if cache_dir and cache_key and cache_key in cache:
            try:
                fig = self._render_from_grid_entry(cache[cache_key])
                if fig:
                    self._save_fig_with_fallback(fig, filepath)
                    return True
            except Exception as e:
                logger.warning("Cache render failed, falling back to full generation: %s", e)
        try:
            need_cache = bool(cache_dir and cache_key)
            result = self._plot_topomap(values, channel_names, title, return_cache_entry=need_cache, **plot_kwargs)
            if not result:
                return False
            if need_cache:
                fig, entry = result
                if entry:
                    cache[cache_key] = entry
                    self._save_interp_cache(cache_dir, cache)
            else:
                fig = result
            self._save_fig_with_fallback(fig, filepath)
            return True
        except Exception as e:
            if getattr(self.config, '_enhancement_failed', False):
                raise
            logger.warning("Enhanced topomap failed, retrying with default resolution/DPI: %s", e)
            self.config.set_enhancement_fallback()
            fig = self._plot_topomap(values, channel_names, title, **plot_kwargs)
            if not fig:
                return False
            self._save_fig_with_fallback(fig, filepath)
            return True

    def _save_fig_with_fallback(self, fig, filepath: Path, **extra_save_kwargs) -> bool:
        """Save figure with current DPI; on failure retry once with default DPI."""
        kwargs = {
            'format': self.config.get_format(),
            'facecolor': self.theme.get_background_color(),
            'bbox_inches': 'tight',
            'pad_inches': 0.1,
        }
        kwargs.update(extra_save_kwargs)
        try:
            fig.savefig(filepath, dpi=self.config.get_dpi(), **kwargs)
            plt.close(fig)
            return True
        except Exception as e:
            if getattr(self.config, '_enhancement_failed', False):
                raise
            logger.warning("Enhanced save failed, retrying with default DPI: %s", e)
            self.config.set_enhancement_fallback()
            fig.savefig(filepath, dpi=self.config.get_dpi(), **kwargs)
            plt.close(fig)
            return True

    def generate_band_topomaps(self, metrics_by_site: Dict[str, Any], 
                              output_dir: Path, 
                              subject_id: str,
                              session_id: str,
                              metrics_by_site_remontage: Optional[Dict[str, Any]] = None) -> Dict[str, Path]:
        """
        Generate topomaps for all frequency bands.
        When metrics_by_site_remontage is provided (19ch base/remontage comparison), also
        generates _avgref variants and adds them to the returned paths.
        
        Args:
            metrics_by_site: Dictionary of metrics by site
            output_dir: Output directory for images
            subject_id: Subject identifier
            session_id: Session identifier
            metrics_by_site_remontage: Optional avg-ref metrics for base vs remontage comparison
            
        Returns:
            Dictionary mapping band names to file paths
        """
        if not self.config.are_topomaps_enabled():
            return {}
        if not self.config.get('topomaps.generate_all_bands', True):
            return {}
        
        bands = self.config.get_topomap_bands()
        output_paths = {}
        generated_keys = set()
        is_nested = is_nested_structure(metrics_by_site)
        epochs_to_process = self._resolve_epochs(metrics_by_site)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for epoch in epochs_to_process:
            for band in bands:
                try:
                    # Extract band values
                    channel_names, values = extract_band_values(metrics_by_site, band, epoch)
                    
                    if len(channel_names) == 0:
                        logger.warning(f"No channels found for band {band} ({epoch or 'all'})")
                        continue
                    
                    # Check if we have any non-zero values
                    max_value = np.max(values) if len(values) > 0 else 0.0
                    min_value = np.min(values) if len(values) > 0 else 0.0
                    non_zero_count = np.sum(values != 0.0)
                    
                    logger.debug(f"Band {band} ({epoch or 'all'}): "
                               f"channels={len(channel_names)}, "
                               f"non-zero={non_zero_count}/{len(values)}, "
                               f"range=[{min_value:.4f}, {max_value:.4f}]")
                    
                    if max_value <= 0:
                        logger.warning(f"All values are zero for band {band} ({epoch or 'all'}), skipping topomap")
                        continue
                    
                    # Additional validation: check if we have enough valid data points
                    if non_zero_count < 2:
                        logger.warning(f"Too few non-zero values ({non_zero_count}) for band {band} ({epoch or 'all'}), "
                                    f"topomap may not display correctly")
                    
                    # Map band name for display (handle HiBeta, SMR capitalization)
                    band_display_map = {
                        'hibeta': 'HiBeta',
                        'smr': 'SMR'
                    }
                    band_display = band_display_map.get(band.lower(), band.capitalize())
                    
                    # Get frequency range for this band
                    freq_range = get_band_frequency_range(band, self._band_ranges)
                    
                    # Check if CSD should be applied
                    condition = epoch or ''
                    csd_enabled = self.config.get('csd.enabled', False)
                    apply_csd_to_topomaps = self.config.get('csd.apply_to_topomaps', False)
                    
                    if csd_enabled and apply_csd_to_topomaps and condition:
                        # Add CSD suffix to condition name
                        condition = f"{condition}_CSD"
                    
                    # Create title with frequency range
                    title = f"{band_display} Power"
                    if freq_range:
                        title += f" ({freq_range})"
                    if condition:
                        title += f" - {condition}"
                    
                    # Filename/key before generation (for fallback retry)
                    if condition:
                        filename = f"topomap_{band}_{condition.lower()}.png"
                        key = f"{band}_{condition.lower()}"
                    else:
                        filename = f"topomap_{band}.png"
                        key = band
                    if key in generated_keys:
                        logger.warning(f"Duplicate key detected: {key}, skipping")
                        continue
                    generated_keys.add(key)
                    filepath = output_dir / filename
                    
                    # Generate and save topomap (uses interpolation cache when available)
                    cache_key = f"band_{key}"
                    if self._plot_and_save_topomap_with_fallback(
                            values, channel_names, title, filepath,
                            cache_dir=output_dir, cache_key=cache_key,
                            is_zscore=False, frequency_band=band_display, condition=condition):
                        output_paths[key] = filepath
                        logger.info(f"Generated topomap for {band} ({epoch or 'all'}): {filepath}")
                        
                        # Create HTML wrapper with additional information
                        html_filepath = self._create_topomap_html_wrapper(
                            filepath, band, epoch, values, channel_names, output_dir
                        )
                        if html_filepath:
                            output_paths[f"{key}_html"] = html_filepath

                        # Remontage (avg-ref) variant for base vs re-montage comparison (19ch)
                        if metrics_by_site_remontage and epoch and is_nested_structure(metrics_by_site_remontage):
                            try:
                                ch_rem, val_rem = extract_band_values(metrics_by_site_remontage, band, epoch)
                                if len(ch_rem) >= 2 and (np.max(val_rem) if len(val_rem) else 0) > 0:
                                    cond_rem = f"{epoch}_avgref"
                                    title_rem = f"{band_display} Power"
                                    if freq_range:
                                        title_rem += f" ({freq_range})"
                                    title_rem += f" - {cond_rem}"
                                    key_rem = f"{band}_{epoch.lower()}_avgref"
                                    if key_rem not in generated_keys:
                                        generated_keys.add(key_rem)
                                        fp_rem = output_dir / f"topomap_{band}_{epoch.lower()}_avgref.png"
                                        if self._plot_and_save_topomap_with_fallback(
                                                np.array(val_rem), ch_rem, title_rem, fp_rem,
                                                cache_dir=output_dir, cache_key=f"band_{key_rem}",
                                                is_zscore=False, frequency_band=band_display, condition=cond_rem):
                                            output_paths[key_rem] = fp_rem
                                            logger.info("Generated remontage topomap for %s (%s): %s", band, epoch, fp_rem)
                                            html_rem = self._create_topomap_html_wrapper(
                                                fp_rem, band, cond_rem, val_rem, ch_rem, output_dir
                                            )
                                            if html_rem:
                                                output_paths[f"{key_rem}_html"] = html_rem
                            except Exception as ex:
                                logger.warning("Remontage topomap for %s %s: %s", band, epoch, ex)
                    else:
                        logger.warning(f"Failed to generate topomap for {band} ({epoch or 'all'})")
                        
                except Exception as e:
                    logger.error(f"Error generating topomap for {band} ({epoch or 'all'}): {e}", exc_info=True)
        
        # Separate pass: ensure individual avgref topomaps exist when remontage data is available
        # (base_avgref combined may exist from generate_base_remontage_side_by_side_topomaps,
        # but avgref-only can be missing if base topomap failed; generate them here)
        if metrics_by_site_remontage and is_nested_structure(metrics_by_site_remontage):
            remontage_epochs = get_all_available_epochs(metrics_by_site_remontage)
            for epoch in remontage_epochs:
                for band in bands:
                    key_rem = f"{band}_{epoch.lower()}_avgref"
                    if key_rem in generated_keys:
                        continue
                    try:
                        ch_rem, val_rem = extract_band_values(metrics_by_site_remontage, band, epoch)
                        if len(ch_rem) < 2 or (np.max(val_rem) if len(val_rem) else 0) <= 0:
                            continue
                        band_display_map = {'hibeta': 'HiBeta', 'smr': 'SMR'}
                        band_display = band_display_map.get(band.lower(), band.capitalize())
                        freq_range = get_band_frequency_range(band, self._band_ranges)
                        cond_rem = f"{epoch}_avgref"
                        title_rem = f"{band_display} Power"
                        if freq_range:
                            title_rem += f" ({freq_range})"
                        title_rem += f" - {cond_rem}"
                        generated_keys.add(key_rem)
                        fp_rem = output_dir / f"topomap_{band}_{epoch.lower()}_avgref.png"
                        if self._plot_and_save_topomap_with_fallback(
                                np.array(val_rem), ch_rem, title_rem, fp_rem,
                                cache_dir=output_dir, cache_key=f"band_{key_rem}",
                                is_zscore=False, frequency_band=band_display, condition=cond_rem):
                            output_paths[key_rem] = fp_rem
                            logger.info("Generated avgref-only topomap for %s (%s): %s", band, epoch, fp_rem)
                            html_rem = self._create_topomap_html_wrapper(
                                fp_rem, band, cond_rem, val_rem, ch_rem, output_dir
                            )
                            if html_rem:
                                output_paths[f"{key_rem}_html"] = html_rem
                    except Exception as ex:
                        logger.warning("Avgref-only topomap for %s %s: %s", band, epoch, ex)
        
        return output_paths
    
    def _create_side_by_side_topomap(self, eo_values: np.ndarray, ec_values: np.ndarray,
                                     channel_names: List[str], title_base: str,
                                     is_zscore: bool = False, unit_label: Optional[str] = None,
                                     left_label: str = "Eyes Open (EO)",
                                     right_label: str = "Eyes Closed (EC)",
                                     suptitle_suffix: Optional[str] = None) -> Optional[plt.Figure]:
        """
        Create a side-by-side topomap (e.g. EO vs EC, or Base vs Avg reference).
        
        Args:
            eo_values: Values for left plot
            ec_values: Values for right plot
            channel_names: List of channel names
            title_base: Base title (e.g., "Delta Power")
            is_zscore: Whether values are z-scores
            unit_label: Optional unit label
            left_label: Label for left subplot
            right_label: Label for right subplot
            suptitle_suffix: Override suptitle suffix (default: "left_label vs right_label")
            
        Returns:
            Matplotlib figure or None
        """
        try:
            suffix = suptitle_suffix if suptitle_suffix is not None else f"{left_label} vs {right_label}"
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(24, 10), 
                                           facecolor=self.theme.get_background_color())
            fig.suptitle(f"{title_base} - {suffix}", 
                        fontsize=16, color=self.theme.get_foreground_color(),
                        y=0.98)
            
            # Add branding in top-left corner of the figure
            fig.text(0.02, 0.98, "EEG Paradox Decoder Topo Generator",
                    fontsize=10, fontweight='bold',
                    color=self.theme.NEON_CYAN, ha='left', va='top',
                    bbox=dict(boxstyle='round,pad=0.3',
                            facecolor=self.theme.get_background_color(),
                            alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5),
                    transform=fig.transFigure, zorder=100)
            
            # Get positions for both plots
            positions, valid_channels = self._get_channel_positions(channel_names)
            if len(positions) == 0:
                return None
            
            # Ensure values match channels - use same order as valid_channels
            # This is critical to match individual topomaps exactly
            # Create a mapping from cleaned channel names to original channel names
            # This handles case mismatches (e.g., "CZ" vs "Cz")
            channel_name_map = {}
            for orig_name in channel_names:
                cleaned = clean_channel_name(orig_name)
                # If multiple original names map to same cleaned name, use first one
                if cleaned not in channel_name_map:
                    channel_name_map[cleaned] = orig_name
            
            # Match the channel order from valid_channels
            eo_vals = []
            ec_vals = []
            problematic_sites = ['Oz', 'Cz', 'Pz', 'Fz', 'OZ', 'CZ', 'PZ', 'FZ']
            for ch in valid_channels:
                # Try to find the original channel name that maps to this cleaned name
                orig_name = channel_name_map.get(ch, ch)
                is_problematic_ch = ch.upper() in [s.upper() for s in problematic_sites]
                matched = False
                
                if orig_name in channel_names:
                    idx = channel_names.index(orig_name)
                    if idx < len(eo_values):
                        eo_vals.append(eo_values[idx])
                    else:
                        eo_vals.append(0.0)
                    if idx < len(ec_values):
                        ec_vals.append(ec_values[idx])
                    else:
                        ec_vals.append(0.0)
                    matched = True
                    if is_problematic_ch:
                        logger.debug(f"Side-by-side topomap {ch} -> {orig_name} (idx {idx})")
                elif ch in channel_names:
                    # Also try direct match in case names are already cleaned
                    idx = channel_names.index(ch)
                    if idx < len(eo_values):
                        eo_vals.append(eo_values[idx])
                    else:
                        eo_vals.append(0.0)
                    if idx < len(ec_values):
                        ec_vals.append(ec_values[idx])
                    else:
                        ec_vals.append(0.0)
                    matched = True
                    if is_problematic_ch:
                        logger.debug(f"Side-by-side topomap {ch} direct match (idx {idx})")
                else:
                    # Final fallback: case-insensitive search
                    ch_upper = ch.upper()
                    for i, cn in enumerate(channel_names):
                        if cn.upper() == ch_upper:
                            if i < len(eo_values):
                                eo_vals.append(eo_values[i])
                            else:
                                eo_vals.append(0.0)
                            if i < len(ec_values):
                                ec_vals.append(ec_values[i])
                            else:
                                ec_vals.append(0.0)
                            matched = True
                            if is_problematic_ch:
                                logger.debug(f"Side-by-side topomap {ch} -> {cn} (case-insensitive, idx {i})")
                            break
                    
                    if not matched:
                        eo_vals.append(0.0)
                        ec_vals.append(0.0)
                        if is_problematic_ch:
                            logger.debug(f"Side-by-side topomap {ch} not found. Available: {channel_names[:15]}")
            
            eo_vals = np.array(eo_vals)
            ec_vals = np.array(ec_vals)
            
            # Interpolate for both using same method as individual plots
            resolution = getattr(self.config, 'get_topomap_resolution', lambda: self.config.get('topomaps.resolution', 128))()
            Xi1, Yi1, Zi1 = self._clinical_interpolation(eo_vals, positions, resolution)
            Xi2, Yi2, Zi2 = self._clinical_interpolation(ec_vals, positions, resolution)
            
            # Determine color scaling - use EXACT same logic as _plot_topomap for EACH plot independently
            # This ensures side-by-side images match individual ones exactly
            if is_zscore:
                eo_vmin, eo_vmax = self._zscore_vmin, self._zscore_vmax
                ec_vmin, ec_vmax = self._zscore_vmin, self._zscore_vmax
                cmap = self.theme.get_diverging_colormap()
                eo_vmin, eo_vmax = _expand_topomap_vlim_for_grid(
                    eo_vmin, eo_vmax, Zi1, is_zscore=True,
                    zmin=self._zscore_vmin, zmax=self._zscore_vmax,
                )
                ec_vmin, ec_vmax = _expand_topomap_vlim_for_grid(
                    ec_vmin, ec_vmax, Zi2, is_zscore=True,
                    zmin=self._zscore_vmin, zmax=self._zscore_vmax,
                )
            else:
                # Calculate EO scaling using EXACT same logic as _plot_topomap
                non_zero_eo = eo_vals[eo_vals != 0.0]
                non_zero_ratio_eo = len(non_zero_eo) / len(eo_vals) if len(eo_vals) > 0 else 0
                
                if len(non_zero_eo) > 0 and non_zero_ratio_eo < 0.5:
                    # Sparse EO data: use actual range of non-zero values (same as individual plot)
                    eo_vmin = np.min(non_zero_eo)
                    eo_vmax = np.max(non_zero_eo)
                else:
                    # Normal EO data: use 2nd and 98th percentiles (same as individual plot)
                    eo_vmin = np.percentile(eo_vals, 2)
                    eo_vmax = np.percentile(eo_vals, 98)
                
                if eo_vmax - eo_vmin < 1e-6:
                    eo_vmax = eo_vmin + 1e-6
                
                # Calculate EC scaling using EXACT same logic as _plot_topomap
                non_zero_ec = ec_vals[ec_vals != 0.0]
                non_zero_ratio_ec = len(non_zero_ec) / len(ec_vals) if len(ec_vals) > 0 else 0
                
                if len(non_zero_ec) > 0 and non_zero_ratio_ec < 0.5:
                    # Sparse EC data: use actual range of non-zero values (same as individual plot)
                    ec_vmin = np.min(non_zero_ec)
                    ec_vmax = np.max(non_zero_ec)
                else:
                    # Normal EC data: use 2nd and 98th percentiles (same as individual plot)
                    ec_vmin = np.percentile(ec_vals, 2)
                    ec_vmax = np.percentile(ec_vals, 98)
                
                if ec_vmax - ec_vmin < 1e-6:
                    ec_vmax = ec_vmin + 1e-6
                
                eo_vmin, eo_vmax = _expand_topomap_vlim_for_grid(
                    eo_vmin, eo_vmax, Zi1, is_zscore=False,
                    zmin=self._zscore_vmin, zmax=self._zscore_vmax,
                )
                ec_vmin, ec_vmax = _expand_topomap_vlim_for_grid(
                    ec_vmin, ec_vmax, Zi2, is_zscore=False,
                    zmin=self._zscore_vmin, zmax=self._zscore_vmax,
                )
                cmap = _power_topomap_colormap()
            
            # Plot EO on left with ITS OWN scaling (matches individual EO plot exactly)
            ax1.set_facecolor(self.theme.get_background_color())
            ax1.contourf(Xi1, Yi1, Zi1, levels=16, cmap=cmap, vmin=eo_vmin, vmax=eo_vmax, extend='both')
            ax1.contour(Xi1, Yi1, Zi1, levels=8, colors=self.theme.get_foreground_color(), 
                       linewidths=0.5, alpha=0.3)
            head_circle1 = plt.Circle((0, 0), 1.0, fill=False, color=self.theme.NEON_CYAN, 
                                     linewidth=1.8, alpha=0.8, zorder=3)
            ax1.add_patch(head_circle1)
            ax1.scatter(positions[:, 0], positions[:, 1], c=self.theme.get_foreground_color(),
                       s=42, edgecolors=self.theme.get_background_color(), linewidths=0.8, zorder=10)
            
            # Add channel labels to EO plot
            for i, (pos, ch) in enumerate(zip(positions, valid_channels)):
                dist_from_center = np.sqrt(pos[0]**2 + pos[1]**2)
                if dist_from_center > 0.8:
                    label_offset = -0.12
                    if abs(pos[0]) > 0.8:
                        ha = 'right' if pos[0] < 0 else 'left'
                    else:
                        ha = 'center'
                else:
                    label_offset = -0.08
                    ha = 'center'
                
                ax1.text(pos[0], pos[1] + label_offset, ch,
                        ha=ha, va='top',
                        color=self.theme.get_region_color(ch), fontsize=9, fontweight='bold',
                        zorder=11)
            
            ax1.set_xlim(-1.3, 1.3)
            ax1.set_ylim(-1.3, 1.3)
            ax1.set_aspect('equal')
            ax1.axis('off')
            ax1.text(0.5, -0.15, left_label, transform=ax1.transAxes,
                    ha='center', fontsize=14, color=self.theme.get_foreground_color(), fontweight='bold')
            
            # Plot right with ITS OWN scaling (matches individual plot exactly)
            ax2.set_facecolor(self.theme.get_background_color())
            ax2.contourf(Xi2, Yi2, Zi2, levels=16, cmap=cmap, vmin=ec_vmin, vmax=ec_vmax, extend='both')
            ax2.contour(Xi2, Yi2, Zi2, levels=8, colors=self.theme.get_foreground_color(),
                       linewidths=0.5, alpha=0.3)
            head_circle2 = plt.Circle((0, 0), 1.0, fill=False, color=self.theme.NEON_CYAN,
                                     linewidth=1.8, alpha=0.8, zorder=3)
            ax2.add_patch(head_circle2)
            ax2.scatter(positions[:, 0], positions[:, 1], c=self.theme.get_foreground_color(),
                       s=42, edgecolors=self.theme.get_background_color(), linewidths=0.8, zorder=10)
            
            # Add channel labels to EC plot
            for i, (pos, ch) in enumerate(zip(positions, valid_channels)):
                dist_from_center = np.sqrt(pos[0]**2 + pos[1]**2)
                if dist_from_center > 0.8:
                    label_offset = -0.12
                    if abs(pos[0]) > 0.8:
                        ha = 'right' if pos[0] < 0 else 'left'
                    else:
                        ha = 'center'
                else:
                    label_offset = -0.08
                    ha = 'center'
                
                ax2.text(pos[0], pos[1] + label_offset, ch,
                        ha=ha, va='top',
                        color=self.theme.get_region_color(ch), fontsize=9, fontweight='bold',
                        zorder=11)
            
            ax2.set_xlim(-1.3, 1.3)
            ax2.set_ylim(-1.3, 1.3)
            ax2.set_aspect('equal')
            ax2.axis('off')
            ax2.text(0.5, -0.15, right_label, transform=ax2.transAxes,
                    ha='center', fontsize=14, color=self.theme.get_foreground_color(), fontweight='bold')
            
            # Add colorbar for EC (right side) - shows EC's scale
            divider = make_axes_locatable(ax2)
            cax = divider.append_axes("right", size="5%", pad=0.1)
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=ec_vmin, vmax=ec_vmax))
            sm.set_array([])
            cbar = plt.colorbar(sm, cax=cax)
            cbar.set_label(unit_label or ("Z-Score" if is_zscore else "Power (µV)"),
                          color=self.theme.get_foreground_color(), fontsize=12)
            cbar.ax.tick_params(colors=self.theme.get_foreground_color())
            
            # Add colorbar for EO (left side) - shows EO's scale
            divider1 = make_axes_locatable(ax1)
            cax1 = divider1.append_axes("left", size="5%", pad=0.1)
            sm1 = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=eo_vmin, vmax=eo_vmax))
            sm1.set_array([])
            cbar1 = plt.colorbar(sm1, cax=cax1)
            cbar1.set_label(unit_label or ("Z-Score" if is_zscore else "Power (µV)"),
                           color=self.theme.get_foreground_color(), fontsize=12)
            cbar1.ax.tick_params(colors=self.theme.get_foreground_color())
            
            plt.tight_layout(rect=[0, 0.05, 1, 0.95])
            return fig
            
        except Exception as e:
            logger.error(f"Error creating side-by-side topomap: {e}", exc_info=True)
            return None
    
    def generate_side_by_side_topomaps(self, metrics_by_site: Dict[str, Any],
                                       output_dir: Path,
                                       subject_id: str,
                                       session_id: str,
                                       results: Optional[Dict[str, Any]] = None) -> Dict[str, Path]:
        """
        Generate side-by-side EO/EC topomaps when both epochs are available
        
        Args:
            metrics_by_site: Dictionary of metrics by site
            output_dir: Output directory
            subject_id: Subject identifier
            session_id: Session identifier
            
        Returns:
            Dictionary mapping visualization keys to file paths
        """
        output_paths = {}
        
        # Check if we have both EO and EC
        epochs = get_all_available_epochs(metrics_by_site)
        if 'EO' not in epochs or 'EC' not in epochs:
            logger.debug("Both EO and EC epochs not available, skipping side-by-side topomaps")
            return output_paths
        
        if not is_nested_structure(metrics_by_site):
            return output_paths
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate side-by-side for band topomaps
        # Use same bands as individual topomaps to ensure consistency
        bands = self.config.get_topomap_bands()
        logger.debug(f"Generating side-by-side topomaps for bands: {bands}")
        
        for band in bands:
            try:
                # Extract EO and EC values using EXACT same method as individual topomaps
                # This ensures the data matches exactly
                eo_channels, eo_values = extract_band_values(metrics_by_site, band, 'EO')
                ec_channels, ec_values = extract_band_values(metrics_by_site, band, 'EC')
                
                if len(eo_channels) == 0 or len(ec_channels) == 0:
                    logger.debug(f"Skipping side-by-side for {band}: EO channels={len(eo_channels)}, EC channels={len(ec_channels)}")
                    continue
                
                # Use union of channels (not intersection) to match individual topomap behavior
                # Individual topomaps show all available channels, even if one epoch is missing
                all_channels = sorted(set(eo_channels + ec_channels))
                
                if len(all_channels) == 0:
                    logger.warning(f"No channels found for {band} side-by-side")
                    continue
                
                # Extract values in same order as all_channels
                # Use 0.0 for missing channels (same as individual plots)
                eo_vals = []
                ec_vals = []
                for ch in all_channels:
                    if ch in eo_channels:
                        eo_vals.append(eo_values[eo_channels.index(ch)])
                    else:
                        eo_vals.append(0.0)
                    
                    if ch in ec_channels:
                        ec_vals.append(ec_values[ec_channels.index(ch)])
                    else:
                        ec_vals.append(0.0)
                
                eo_vals = np.array(eo_vals)
                ec_vals = np.array(ec_vals)
                
                # Verify we have non-zero data
                if np.max(eo_vals) <= 0 and np.max(ec_vals) <= 0:
                    logger.debug(f"All values are zero for {band} side-by-side, skipping")
                    continue
                
                # Map band name for display (handle HiBeta, SMR capitalization)
                band_display_map = {'hibeta': 'HiBeta', 'smr': 'SMR'}
                band_display = band_display_map.get(band.lower(), band.capitalize())
                
                # Get frequency range for this band
                freq_range = get_band_frequency_range(band, self._band_ranges)
                
                # Create title with frequency range
                title_base = f"{band_display} Power"
                if freq_range:
                    title_base += f" ({freq_range})"
                
                logger.debug(f"Creating side-by-side for {band_display}: {len(all_channels)} channels, "
                           f"EO range=[{np.min(eo_vals):.4f}, {np.max(eo_vals):.4f}], "
                           f"EC range=[{np.min(ec_vals):.4f}, {np.max(ec_vals):.4f}]")
                
                # Create side-by-side using same data extraction as individual plots (try enhanced, fallback if fails)
                def _do_side_by_side():
                    fig = self._create_side_by_side_topomap(
                        eo_vals, ec_vals,
                        all_channels, title_base,
                        is_zscore=False
                    )
                    if fig:
                        filename = f"topomap_{band}_eo_ec_combined.png"
                        fp = output_dir / filename
                        self._save_fig_with_fallback(fig, fp)
                        return fp
                    return None
                try:
                    filepath = _do_side_by_side()
                except Exception as e:
                    if not getattr(self.config, '_enhancement_failed', False):
                        logger.warning("Enhanced side-by-side failed, retrying with default res/DPI: %s", e)
                        self.config.set_enhancement_fallback()
                        filepath = _do_side_by_side()
                    else:
                        raise
                if filepath:
                    output_paths[f"{band}_eo_ec"] = filepath
                    logger.info(f"Generated side-by-side topomap for {band}: {filepath}")
                    
                    # Create HTML wrapper with comparison notes
                    logger.info(f"Calling _create_comparison_html_wrapper for {band} with {len(eo_vals)} EO values and {len(ec_vals)} EC values")
                    html_filepath = self._create_comparison_html_wrapper(
                        filepath, band, eo_vals, ec_vals, all_channels, output_dir, results=results
                    )
                    if html_filepath:
                        logger.info(f"HTML wrapper created successfully for {band}: {html_filepath}")
                        output_paths[f"{band}_eo_ec_html"] = html_filepath
                    else:
                        logger.warning(f"HTML wrapper creation returned None for {band} - insights JSON will not be created")
                    
            except Exception as e:
                logger.error(f"Error generating side-by-side topomap for {band}: {e}", exc_info=True)
        
        return output_paths

    def generate_base_remontage_side_by_side_topomaps(
        self,
        metrics_by_site: Dict[str, Any],
        metrics_by_site_remontage: Dict[str, Any],
        output_dir: Path,
        subject_id: str,
        session_id: str,
    ) -> Dict[str, Path]:
        """
        Generate side-by-side Base (recording ref) vs Avg reference topomaps per band per epoch.
        Used for 19-channel base vs re-montage comparison.
        """
        output_paths = {}
        if not is_nested_structure(metrics_by_site) or not is_nested_structure(metrics_by_site_remontage):
            return output_paths
        epochs = get_all_available_epochs(metrics_by_site)
        remontage_epochs = set(get_all_available_epochs(metrics_by_site_remontage))
        bands = self.config.get_topomap_bands()
        band_display_map = {'hibeta': 'HiBeta', 'smr': 'SMR'}
        output_dir.mkdir(parents=True, exist_ok=True)
        for band in bands:
            band_display = band_display_map.get(band.lower(), band.capitalize())
            freq_range = get_band_frequency_range(band, self._band_ranges)
            title_base = f"{band_display} Power"
            if freq_range:
                title_base += f" ({freq_range})"
            for epoch in epochs:
                if epoch not in remontage_epochs:
                    continue
                try:
                    ch_base, val_base = extract_band_values(metrics_by_site, band, epoch)
                    ch_rem, val_rem = extract_band_values(metrics_by_site_remontage, band, epoch)
                    if len(ch_base) < 2 or len(ch_rem) < 2:
                        continue
                    all_ch = sorted(set(ch_base) | set(ch_rem))
                    base_vals = np.array([val_base[ch_base.index(c)] if c in ch_base else 0.0 for c in all_ch])
                    rem_vals = np.array([val_rem[ch_rem.index(c)] if c in ch_rem else 0.0 for c in all_ch])
                    if np.max(base_vals) <= 0 and np.max(rem_vals) <= 0:
                        continue
                    def _do_base_remontage():
                        fig = self._create_side_by_side_topomap(
                            base_vals, rem_vals, all_ch, title_base,
                            left_label="Base (recording ref)", right_label="Avg reference",
                            suptitle_suffix="Base vs Avg reference",
                        )
                        if fig:
                            fn = f"topomap_{band}_{epoch.lower()}_base_avgref.png"
                            fp = output_dir / fn
                            self._save_fig_with_fallback(fig, fp)
                            return fp
                        return None
                    try:
                        fp = _do_base_remontage()
                    except Exception as err:
                        if not getattr(self.config, '_enhancement_failed', False):
                            self.config.set_enhancement_fallback()
                            fp = _do_base_remontage()
                        else:
                            raise
                    if fp:
                        key = f"{band}_{epoch.lower()}_base_avgref"
                        output_paths[key] = fp
                        logger.info("Generated base vs remontage topomap for %s %s: %s", band, epoch, fp)
                except Exception as e:
                    logger.warning("Base/remontage side-by-side for %s %s: %s", band, epoch, e)
        return output_paths
    
    def _calculate_comparison_insights(self, band: str, eo_values: np.ndarray, 
                                       ec_values: np.ndarray, channel_names: List[str],
                                       results: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Calculate clinical insights for EO vs EC comparison
        
        Uses actual detection results (conditions, phenotypes, norm violations) when available,
        combined with pattern-based analysis for comprehensive insights.
        """
        try:
            # Calculate statistics
            eo_non_zero = eo_values[eo_values != 0.0]
            ec_non_zero = ec_values[ec_values != 0.0]
            
            if len(eo_non_zero) == 0 or len(ec_non_zero) == 0:
                return {}
            
            eo_mean = float(np.mean(eo_non_zero))
            ec_mean = float(np.mean(ec_non_zero))
            
            # Calculate reactivity
            reactivity = ec_mean - eo_mean
            reactivity_pct = (reactivity / eo_mean * 100) if eo_mean > 0 else 0
            
            # Generate comparison notes
            comparison_notes = []
            
            # Alpha reactivity check
            if band.lower() == 'alpha':
                    if reactivity_pct > 50:
                        comparison_notes.append({
                            'type': 'normal',
                            'title': '[OK] Normal Alpha Reactivity',
                            'note': f'Alpha increased by {reactivity_pct:.1f}% in EC (normal reactivity). Indicates healthy visual cortex response.'
                        })
                    elif reactivity_pct > 20:
                        comparison_notes.append({
                            'type': 'mild',
                            'title': '[WARNING] Reduced Alpha Reactivity',
                            'note': f'Alpha increased by only {reactivity_pct:.1f}% in EC (expected >50%). May indicate visual processing issues.'
                        })
                    else:
                        comparison_notes.append({
                            'type': 'concerning',
                            'title': '[ALERT] Poor Alpha Reactivity',
                            'note': f'Minimal alpha increase ({reactivity_pct:.1f}%) in EC. May indicate visual processing dysfunction or anxiety.'
                        })
            
            # Check for asymmetry patterns
            left_channels = [ch for ch in channel_names if any(ch.upper().endswith(s) for s in ['1', '3', '7']) or ch.upper() in ['FP1', 'F3', 'F7', 'C3', 'P3', 'O1', 'T7']]
            right_channels = [ch for ch in channel_names if any(ch.upper().endswith(s) for s in ['2', '4', '8']) or ch.upper() in ['FP2', 'F4', 'F8', 'C4', 'P4', 'O2', 'T8']]
            
            if left_channels and right_channels:
                left_indices = [i for i, ch in enumerate(channel_names) if ch in left_channels]
                right_indices = [i for i, ch in enumerate(channel_names) if ch in right_channels]
                
                if left_indices and right_indices:
                    eo_left_mean = np.mean([eo_values[i] for i in left_indices if i < len(eo_values)])
                    eo_right_mean = np.mean([eo_values[i] for i in right_indices if i < len(eo_values)])
                    ec_left_mean = np.mean([ec_values[i] for i in left_indices if i < len(ec_values)])
                    ec_right_mean = np.mean([ec_values[i] for i in right_indices if i < len(ec_values)])
                    
                    eo_asymmetry = abs(eo_left_mean - eo_right_mean) / max(eo_left_mean, eo_right_mean) * 100 if max(eo_left_mean, eo_right_mean) > 0 else 0
                    ec_asymmetry = abs(ec_left_mean - ec_right_mean) / max(ec_left_mean, ec_right_mean) * 100 if max(ec_left_mean, ec_right_mean) > 0 else 0
                    
                    if eo_asymmetry > 20 or ec_asymmetry > 20:
                        band_label = band.upper()
                        if eo_left_mean > eo_right_mean or ec_left_mean > ec_right_mean:
                            comparison_notes.append({
                                'type': 'asymmetry',
                                'title': '[WARNING] Left Hemisphere Dominance',
                                'note': f'Left hemisphere shows higher {band_label} activity (EO: {eo_asymmetry:.1f}%, EC: {ec_asymmetry:.1f}% asymmetry).'
                            })
                        else:
                            comparison_notes.append({
                                'type': 'asymmetry',
                                'title': '[WARNING] Right Hemisphere Dominance',
                                'note': f'Right hemisphere shows higher {band_label} activity (EO: {eo_asymmetry:.1f}%, EC: {ec_asymmetry:.1f}% asymmetry).'
                            })
            
            # Get top clinical insights for key channels
            # First, try to use actual detection results (conditions, norm violations)
            eo_clinical_keys = []
            ec_clinical_keys = []
            
            # Use norm violations and conditions if available
            if results:
                try:
                    from hexnode.eeg.utils.z_score_severity import get_z_score_thresholds
                    _sig_thresh = get_z_score_thresholds().get('abnormal', 2.0)
                except Exception:
                    _sig_thresh = 2.0
                norm_violations = results.get('norm_violations', {})
                conditions = results.get('conditions', [])
                band_lower = band.lower()
                
                # Collect relevant findings for this band
                for ch in channel_names:
                    ch_upper = ch.upper()
                    
                    # Check norm violations for this channel/band
                    for epoch_key in ['EO', 'EC']:
                        epoch_lower = epoch_key.lower()
                        clinical_keys_list = eo_clinical_keys if epoch_key == 'EO' else ec_clinical_keys
                        
                        # Look for norm violations
                        if epoch_key in norm_violations:
                            epoch_violations = norm_violations[epoch_key]
                            if ch_upper in epoch_violations:
                                site_violations = epoch_violations[ch_upper]
                                for metric, violation_data in site_violations.items():
                                    if isinstance(violation_data, dict) and band_lower in metric.lower():
                                        z_score = violation_data.get('z_score', 0)
                                        if abs(z_score) >= _sig_thresh:  # Significant deviation
                                            direction = 'high' if z_score > 0 else 'low'
                                            key = self._get_clinical_interpretation(ch, band, direction, epoch_key)
                                            if key:
                                                # Enhance with actual z-score
                                                key['z_score'] = z_score
                                                key['source'] = 'norm_analysis'
                                                if key not in clinical_keys_list:
                                                    clinical_keys_list.append(key)
                        
                        # Look for conditions at this channel/band
                        for condition in conditions:
                            cond_site = condition.get('site', '').upper()
                            cond_band = condition.get('band', '').lower()
                            cond_epoch = condition.get('epoch', '').upper()
                            
                            if (cond_site == ch_upper and 
                                cond_band == band_lower and 
                                (cond_epoch == epoch_key or cond_epoch == '')):
                                # Create clinical key from condition
                                cond_name = condition.get('condition', '')
                                key = {
                                    'location': f"{ch} ({cond_name})",
                                    'pattern': cond_name,
                                    'interpretation': condition.get('description', f'{cond_name} detected at {ch}'),
                                    'clinical_context': condition.get('severity', 'mild').title() + ' severity',
                                    'source': 'condition_detection',
                                    'confidence': condition.get('confidence', 0)
                                }
                                if key not in clinical_keys_list:
                                    clinical_keys_list.append(key)
            
            # Fallback to pattern-based analysis if no detection results or insufficient findings
            if len(eo_clinical_keys) < 2 or len(ec_clinical_keys) < 2:
                if len(channel_names) > 0:
                    eo_sorted = np.argsort(eo_values)[::-1]
                    eo_top = [channel_names[i] for i in eo_sorted[:3] if i < len(eo_values) and eo_values[i] > 0]
                    for ch in eo_top:
                        if len(eo_clinical_keys) >= 3:
                            break
                        try:
                            ch_idx = channel_names.index(ch)
                            if ch_idx < len(eo_values) and eo_values[ch_idx] > eo_mean * 1.3:  # Lowered threshold
                                key = self._get_clinical_interpretation(ch, band, 'high', 'EO')
                                if key and key not in eo_clinical_keys:
                                    key['source'] = 'pattern_analysis'
                                    eo_clinical_keys.append(key)
                        except (ValueError, IndexError):
                            continue
                    
                    ec_sorted = np.argsort(ec_values)[::-1]
                    ec_top = [channel_names[i] for i in ec_sorted[:3] if i < len(ec_values) and ec_values[i] > 0]
                    for ch in ec_top:
                        if len(ec_clinical_keys) >= 3:
                            break
                        try:
                            ch_idx = channel_names.index(ch)
                            if ch_idx < len(ec_values) and ec_values[ch_idx] > ec_mean * 1.3:  # Lowered threshold
                                key = self._get_clinical_interpretation(ch, band, 'high', 'EC')
                                if key and key not in ec_clinical_keys:
                                    key['source'] = 'pattern_analysis'
                                    ec_clinical_keys.append(key)
                        except (ValueError, IndexError):
                            continue
            
            # Enhance with actual detection results if available
            if results:
                # Get relevant conditions for this band and channels
                conditions = results.get('conditions', [])
                band_lower = band.lower()
                
                # Filter conditions relevant to this band and displayed channels
                relevant_conditions = []
                for condition in conditions:
                    cond_band = condition.get('band', '').lower()
                    cond_site = condition.get('site', '').upper()
                    # Match if band matches and site is in our channels
                    if cond_band == band_lower and cond_site in [ch.upper() for ch in channel_names]:
                        # Only include significant conditions (avoid clutter)
                        confidence = condition.get('confidence', 0)
                        severity = condition.get('severity', '')
                        if confidence >= 0.5 or severity in ['moderate', 'severe']:
                            relevant_conditions.append(condition)
                
                # Add top 2-3 most relevant conditions to comparison notes
                if relevant_conditions:
                    # Sort by confidence/severity
                    relevant_conditions.sort(key=lambda x: (
                        x.get('confidence', 0),
                        {'severe': 3, 'moderate': 2, 'mild': 1}.get(x.get('severity', ''), 0)
                    ), reverse=True)
                    
                    for cond in relevant_conditions[:2]:  # Limit to top 2
                        cond_name = cond.get('condition', '')
                        cond_site = cond.get('site', '')
                        cond_severity = cond.get('severity', 'mild')
                        
                        # Determine note type based on severity
                        if cond_severity == 'severe':
                            note_type = 'concerning'
                        elif cond_severity == 'moderate':
                            note_type = 'mild'
                        else:
                            note_type = 'normal'
                        
                        comparison_notes.append({
                            'type': note_type,
                            'title': f'[DETECTED] {cond_name}',
                            'note': f'Detected at {cond_site} ({cond_severity} severity). Part of comprehensive analysis findings.'
                        })
                
                # Add relevant phenotypes (top 1-2)
                phenotypes = results.get('phenotypes', [])
                if phenotypes:
                    # Filter phenotypes that might relate to this band
                    band_related_phenotypes = []
                    for phenotype in phenotypes:
                        phenotype_name = phenotype.get('phenotype', '').lower()
                        # Check if phenotype name mentions this band or related terms
                        if band_lower in phenotype_name or any(term in phenotype_name for term in ['alpha', 'beta', 'theta', 'delta', 'gamma', 'smr']):
                            band_related_phenotypes.append(phenotype)
                    
                    if band_related_phenotypes:
                        # Take top phenotype
                        top_phenotype = band_related_phenotypes[0]
                        phenotype_name = top_phenotype.get('phenotype', '')
                        comparison_notes.append({
                            'type': 'mild',
                            'title': f'[PHENOTYPE] {phenotype_name}',
                            'note': 'Identified phenotype pattern relevant to this frequency band analysis.'
                        })
            
            return {
                'comparison_notes': comparison_notes,
                'eo_clinical_keys': eo_clinical_keys,
                'ec_clinical_keys': ec_clinical_keys,
                'reactivity_pct': reactivity_pct,
                'eo_mean': eo_mean,
                'ec_mean': ec_mean
            }
        except Exception as e:
            logger.error(f"Error calculating comparison insights: {e}", exc_info=True)
            return {}
    
    def _add_clinical_insights_to_figure(self, fig: plt.Figure, insights: Dict[str, Any]) -> None:
        """Add clinical insights as text annotations to the figure"""
        try:
            comparison_notes = insights.get('comparison_notes', [])
            eo_clinical_keys = insights.get('eo_clinical_keys', [])
            ec_clinical_keys = insights.get('ec_clinical_keys', [])
            
            if not comparison_notes and not eo_clinical_keys and not ec_clinical_keys:
                return
            
            # Create text box at bottom of figure
            text_y_start = 0.02
            text_x = 0.5
            line_height = 0.025
            current_y = text_y_start
            
            # Add comparison notes
            if comparison_notes:
                fig.text(text_x, current_y + line_height * 2, "Clinical Insights:",
                        ha='center', fontsize=11, fontweight='bold',
                        color=self.theme.NEON_CYAN, transform=fig.transFigure)
                current_y += line_height * 1.5
                
                for note in comparison_notes[:3]:  # Limit to 3 most important
                    note_type = note.get('type', 'normal')
                    title = note.get('title', '')
                    note_text = note.get('note', '')
                    
                    # Choose color based on type
                    if note_type == 'normal':
                        color = '#00FF88'
                    elif note_type == 'mild':
                        color = '#FFA500'
                    elif note_type == 'concerning':
                        color = '#FF4444'
                    else:
                        color = '#FFA500'
                    
                    # Add title
                    fig.text(text_x, current_y, title,
                            ha='center', fontsize=10, fontweight='bold',
                            color=color, transform=fig.transFigure)
                    current_y -= line_height
                    
                    # Add note text (truncate if too long)
                    if len(note_text) > 80:
                        note_text = note_text[:77] + "..."
                    fig.text(text_x, current_y, note_text,
                            ha='center', fontsize=9,
                            color=self.theme.get_foreground_color(), transform=fig.transFigure)
                    current_y -= line_height * 1.2
            
            # Add key channel insights
            if eo_clinical_keys or ec_clinical_keys:
                current_y -= line_height * 0.5
                fig.text(text_x, current_y, "Key Locations:",
                        ha='center', fontsize=10, fontweight='bold',
                        color=self.theme.NEON_CYAN, transform=fig.transFigure)
                current_y -= line_height
                
                key_texts = []
                for key in (eo_clinical_keys + ec_clinical_keys)[:4]:  # Limit to 4
                    location = key.get('location', '')
                    interpretation = key.get('interpretation', '')
                    if location and interpretation:
                        # Truncate interpretation if too long
                        if len(interpretation) > 50:
                            interpretation = interpretation[:47] + "..."
                        key_texts.append(f"{location}: {interpretation}")
                
                if key_texts:
                    combined_text = " • ".join(key_texts)
                    if len(combined_text) > 120:
                        # Split into two lines if needed
                        mid = len(combined_text) // 2
                        split_pos = combined_text.rfind(' • ', 0, mid)
                        if split_pos > 0:
                            fig.text(text_x, current_y, combined_text[:split_pos],
                                    ha='center', fontsize=8,
                                    color=self.theme.get_foreground_color(), transform=fig.transFigure)
                            current_y -= line_height * 0.8
                            fig.text(text_x, current_y, combined_text[split_pos+3:],
                                    ha='center', fontsize=8,
                                    color=self.theme.get_foreground_color(), transform=fig.transFigure)
                        else:
                            fig.text(text_x, current_y, combined_text[:120] + "...",
                                    ha='center', fontsize=8,
                                    color=self.theme.get_foreground_color(), transform=fig.transFigure)
                    else:
                        fig.text(text_x, current_y, combined_text,
                                ha='center', fontsize=8,
                                color=self.theme.get_foreground_color(), transform=fig.transFigure)
        except Exception as e:
            logger.error(f"Error adding clinical insights to figure: {e}", exc_info=True)
    
    def _create_comparison_html_wrapper(self, image_path: Path, band: str,
                                       eo_values: np.ndarray, ec_values: np.ndarray,
                                       channel_names: List[str],
                                       output_dir: Path,
                                       results: Optional[Dict[str, Any]] = None) -> Optional[Path]:
        """Create HTML wrapper for EO vs EC comparison with clinical notes"""
        logger.info(f"Creating comparison HTML wrapper for {band} at {image_path}")
        logger.info(f"  Input: EO values shape={eo_values.shape}, EC values shape={ec_values.shape}, channels={len(channel_names)}")
        try:
            # Calculate statistics for both epochs
            # Use a small threshold to avoid floating point precision issues
            threshold = 1e-10
            eo_non_zero = eo_values[eo_values > threshold]
            ec_non_zero = ec_values[ec_values > threshold]
            
            logger.info(f"  After filtering near-zero values (threshold={threshold}): EO non-zero={len(eo_non_zero)}, EC non-zero={len(ec_non_zero)}")
            logger.info(f"  EO value range: min={np.min(eo_values):.6f}, max={np.max(eo_values):.6f}, mean={np.mean(eo_values):.6f}")
            logger.info(f"  EC value range: min={np.min(ec_values):.6f}, max={np.max(ec_values):.6f}, mean={np.mean(ec_values):.6f}")
            
            # Require at least 3 non-zero values in each epoch for meaningful comparison
            min_required = 3
            if len(eo_non_zero) < min_required or len(ec_non_zero) < min_required:
                logger.warning(f"Skipping HTML wrapper for {band}: insufficient non-zero values (EO: {len(eo_non_zero)}, EC: {len(ec_non_zero)}, required: {min_required} each)")
                return None
            
            eo_mean = float(np.mean(eo_non_zero))
            ec_mean = float(np.mean(ec_non_zero))
            eo_max = float(np.max(eo_non_zero))
            ec_max = float(np.max(ec_non_zero))
            
            # Calculate reactivity (EC - EO change)
            reactivity = ec_mean - eo_mean
            reactivity_pct = (reactivity / eo_mean * 100) if eo_mean > 0 else 0
            
            # Get frequency range
            freq_range = get_band_frequency_range(band, self._band_ranges)
            band_label = band.upper()
            
            # Use the helper method to calculate insights (with actual detection results if available)
            insights = self._calculate_comparison_insights(band, eo_values, ec_values, channel_names, results=results)
            comparison_notes = insights.get('comparison_notes', [])
            eo_clinical_keys = insights.get('eo_clinical_keys', [])
            ec_clinical_keys = insights.get('ec_clinical_keys', [])
            
            
            # Generate clinical keys HTML sections
            clinical_keys_html = self._generate_comparison_clinical_keys(band, eo_clinical_keys, ec_clinical_keys)
            
            # Embed the PNG image as base64 so it works when HTML is downloaded
            image_base64 = None
            if image_path.exists():
                try:
                    with open(image_path, 'rb') as img_file:
                        image_data = img_file.read()
                        image_base64 = base64.b64encode(image_data).decode('utf-8')
                        # Determine image format from extension
                        img_format = 'png' if image_path.suffix.lower() == '.png' else 'jpeg'
                        image_data_uri = f"data:image/{img_format};base64,{image_base64}"
                except Exception as e:
                    logger.warning(f"Failed to embed image in HTML: {e}")
                    image_data_uri = image_path.name  # Fallback to filename
            
            # Create HTML
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>EEG Paradox Decoder - {band_label} EO vs EC Comparison</title>
    <style>
        body {{ font-family: Arial, sans-serif; background: #0a0a0a; color: #ffffff; margin: 0; padding: 20px; }}
        .container {{ max-width: 1600px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 20px; color: #00F0FF; }}
        .comparison-section {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
        .topomap-card {{ background: rgba(0, 0, 0, 0.8); border: 2px solid #00F0FF; border-radius: 8px; padding: 20px; }}
        .topomap-card h3 {{ color: #00F0FF; margin-top: 0; text-align: center; }}
        .topomap-card img {{ width: 100%; height: auto; border-radius: 4px; }}
        .stats-box {{ background: rgba(0, 240, 255, 0.1); padding: 15px; border-radius: 4px; margin-top: 15px; }}
        .comparison-notes {{ background: rgba(255, 165, 0, 0.1); border: 2px solid #FFA500; border-radius: 8px; padding: 20px; margin-top: 20px; }}
        .comparison-notes h3 {{ color: #FFA500; margin-top: 0; }}
        .note-item {{ margin-bottom: 1rem; padding: 0.75rem; background: rgba(0, 0, 0, 0.3); border-radius: 4px; border-left: 3px solid #FFA500; }}
        .note-item.normal {{ border-left-color: #00FF88; }}
        .note-item.mild {{ border-left-color: #FFA500; }}
        .note-item.concerning {{ border-left-color: #FF4444; }}
        .note-item.asymmetry {{ border-left-color: #FFA500; }}
        .note-title {{ font-weight: bold; margin-bottom: 0.25rem; }}
        .clinical-keys-section {{ margin-top: 20px; }}
        .clinical-keys-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px; }}
        .clinical-key-box {{ background: rgba(0, 255, 136, 0.1); border-radius: 4px; border-left: 3px solid #00FF88; max-height: 500px; overflow-y: auto; display: flex; flex-direction: column; }}
        .clinical-key-box h4 {{ color: #00FF88; margin: 0; padding: 15px 15px 10px 15px; position: sticky; top: 0; background: rgba(0, 255, 136, 0.15); z-index: 10; border-radius: 4px 4px 0 0; }}
        .clinical-key-box > div {{ padding: 0 15px 15px 15px; }}
        .clinical-key-box::-webkit-scrollbar {{ width: 8px; }}
        .clinical-key-box::-webkit-scrollbar-track {{ background: rgba(0, 0, 0, 0.3); border-radius: 4px; }}
        .clinical-key-box::-webkit-scrollbar-thumb {{ background: rgba(0, 255, 136, 0.5); border-radius: 4px; }}
        .clinical-key-box::-webkit-scrollbar-thumb:hover {{ background: rgba(0, 255, 136, 0.7); }}
        .button-group {{ margin-top: 20px; display: flex; gap: 10px; justify-content: center; }}
        .btn {{ background: #00F0FF; color: #000; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; }}
        .btn:hover {{ background: #00D0E0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>EEG Paradox Decoder - {band_label} Power Comparison</h1>
            <p>{freq_range} • Eyes Open vs Eyes Closed</p>
        </div>
        
        <div style="text-align: center; margin-bottom: 20px;">
            <img src="{image_data_uri if image_base64 else image_path.name}" alt="{band_label} EO vs EC Comparison" style="max-width: 100%; height: auto; border: 2px solid #00F0FF; border-radius: 8px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
            <div style="display: none; color: #FFA500; padding: 1rem; background: rgba(255, 165, 0, 0.1); border-radius: 4px; margin-top: 1rem;">
                <p>Image not found. Make sure {image_path.name} is in the same directory as this HTML file.</p>
                <p>You can download the image separately using the button below.</p>
            </div>
        </div>
        
        <div class="comparison-section">
            <div class="topomap-card">
                <h3>👁️ Eyes Open (EO)</h3>
                <div class="stats-box">
                    <p><b>Mean:</b> {eo_mean:.4f} µV²</p>
                    <p><b>Peak:</b> {eo_max:.4f} µV²</p>
                    <p><b>Active Channels:</b> {len(eo_non_zero)}/{len(eo_values)}</p>
                </div>
            </div>
            <div class="topomap-card">
                <h3>👁️‍🗨️ Eyes Closed (EC)</h3>
                <div class="stats-box">
                    <p><b>Mean:</b> {ec_mean:.4f} µV²</p>
                    <p><b>Peak:</b> {ec_max:.4f} µV²</p>
                    <p><b>Active Channels:</b> {len(ec_non_zero)}/{len(ec_values)}</p>
                    <p><b>Reactivity:</b> {reactivity:+.4f} µV² ({reactivity_pct:+.1f}%)</p>
                </div>
            </div>
        </div>
        
        <div class="comparison-notes">
            <h3>🔍 Comparison Analysis</h3>
            {'<br>'.join([f'''
            <div class="note-item {note['type']}">
                <div class="note-title">{note['title']}</div>
                <div>{note['note']}</div>
            </div>
            ''' for note in comparison_notes])}
            
            <div style="margin-top: 1rem; padding: 0.75rem; background: rgba(0, 0, 0, 0.3); border-radius: 4px; font-size: 0.9em;">
                <b>📊 Key Observations:</b><br>
                • Compare the spatial distribution between EO and EC states<br>
                • Note any regions that show significant changes (reactivity)<br>
                • Look for patterns that persist across both states (stable findings)<br>
                • Review clinical interpretation keys below for location-specific insights
            </div>
        </div>
        
        {clinical_keys_html}
        
        <div class="button-group">
            <a href="{image_path.name}" download class="btn">📥 Download Image</a>
            <button onclick="window.print()" class="btn">🖨️ Print</button>
        </div>
    </div>
</body>
</html>"""
            
            # Save HTML file
            html_filename = image_path.stem + '.html'
            html_filepath = output_dir / html_filename
            
            logger.info(f"Saving HTML file: {html_filepath} for band {band}")
            with open(html_filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"Successfully saved HTML file: {html_filepath}")
            
            # Also save insights as JSON for easy frontend access
            insights_json = {
                'band': band,
                'band_label': band_label,
                'freq_range': freq_range,
                'eo_mean': eo_mean,
                'ec_mean': ec_mean,
                'eo_max': eo_max,
                'ec_max': ec_max,
                'reactivity': float(reactivity),
                'reactivity_pct': float(reactivity_pct),
                'eo_active_channels': len(eo_non_zero),
                'ec_active_channels': len(ec_non_zero),
                'total_channels': len(eo_values),
                'comparison_notes': comparison_notes,
                'eo_clinical_keys': eo_clinical_keys,
                'ec_clinical_keys': ec_clinical_keys
            }
            
            json_filename = image_path.stem + '_insights.json'
            json_filepath = output_dir / json_filename
            import json
            
            # Ensure output directory exists
            output_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Attempting to create insights JSON file: {json_filepath}")
            logger.info(f"  JSON data keys: {list(insights_json.keys())}")
            try:
                with open(json_filepath, 'w', encoding='utf-8') as f:
                    json.dump(insights_json, f, indent=2, default=str)
                logger.info(f"Created insights JSON file: {json_filepath}")
                # Verify file was actually created
                if json_filepath.exists():
                    file_size = json_filepath.stat().st_size
                    logger.info(f"Verified insights JSON file exists: {json_filepath} (size: {file_size} bytes)")
                else:
                    logger.error(f"❌ Insights JSON file was not created despite no exception: {json_filepath}")
            except Exception as json_error:
                logger.error(f"❌ Failed to create insights JSON file {json_filepath}: {json_error}", exc_info=True)
                # Continue anyway - HTML file is still useful
            
            return html_filepath
            
        except Exception as e:
            logger.error(f"❌ Failed to create comparison HTML wrapper for {band}: {e}", exc_info=True)
            return None
    
    def generate_absolute_power_topomaps(self, metrics_by_site: Dict[str, Any],
                                         output_dir: Path,
                                         subject_id: str,
                                         session_id: str,
                                         metrics_by_site_remontage: Optional[Dict[str, Any]] = None) -> Dict[str, Path]:
        """
        Generate absolute power (total power) topomaps.
        When metrics_by_site_remontage is provided, also generates avgref variants.
        
        Args:
            metrics_by_site: Dictionary of metrics by site
            output_dir: Output directory for images
            subject_id: Subject identifier
            session_id: Session identifier
            metrics_by_site_remontage: Optional avg-ref metrics for avgref variants
            
        Returns:
            Dictionary mapping epoch names to file paths
        """
        if not self.config.are_topomaps_enabled():
            return {}
        
        output_paths = {}
        is_nested = is_nested_structure(metrics_by_site)
        epochs_to_process = self._resolve_epochs(metrics_by_site)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        bands = ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma', 'SMR', 'HiBeta']
        
        for epoch in epochs_to_process:
            try:
                channel_names = extract_all_sites(metrics_by_site)
                absolute_powers = []
                
                for ch_name in channel_names:
                    site_data = metrics_by_site.get(ch_name, {})
                    
                    # Handle nested structure with epoch
                    if is_nested and epoch:
                        # Try case-insensitive epoch lookup
                        epoch_key = None
                        if isinstance(site_data, dict):
                            # Try exact match first
                            if epoch in site_data:
                                epoch_key = epoch
                            else:
                                # Try case-insensitive match
                                epoch_upper = epoch.upper()
                                epoch_lower = epoch.lower()
                                for key in site_data.keys():
                                    if isinstance(key, str):
                                        if key.upper() == epoch_upper or key.lower() == epoch_lower:
                                            epoch_key = key
                                            break
                        
                        if epoch_key and epoch_key in site_data:
                            site_metrics = site_data[epoch_key]
                            # Validate that site_metrics is a dict, not a list
                            if not isinstance(site_metrics, dict):
                                logger.warning(f"Epoch '{epoch}' data for site {ch_name} is not a dict: {type(site_metrics)}, skipping")
                                absolute_powers.append(0.0)
                                continue
                        else:
                            available_keys = list(site_data.keys()) if isinstance(site_data, dict) else []
                            logger.warning(f"Epoch '{epoch}' not found for site {ch_name}. Available keys: {available_keys}")
                            # Don't skip - use 0.0 but log warning
                            absolute_powers.append(0.0)
                            continue
                    elif is_nested and not epoch:
                        # Average across available epochs
                        epoch_values = []
                        for ep_key, ep_metrics in site_data.items():
                            if isinstance(ep_metrics, dict) and ep_key in ['EO', 'EC', 'EOT', 'EO1', 'EO2', 'EC1', 'EC2']:
                                # Calculate power for this epoch
                                ep_total_power = 0.0
                                for band in bands:
                                    band_amplitude = ep_metrics.get(band, 0.0)
                                    ep_total_power += band_amplitude ** 2
                                if ep_total_power > 0:
                                    epoch_values.append(np.sqrt(ep_total_power))
                        
                        if epoch_values:
                            absolute_power = np.mean(epoch_values)
                        else:
                            absolute_power = 0.0
                        absolute_powers.append(absolute_power)
                        continue
                    else:
                        # Flat structure
                        site_metrics = site_data if isinstance(site_data, dict) else {}
                    
                    # Sum of squared band amplitudes (power)
                    total_power = 0.0
                    for band in bands:
                        band_amplitude = site_metrics.get(band, 0.0)
                        # Convert amplitude to power (A²)
                        total_power += band_amplitude ** 2
                    
                    # Convert back to amplitude (sqrt of total power)
                    absolute_power = np.sqrt(total_power) if total_power > 0 else 0.0
                    absolute_powers.append(absolute_power)
                
                if len(absolute_powers) == 0:
                    logger.warning(f"No channels found for absolute power topomap ({epoch or 'all'})")
                    continue
                
                # Check if we have any non-zero values
                max_absolute = np.max(absolute_powers) if len(absolute_powers) > 0 else 0.0
                min_absolute = np.min(absolute_powers) if len(absolute_powers) > 0 else 0.0
                
                # Check for too many zeros (indicates missing data)
                zero_count = np.sum(np.array(absolute_powers) == 0.0)
                zero_ratio = zero_count / len(absolute_powers) if len(absolute_powers) > 0 else 1.0
                
                if max_absolute <= 0:
                    logger.warning(f"All absolute power values are zero for ({epoch or 'all'}), skipping topomap")
                    continue
                
                if zero_ratio > 0.5:  # More than 50% zeros
                    logger.warning(f"High zero ratio ({zero_ratio:.1%}) for {epoch or 'all'} absolute power. "
                                 f"Range: [{min_absolute:.4f}, {max_absolute:.4f}] µV. "
                                 f"This may indicate missing channel data.")
                
                title = "Absolute Power"
                if epoch:
                    title += f" ({epoch})"
                
                if epoch:
                    filename = f"topomap_absolute_{epoch.lower()}.png"
                    key = f"absolute_{epoch.lower()}"
                else:
                    filename = "topomap_absolute.png"
                    key = "absolute"
                filepath = output_dir / filename
                if self._plot_and_save_topomap_with_fallback(
                        np.array(absolute_powers), channel_names, title, filepath,
                        cache_dir=output_dir, cache_key=key,
                        is_zscore=False, frequency_band='Absolute', condition=epoch or '',
                        unit_label='Amplitude (µV)'):
                    output_paths[key] = filepath
                    logger.info(f"Generated absolute power topomap ({epoch or 'all'}): {filepath}")
                    
            except Exception as e:
                logger.error(f"Error generating absolute power topomap ({epoch or 'all'}): {e}", exc_info=True)
        
        # Avgref variants when remontage data available
        bands_for_abs = ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma', 'SMR', 'HiBeta']
        if metrics_by_site_remontage and is_nested_structure(metrics_by_site_remontage):
            remontage_epochs = get_all_available_epochs(metrics_by_site_remontage)
            for epoch in remontage_epochs:
                if not epoch:
                    continue
                try:
                    channel_names = extract_all_sites(metrics_by_site_remontage)
                    absolute_powers = []
                    for ch_name in channel_names:
                        site_data = metrics_by_site_remontage.get(ch_name, {})
                        epoch_key = epoch if epoch in site_data else None
                        if not epoch_key:
                            for key in (site_data.keys() if isinstance(site_data, dict) else []):
                                if isinstance(key, str) and key.upper() == epoch.upper():
                                    epoch_key = key
                                    break
                        if epoch_key and epoch_key in site_data:
                            site_metrics = site_data[epoch_key]
                            if not isinstance(site_metrics, dict):
                                absolute_powers.append(0.0)
                                continue
                        else:
                            absolute_powers.append(0.0)
                            continue
                        total_power = sum((site_metrics.get(b, 0.0) ** 2) for b in bands_for_abs)
                        absolute_powers.append(np.sqrt(total_power) if total_power > 0 else 0.0)
                    if len(absolute_powers) < 2 or np.max(absolute_powers) <= 0:
                        continue
                    key_rem = f"absolute_{epoch.lower()}_avgref"
                    title = f"Absolute Power ({epoch}) - avgref"
                    fp = output_dir / f"topomap_absolute_{epoch.lower()}_avgref.png"
                    if self._plot_and_save_topomap_with_fallback(
                            np.array(absolute_powers), channel_names, title, fp,
                            cache_dir=output_dir, cache_key=f"absolute_{key_rem}",
                            is_zscore=False, frequency_band='Absolute', condition=f"{epoch}_avgref",
                            unit_label='Amplitude (µV)'):
                        output_paths[key_rem] = fp
                        logger.info("Generated absolute power avgref topomap (%s): %s", epoch, fp)
                except Exception as ex:
                    logger.warning("Absolute power avgref for %s: %s", epoch, ex)
        
        return output_paths
    
    def generate_relative_power_topomaps(self, metrics_by_site: Dict[str, Any],
                                       output_dir: Path,
                                       subject_id: str,
                                       session_id: str,
                                       metrics_by_site_remontage: Optional[Dict[str, Any]] = None) -> Dict[str, Path]:
        """
        Generate relative power topomaps for each frequency band.
        When metrics_by_site_remontage is provided, also generates avgref variants.
        
        Args:
            metrics_by_site: Dictionary of metrics by site
            output_dir: Output directory for images
            subject_id: Subject identifier
            session_id: Session identifier
            metrics_by_site_remontage: Optional avg-ref metrics for avgref variants
            
        Returns:
            Dictionary mapping band_epoch names to file paths
        """
        if not self.config.are_topomaps_enabled():
            return {}
        
        output_paths = {}
        is_nested = is_nested_structure(metrics_by_site)
        epochs_to_process = self._resolve_epochs(metrics_by_site)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        bands = self.config.get_topomap_bands()
        
        band_metric_map = {
            'delta': 'Delta',
            'theta': 'Theta',
            'alpha': 'Alpha',
            'beta': 'Beta',
            'gamma': 'Gamma',
            'smr': 'SMR',
            'hibeta': 'HiBeta'  # Note: metrics use HiBeta, not Hibeta
        }
        
        # All bands for total power calculation
        all_band_keys = ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma', 'SMR', 'HiBeta']
        
        for epoch in epochs_to_process:
            for band in bands:
                try:
                    channel_names = extract_all_sites(metrics_by_site)
                    relative_powers = []
                    
                    # Get the correct metric key for this band
                    band_metric_key = band_metric_map.get(band.lower(), band.capitalize())
                    
                    for ch_name in channel_names:
                        site_data = metrics_by_site.get(ch_name, {})
                        
                        # Handle nested structure with epoch
                        if is_nested and epoch:
                            # Try case-insensitive epoch lookup
                            epoch_key = None
                            if isinstance(site_data, dict):
                                # Try exact match first
                                if epoch in site_data:
                                    epoch_key = epoch
                                else:
                                    # Try case-insensitive match
                                    epoch_upper = epoch.upper()
                                    epoch_lower = epoch.lower()
                                    for key in site_data.keys():
                                        if isinstance(key, str):
                                            if key.upper() == epoch_upper or key.lower() == epoch_lower:
                                                epoch_key = key
                                                break
                            
                            if epoch_key and epoch_key in site_data:
                                site_metrics = site_data[epoch_key]
                                # Validate that site_metrics is a dict, not a list
                                if not isinstance(site_metrics, dict):
                                    logger.warning(f"Epoch '{epoch}' data for site {ch_name} is not a dict: {type(site_metrics)}, skipping")
                                    relative_powers.append(0.0)
                                    continue
                            else:
                                available_keys = list(site_data.keys()) if isinstance(site_data, dict) else []
                                logger.debug(f"Epoch '{epoch}' not found for site {ch_name} in relative power calculation. Available keys: {available_keys}")
                                relative_powers.append(0.0)
                                continue
                        elif is_nested and not epoch:
                            # Average across available epochs
                            epoch_relative_values = []
                            for ep_key, ep_metrics in site_data.items():
                                if isinstance(ep_metrics, dict) and ep_key in ['EO', 'EC', 'EOT', 'EO1', 'EO2', 'EC1', 'EC2']:
                                    # Calculate total power for this epoch
                                    ep_total_power = 0.0
                                    for b_key in all_band_keys:
                                        p = float(ep_metrics.get(b_key, 0.0))
                                        ep_total_power += max(p, 0.0)
                                    band_power = max(float(ep_metrics.get(band_metric_key, 0.0)), 0.0)
                                    if ep_total_power > 0:
                                        ep_relative = (band_power / ep_total_power) * 100.0
                                        epoch_relative_values.append(ep_relative)
                            
                            if epoch_relative_values:
                                relative_power = np.mean(epoch_relative_values)
                            else:
                                relative_power = 0.0
                            relative_powers.append(relative_power)
                            continue
                        else:
                            # Flat structure
                            site_metrics = site_data if isinstance(site_data, dict) else {}
                        
                        # Band keys hold integrated band *power* (Welch), not amplitude
                        total_power = 0.0
                        for b_key in all_band_keys:
                            p = float(site_metrics.get(b_key, 0.0))
                            total_power += max(p, 0.0)
                        band_power = max(float(site_metrics.get(band_metric_key, 0.0)), 0.0)
                        if total_power > 0:
                            relative_power = (band_power / total_power) * 100.0
                        else:
                            relative_power = 0.0
                        
                        relative_powers.append(relative_power)
                    
                    if len(relative_powers) == 0:
                        logger.warning(f"No channels found for relative power topomap: {band} ({epoch or 'all'})")
                        continue
                    
                    # Check if we have any non-zero values
                    max_relative = np.max(relative_powers) if len(relative_powers) > 0 else 0.0
                    if max_relative <= 0:
                        logger.warning(f"All relative power values are zero for {band} ({epoch or 'all'}), skipping topomap")
                        continue
                    
                    # Get frequency range for this band
                    freq_range = get_band_frequency_range(band, self._band_ranges)
                    
                    # Create title with frequency range
                    title = f"{band_metric_key} Relative Power (%)"
                    if freq_range:
                        title += f" ({freq_range})"
                    if epoch:
                        title += f" - {epoch}"
                    
                    if epoch:
                        filename = f"topomap_relative_{band}_{epoch.lower()}.png"
                        key = f"relative_{band}_{epoch.lower()}"
                    else:
                        filename = f"topomap_relative_{band}.png"
                        key = f"relative_{band}"
                    filepath = output_dir / filename
                    if self._plot_and_save_topomap_with_fallback(
                            np.array(relative_powers), channel_names, title, filepath,
                            cache_dir=output_dir, cache_key=f"relative_{key}",
                            is_zscore=False, frequency_band=band_metric_key,
                            condition=epoch or '', unit_label='Power (%)'):
                        output_paths[key] = filepath
                        logger.info(f"Generated relative power topomap for {band} ({epoch or 'all'}): {filepath}")
                        
                except Exception as e:
                    logger.error(f"Error generating relative power topomap for {band} ({epoch or 'all'}): {e}", exc_info=True)
        
        # Avgref variants when remontage data available
        if metrics_by_site_remontage and is_nested_structure(metrics_by_site_remontage):
            remontage_epochs = get_all_available_epochs(metrics_by_site_remontage)
            for epoch in remontage_epochs:
                if not epoch:
                    continue
                for band in bands:
                    try:
                        channel_names_rem = extract_all_sites(metrics_by_site_remontage)
                        relative_powers = []
                        band_metric_key = band_metric_map.get(band.lower(), band.capitalize())
                        for ch_name in channel_names_rem:
                            site_data = metrics_by_site_remontage.get(ch_name, {})
                            epoch_key = epoch if epoch in site_data else None
                            if not epoch_key:
                                for k in (site_data.keys() if isinstance(site_data, dict) else []):
                                    if isinstance(k, str) and k.upper() == epoch.upper():
                                        epoch_key = k
                                        break
                            if epoch_key and epoch_key in site_data:
                                site_metrics = site_data[epoch_key]
                                if isinstance(site_metrics, dict):
                                    total_power = sum(
                                        max(float(site_metrics.get(b, 0.0)), 0.0) for b in all_band_keys
                                    )
                                    band_power = max(float(site_metrics.get(band_metric_key, 0.0)), 0.0)
                                    rel = (band_power / total_power * 100.0) if total_power > 0 else 0.0
                                    relative_powers.append(rel)
                                else:
                                    relative_powers.append(0.0)
                            else:
                                relative_powers.append(0.0)
                        if np.max(relative_powers) <= 0:
                            continue
                        key_rem = f"relative_{band}_{epoch.lower()}_avgref"
                        freq_range = get_band_frequency_range(band, self._band_ranges)
                        title = f"{band_metric_key} Relative Power (%)"
                        if freq_range:
                            title += f" ({freq_range})"
                        title += f" - {epoch} - avgref"
                        fp = output_dir / f"topomap_relative_{band}_{epoch.lower()}_avgref.png"
                        if self._plot_and_save_topomap_with_fallback(
                                np.array(relative_powers), channel_names_rem, title, fp,
                                cache_dir=output_dir, cache_key=f"relative_{key_rem}",
                                is_zscore=False, frequency_band=band_metric_key,
                                condition=f"{epoch}_avgref", unit_label='Power (%)'):
                            output_paths[key_rem] = fp
                            logger.info("Generated relative power avgref topomap for %s (%s): %s", band, epoch, fp)
                    except Exception as ex:
                        logger.warning("Relative power avgref for %s %s: %s", band, epoch, ex)
        
        return output_paths
    
    def generate_zscore_topomaps(self, metrics_by_site: Dict[str, Any],
                                 norm_violations: Dict[str, Any],
                                 output_dir: Path,
                                 subject_id: str,
                                 session_id: str) -> Dict[str, Path]:
        """
        Generate z-score topomaps using Cuban database or norm violations
        
        Args:
            metrics_by_site: Dictionary of metrics by site
            norm_violations: Dictionary of norm violations
            output_dir: Output directory for images
            subject_id: Subject identifier
            session_id: Session identifier
            
        Returns:
            Dictionary mapping band names to file paths
        """
        if not self.config.are_topomaps_enabled():
            return {}
        if not self.config.get('topomaps.generate_z_scores', True):
            return {}
        
        output_paths = {}
        bands = self.config.get_topomap_bands()
        epochs_to_process = self._resolve_epochs(metrics_by_site)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for epoch in epochs_to_process:
            for band in bands:
                try:
                    # Try to get z-scores from norm_violations first
                    z_scores = None
                    channel_names = extract_all_sites(metrics_by_site)
                    
                    # Check norm_violations structure
                    if norm_violations:
                        # Try to find z-scores for this band and epoch
                        for site in channel_names:
                            if site in norm_violations:
                                site_violations = norm_violations[site]
                                if isinstance(site_violations, dict):
                                    # Look for band-specific z-scores
                                    band_key = band.lower()
                                    if band_key in site_violations:
                                        z_score = site_violations[band_key].get('z_score', 0.0)
                                        if z_scores is None:
                                            z_scores = []
                                        z_scores.append(z_score)
                    
                    # If no z-scores from norm_violations, calculate from metrics
                    if z_scores is None or len(z_scores) != len(channel_names):
                        # Extract band values and calculate z-scores
                        _, values = extract_band_values(metrics_by_site, band, epoch)
                        
                        # Simple z-score calculation (mean=0, std=1 normalization)
                        # In production, this should use Cuban database
                        mean_val = np.mean(values)
                        std_val = np.std(values) if np.std(values) > 0 else 1.0
                        z_scores = (values - mean_val) / std_val
                    
                    if len(z_scores) != len(channel_names):
                        logger.warning(f"Z-score length mismatch for {band}")
                        continue
                    
                    # Map band name for display (handle HiBeta, SMR capitalization)
                    band_display_map = {
                        'hibeta': 'HiBeta',
                        'smr': 'SMR'
                    }
                    band_display = band_display_map.get(band.lower(), band.capitalize())
                    
                    # Get frequency range for this band
                    freq_range = get_band_frequency_range(band, self._band_ranges)
                    
                    # Create title with frequency range
                    title = f"{band_display} Z-Scores"
                    if freq_range:
                        title += f" ({freq_range})"
                    if epoch:
                        title += f" - {epoch}"
                    
                    if epoch:
                        filename = f"topomap_zscore_{band}_{epoch.lower()}.png"
                        key = f"zscore_{band}_{epoch.lower()}"
                    else:
                        filename = f"topomap_zscore_{band}.png"
                        key = f"zscore_{band}"
                    filepath = output_dir / filename
                    if self._plot_and_save_topomap_with_fallback(
                            np.array(z_scores), channel_names, title, filepath,
                            cache_dir=output_dir, cache_key=key,
                            is_zscore=True, frequency_band=band.capitalize(), condition=epoch or ''):
                        output_paths[key] = filepath
                        logger.info(f"Generated z-score topomap for {band} ({epoch or 'all'}): {filepath}")
                    else:
                        logger.warning(f"Failed to generate z-score topomap for {band} ({epoch or 'all'})")
                        
                except Exception as e:
                    logger.error(f"Error generating z-score topomap for {band} ({epoch or 'all'}): {e}", exc_info=True)
        
        return output_paths

    def generate_abs_rel_pair_topomaps(self, metrics_by_site: Dict[str, Any],
                                       output_dir: Path,
                                       subject_id: str,
                                       session_id: str) -> Dict[str, Path]:
        """
        Generate side-by-side absolute vs relative power topomaps (Squiggle-style).

        One figure per band with abs and rel topomaps side by side.
        Composites two topomaps into a single image per band.

        Returns:
            Dict mapping band to file path
        """
        if not self.config.are_topomaps_enabled():
            return {}
        output_paths = {}
        bands = self.config.get_topomap_bands()
        epochs = get_all_available_epochs(metrics_by_site)
        epoch = epochs[0] if epochs else None
        output_dir.mkdir(parents=True, exist_ok=True)
        bands_all = ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma', 'SMR', 'HiBeta']
        for band in bands:
            try:
                ch_names, abs_vals = extract_band_values(metrics_by_site, band, epoch)
                if len(ch_names) < 4 or np.all(np.array(abs_vals) == 0):
                    continue
                abs_vals = np.array(abs_vals, dtype=float)
                # Metrics from Welch integration are band *power* (e.g. V² or µV²), not amplitude.
                # Relative band power % = 100 * P_band / sum(P_b). Do not square powers again.
                total_power = np.zeros(len(ch_names))
                for b in bands_all:
                    ch_b, v = extract_band_values(metrics_by_site, b, epoch)
                    ch_to_idx = {c: i for i, c in enumerate(ch_b)}
                    for i, ch in enumerate(ch_names):
                        if ch in ch_to_idx:
                            idx = ch_to_idx[ch]
                            total_power[i] += max(float(v[idx]), 0.0)
                total_power = np.maximum(total_power, 1e-30)
                rel_vals = 100.0 * np.maximum(abs_vals, 0.0) / total_power
                band_display = {'hibeta': 'HiBeta', 'smr': 'SMR'}.get(band.lower(), band.capitalize())
                freq_range = get_band_frequency_range(band, self._band_ranges)
                title_abs = f"{band_display} Absolute" + (f" ({freq_range})" if freq_range else "")
                title_rel = f"{band_display} Relative" + (f" ({freq_range})" if freq_range else "")
                fig_abs = self._plot_topomap(abs_vals, ch_names, title_abs, is_zscore=False)
                fig_rel = self._plot_topomap(rel_vals, ch_names, title_rel, is_zscore=False)
                if fig_abs is None or fig_rel is None:
                    continue
                try:
                    import io
                    buf_abs = io.BytesIO()
                    buf_rel = io.BytesIO()
                    fig_abs.savefig(buf_abs, format='png', dpi=100, bbox_inches='tight',
                                   facecolor=self.theme.get_background_color())
                    fig_rel.savefig(buf_rel, format='png', dpi=100, bbox_inches='tight',
                                   facecolor=self.theme.get_background_color())
                    plt.close(fig_abs)
                    plt.close(fig_rel)
                    buf_abs.seek(0)
                    buf_rel.seek(0)
                    from PIL import Image
                    img_abs = Image.open(buf_abs).convert('RGB')
                    img_rel = Image.open(buf_rel).convert('RGB')
                    w, h = img_abs.size
                    composite = Image.new('RGB', (w * 2 + 20, h))
                    composite.paste(img_abs, (0, 0))
                    composite.paste(img_rel, (w + 20, 0))
                    fp = output_dir / f"topomap_abs_rel_{band}.png"
                    composite.save(fp)
                    output_paths[f"abs_rel_{band}"] = fp
                    logger.info(f"Generated abs/rel pair topomap for {band}: {fp}")
                except ImportError:
                    fp_abs = output_dir / f"topomap_abs_rel_{band}_abs.png"
                    fp_rel = output_dir / f"topomap_abs_rel_{band}_rel.png"
                    self._save_fig_with_fallback(fig_abs, fp_abs)
                    self._save_fig_with_fallback(fig_rel, fp_rel)
                    plt.close(fig_abs)
                    plt.close(fig_rel)
                    output_paths[f"abs_rel_{band}_abs"] = fp_abs
                    output_paths[f"abs_rel_{band}_rel"] = fp_rel
            except Exception as e:
                logger.debug(f"Abs/rel pair for {band}: {e}")
        return output_paths

    def generate_difference_topomaps(self, metrics_by_site: Dict[str, Any],
                                     output_dir: Path,
                                     subject_id: str,
                                     session_id: str) -> Dict[str, Path]:
        """
        Generate EO − EC difference topomaps and bar charts (Squiggle-style).

        Requires both EO and EC epochs. Creates difference topomap and bar per band.

        Returns:
            Dict mapping band to topomap path and bar path
        """
        if not self.config.are_topomaps_enabled():
            return {}
        epochs = get_all_available_epochs(metrics_by_site)
        if 'EO' not in epochs or 'EC' not in epochs:
            return {}
        output_paths = {}
        bands = self.config.get_topomap_bands()
        output_dir.mkdir(parents=True, exist_ok=True)
        for band in bands:
            try:
                eo_ch, eo_vals = extract_band_values(metrics_by_site, band, 'EO')
                ec_ch, ec_vals = extract_band_values(metrics_by_site, band, 'EC')
                all_ch = sorted(set(eo_ch + ec_ch))
                if len(all_ch) < 4:
                    continue
                eo_map = {ch: v for ch, v in zip(eo_ch, eo_vals)}
                ec_map = {ch: v for ch, v in zip(ec_ch, ec_vals)}
                diff_vals = np.array([eo_map.get(ch, 0.0) - ec_map.get(ch, 0.0) for ch in all_ch])
                if np.all(diff_vals == 0):
                    continue
                band_display = {'hibeta': 'HiBeta', 'smr': 'SMR'}.get(band.lower(), band.capitalize())
                freq_range = get_band_frequency_range(band, self._band_ranges)
                title = f"{band_display} EO − EC" + (f" ({freq_range})" if freq_range else "")
                max_abs = max(np.max(np.abs(diff_vals)), 1e-6)
                diff_scaled = 3.0 * diff_vals / max_abs
                if self._plot_and_save_topomap_with_fallback(
                        diff_scaled, all_ch, title, output_dir / f"topomap_diff_{band}.png",
                        is_zscore=True, frequency_band=band_display, condition="EO−EC"):
                    output_paths[f"diff_topomap_{band}"] = output_dir / f"topomap_diff_{band}.png"
                fig2, ax2 = plt.subplots(figsize=(10, 5), facecolor=self.theme.get_background_color())
                ax2.set_facecolor(self.theme.get_background_color())
                colors = [self.theme.NEON_LIME if v >= 0 else self.theme.NEON_RED for v in diff_vals]
                ax2.bar(range(len(all_ch)), diff_vals, color=colors)
                ax2.set_xticks(range(len(all_ch)))
                ax2.set_xticklabels(all_ch, rotation=90, fontsize=8, color=self.theme.get_foreground_color())
                ax2.set_ylabel("EO − EC", color=self.theme.get_foreground_color())
                ax2.set_title(f"{title} - Bar Chart", color=self.theme.get_foreground_color())
                ax2.tick_params(colors=self.theme.get_foreground_color())
                ax2.axhline(0, color=self.theme.get_foreground_color(), linewidth=0.5)
                fig2.tight_layout()
                fp_bar = output_dir / f"topomap_diff_bar_{band}.png"
                self._save_fig_with_fallback(fig2, fp_bar)
                output_paths[f"diff_bar_{band}"] = fp_bar
                plt.close(fig2)
            except Exception as e:
                logger.debug(f"Difference topomap for {band}: {e}")
        return output_paths

    def generate_instability_topomaps(self, metrics_by_site: Dict[str, Any],
                                       output_dir: Path,
                                       subject_id: str,
                                       session_id: str) -> Dict[str, Path]:
        """
        Generate Instability (variance across epochs) topomaps per band.

        Requires multiple epochs (EO, EC, etc.). Skips when len(epochs) < 2
        or len(channels) < 4.

        Returns:
            Dict mapping band to topomap path
        """
        if not self.config.are_topomaps_enabled():
            return {}
        epochs = get_all_available_epochs(metrics_by_site)
        if len(epochs) < 2:
            return {}
        output_paths = {}
        bands = self.config.get_topomap_bands()
        output_dir.mkdir(parents=True, exist_ok=True)
        for band in bands:
            try:
                ch_names, var_vals = extract_band_instability(metrics_by_site, band)
                if len(ch_names) < 4 or len(var_vals) < 4:
                    continue
                if np.all(var_vals == 0):
                    continue
                band_display = {'hibeta': 'HiBeta', 'smr': 'SMR'}.get(band.lower(), band.capitalize())
                freq_range = get_band_frequency_range(band, self._band_ranges)
                title = f"{band_display} Instability" + (f" ({freq_range})" if freq_range else "")
                fp = output_dir / f"topomap_instability_{band}.png"
                if self._plot_and_save_topomap_with_fallback(
                        var_vals, ch_names, title, fp,
                        is_zscore=False, frequency_band=band_display, condition="Variance"):
                    output_paths[f"instability_{band}"] = fp
            except Exception as e:
                logger.debug(f"Instability topomap for {band}: {e}")
        return output_paths

    def generate_topomap_grid(self, metrics_by_site: Dict[str, Any],
                              output_dir: Path,
                              subject_id: str,
                              session_id: str,
                              qc_summary: Optional[Dict[str, Any]] = None,
                              ica_applied_before_metrics: bool = False) -> Optional[Path]:
        """
        Generate multi-band topomap grid
        
        Args:
            metrics_by_site: Dictionary of metrics by site
            output_dir: Output directory for images
            subject_id: Subject identifier
            session_id: Session identifier
            qc_summary: Optional session QC summary for Data quality callout on figure
            ica_applied_before_metrics: Whether ICA was applied before metrics (shown in QC callout)
            
        Returns:
            Path to generated grid image or None
        """
        if not self.config.are_topomaps_enabled():
            return None
        
        bands = self.config.get_topomap_bands()
        epochs_to_process = self._resolve_epochs(metrics_by_site)
        output_dir.mkdir(parents=True, exist_ok=True)
        grid_paths = []
        
        for epoch in epochs_to_process:
            # Determine grid layout
            n_bands = len(bands)
            n_cols = min(3, n_bands)
            n_rows = int(np.ceil(n_bands / n_cols))
            
            fig, axes = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 5 * n_rows),
                                    facecolor=self.theme.get_background_color())
            fig.patch.set_facecolor(self.theme.get_background_color())
            
            fig.text(0.02, 0.98, "EEG Paradox Decoder Topo Generator",
                    fontsize=10, fontweight='bold',
                    color=self.theme.NEON_CYAN, ha='left', va='top',
                    bbox=dict(boxstyle='round,pad=0.3',
                            facecolor=self.theme.get_background_color(),
                            alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5),
                    transform=fig.transFigure, zorder=100)
            
            # Handle axes configuration
            if n_bands == 1:
                axes = [axes]
            elif n_rows == 1:
                axes = axes.reshape(1, -1) if n_cols > 1 else [axes]
            else:
                axes = axes.flatten()
            
            for idx, band in enumerate(bands):
                try:
                    # Extract band values
                    channel_names, values = extract_band_values(metrics_by_site, band, epoch)
                    
                    if len(channel_names) == 0:
                        continue
                    
                    
                    
                    # Get subplot
                    ax = axes[idx] if n_bands > 1 else axes[0]
                    
                    # Get positions
                    positions, valid_channels = self._get_channel_positions(channel_names)
                    
                    if len(positions) == 0:
                        logger.warning(f"No valid positions for band {band} in grid topomap")
                        ax.axis('off')
                        continue
                    
                    # Match values to valid_channels (handle case mismatches)
                    # Create a mapping from cleaned channel names to original channel names
                    channel_name_map = {}
                    for orig_name in channel_names:
                        cleaned = clean_channel_name(orig_name)
                        if cleaned not in channel_name_map:
                            channel_name_map[cleaned] = orig_name
                    
                    
                    matched_values = []
                    for ch in valid_channels:
                        orig_name = channel_name_map.get(ch, ch)
                        matched = False
                        
                        if orig_name in channel_names:
                            orig_idx = channel_names.index(orig_name)
                            if orig_idx < len(values):
                                matched_values.append(values[orig_idx])
                                matched = True
                            else:
                                matched_values.append(0.0)
                        elif ch in channel_names:
                            orig_idx = channel_names.index(ch)
                            if orig_idx < len(values):
                                matched_values.append(values[orig_idx])
                                matched = True
                            else:
                                matched_values.append(0.0)
                        else:
                            ch_upper = ch.upper()
                            for i, cn in enumerate(channel_names):
                                if cn.upper() == ch_upper and i < len(values):
                                    matched_values.append(values[i])
                                    matched = True
                                    break
                            if not matched:
                                matched_values.append(0.0)
                    
                    values = np.array(matched_values, dtype=float)
                    
                    # Check if all values are zero
                    if len(values) == 0:
                        logger.warning(f"No values extracted for band {band} ({epoch or 'all'}) in grid topomap. Channel names: {channel_names[:5]}")
                        ax.axis('off')
                        continue
                    
                    if np.max(values) <= 0:
                        logger.warning(f"All values are zero for band {band} ({epoch or 'all'}) in grid topomap. Channel names: {channel_names[:5]}, values range: [{np.min(values):.4f}, {np.max(values):.4f}]")
                        ax.axis('off')
                        continue

                    # Need at least 4 channels for topomap interpolation (Delaunay)
                    if len(positions) < 4:
                        logger.debug(f"Skipping grid topomap {band} ({epoch or 'all'}): need 4+ channels, have {len(positions)}")
                        ax.axis('off')
                        continue
                    
                    # Interpolate
                    resolution = getattr(self.config, 'get_topomap_resolution', lambda: self.config.get('topomaps.resolution', 128))()
                    Xi, Yi, Zi = self._clinical_interpolation(values, positions, resolution)
                    
                    # Plot
                    vmin, vmax = np.percentile(values, [5, 95])
                    # Ensure vmax > vmin to avoid contour level errors
                    if vmax <= vmin:
                        mag = max(float(np.percentile(np.abs(values), 95)), float(np.max(np.abs(values))), 1e-30)
                        vmax = vmin + max(mag * 0.02, 1e-30)
                    vmin, vmax = _expand_topomap_vlim_for_grid(
                        vmin, vmax, Zi, is_zscore=False,
                        zmin=self._zscore_vmin, zmax=self._zscore_vmax,
                    )
                    
                    levels = np.linspace(vmin, vmax, 8)
                    levels = np.unique(levels)
                    # Ensure we have at least 2 levels
                    if len(levels) < 2:
                        levels = np.array([vmin, vmax])
                    # Ensure levels are strictly increasing
                    if len(levels) > 1 and not np.all(np.diff(levels) > 0):
                        levels = np.linspace(vmin, vmax, max(2, len(levels)))
                        levels = np.unique(levels)
                    
                    cmap = _power_topomap_colormap()
                    ax.contourf(Xi, Yi, Zi, levels=levels, cmap=cmap,
                               vmin=vmin, vmax=vmax, extend='both')
                    
                    # Head outline
                    head_circle = plt.Circle((0, 0), 1.0, fill=False,
                                            color=self.theme.NEON_CYAN, linewidth=1.5, alpha=0.8)
                    ax.add_patch(head_circle)
                    
                    # Sensors (always show)
                    ax.scatter(positions[:, 0], positions[:, 1],
                             c=self.theme.get_foreground_color(), s=30,
                             edgecolors=self.theme.get_background_color(),
                             linewidths=0.6, zorder=10, alpha=0.85)
                    
                    # Add channel labels (always show)
                    for i, (pos, ch) in enumerate(zip(positions, valid_channels)):
                        dist_from_center = np.sqrt(pos[0]**2 + pos[1]**2)
                        if dist_from_center > 0.8:
                            label_offset = -0.12
                            if abs(pos[0]) > 0.8:
                                ha = 'right' if pos[0] < 0 else 'left'
                            else:
                                ha = 'center'
                        else:
                            label_offset = -0.08
                            ha = 'center'
                        
                        ax.text(pos[0], pos[1] + label_offset, ch,
                               ha=ha, va='top',
                               color=self.theme.get_region_color(ch), fontsize=8, fontweight='bold',
                               zorder=11)
                    
                    ax.set_xlim(-1.3, 1.3)
                    ax.set_ylim(-1.3, 1.3)
                    ax.set_aspect('equal')
                    ax.axis('off')
                    ax.set_title(band.capitalize(), color=self.theme.get_foreground_color(),
                               fontsize=14, fontweight='bold')
                    
                except Exception as e:
                    logger.error(f"Error generating grid topomap for {band}: {e}", exc_info=True)
            
            # Hide unused subplots
            for idx in range(n_bands, len(axes)):
                axes[idx].axis('off')
            
            # Optional Data quality callout (same idea as Mahalanobis)
            qc_text = format_qc_callout_plain(qc_summary, ica_applied_before_metrics)
            if qc_text:
                fig.text(0.02, 0.02, "Data quality: " + qc_text,
                         fontsize=8, color=self.theme.get_foreground_color(), ha='left', va='bottom',
                         wrap=True, transform=fig.transFigure,
                         bbox=dict(boxstyle='round,pad=0.2', facecolor=self.theme.get_background_color(),
                                   alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=0.8))
            
            plt.tight_layout()
            
            # Save
            if epoch:
                filename = f"topomap_grid_{epoch.lower()}.png"
            else:
                filename = "topomap_grid.png"
            
            filepath = output_dir / filename
            try:
                self._save_fig_with_fallback(fig, filepath)
            except Exception:
                plt.close(fig)
                raise
            grid_paths.append(filepath)
            logger.info(f"Generated topomap grid ({epoch or 'all'}): {filepath}")
        
        # Return the first grid path (or None if none generated)
        # The report generator will handle multiple paths
        return grid_paths[0] if grid_paths else None
    
    def _create_topomap_html_wrapper(self, image_path: Path, band: str, epoch: Optional[str],
                                     values: np.ndarray, channel_names: List[str],
                                     output_dir: Path) -> Optional[Path]:
        """Create HTML wrapper for topomap with additional information"""
        try:
            # Calculate summary statistics
            non_zero_values = values[values != 0.0]
            if len(non_zero_values) == 0:
                return None
            
            mean_val = float(np.mean(non_zero_values))
            max_val = float(np.max(non_zero_values))
            min_val = float(np.min(non_zero_values))
            std_val = float(np.std(non_zero_values))

            def _fmt(v: float) -> str:
                """Auto-format: fixed for large values, scientific for tiny ones."""
                if v == 0.0:
                    return "0.0000"
                if abs(v) >= 0.001:
                    return f"{v:.4f}"
                return f"{v:.4e}"
            
            # Get frequency range
            freq_range = get_band_frequency_range(band, self._band_ranges)
            
            # Generate clinical insights with location-specific interpretation
            insights = []
            clinical_keys = []
            
            # Find channels with highest and lowest values
            if len(channel_names) > 0:
                sorted_indices = np.argsort(values)[::-1]
                top_channels = [channel_names[i] for i in sorted_indices[:3] if values[i] > 0]
                bottom_channels = [channel_names[i] for i in sorted_indices[-3:] if values[i] > 0]
                
                if top_channels:
                    insights.append(f"• <b>Highest activity:</b> {', '.join(top_channels)}")
                    # Generate clinical interpretation for top channels
                    for ch in top_channels[:2]:  # Top 2 for brevity
                        # Determine if this is "high" based on comparison to mean
                        if values[channel_names.index(ch)] > mean_val * 1.5:
                            clinical_key = self._get_clinical_interpretation(ch, band, 'high', epoch)
                            if clinical_key:
                                clinical_keys.append(clinical_key)
                
                if bottom_channels and min_val < mean_val * 0.5:
                    insights.append(f"• <b>Lowest activity:</b> {', '.join(bottom_channels)}")
                    # Generate clinical interpretation for bottom channels
                    for ch in bottom_channels[:1]:  # Top 1 for brevity
                        clinical_key = self._get_clinical_interpretation(ch, band, 'low', epoch)
                        if clinical_key:
                            clinical_keys.append(clinical_key)
            
            # Check for asymmetry patterns
            left_channels = [ch for ch in channel_names if any(ch.upper().endswith(s) for s in ['1', '3', '7']) or ch.upper() in ['FP1', 'F3', 'F7', 'C3', 'P3', 'O1', 'T7']]
            right_channels = [ch for ch in channel_names if any(ch.upper().endswith(s) for s in ['2', '4', '8']) or ch.upper() in ['FP2', 'F4', 'F8', 'C4', 'P4', 'O2', 'T8']]
            
            if left_channels and right_channels:
                left_indices = [i for i, ch in enumerate(channel_names) if ch in left_channels]
                right_indices = [i for i, ch in enumerate(channel_names) if ch in right_channels]
                
                if left_indices and right_indices:
                    left_mean = np.mean([values[i] for i in left_indices if i < len(values)])
                    right_mean = np.mean([values[i] for i in right_indices if i < len(values)])
                    
                    if abs(left_mean - right_mean) > mean_val * 0.3:
                        if left_mean > right_mean:
                            insights.append(f"• <b>Left hemisphere</b> shows higher {band} activity")
                            clinical_keys.append({
                                'location': 'Left Hemisphere',
                                'pattern': f'Left > Right {band.capitalize()}',
                                'interpretation': self._get_hemispheric_interpretation(band, 'left', epoch),
                                'clinical_context': 'Hemispheric asymmetry detected',
                                'neurofeedback': 'Coherence training, balance protocols'
                            })
                        else:
                            insights.append(f"• <b>Right hemisphere</b> shows higher {band} activity")
                            clinical_keys.append({
                                'location': 'Right Hemisphere',
                                'pattern': f'Right > Left {band.capitalize()}',
                                'interpretation': self._get_hemispheric_interpretation(band, 'right', epoch),
                                'clinical_context': 'Hemispheric asymmetry detected',
                                'neurofeedback': 'Coherence training, balance protocols'
                            })
            
            if max_val > mean_val * 2:
                insights.append("• <b>Peak activity</b> detected in some regions")
            if std_val > mean_val * 0.5:
                insights.append("• <b>High variability</b> across channels")
            
            if not insights:
                insights.append("• Activity patterns within normal range")
            
            # Create HTML
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>EEG Paradox Decoder - {band.upper()} Topomap</title>
    <style>
        body {{ font-family: Arial, sans-serif; background: #0a0a0a; color: #ffffff; margin: 0; padding: 20px; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 20px; color: #00F0FF; }}
        .content {{ display: flex; gap: 20px; flex-wrap: wrap; }}
        .image-section {{ flex: 1; min-width: 600px; }}
        .image-section img {{ width: 100%; height: auto; border: 2px solid #00F0FF; border-radius: 8px; }}
        .info-section {{ flex: 0 0 350px; background: rgba(0, 0, 0, 0.8); border: 2px solid #00F0FF; border-radius: 8px; padding: 20px; }}
        .info-section h3 {{ color: #00F0FF; margin-top: 0; }}
        .stat-box {{ background: rgba(0, 240, 255, 0.1); padding: 15px; border-radius: 4px; margin-bottom: 15px; }}
        .insight-box {{ background: rgba(0, 255, 136, 0.1); padding: 15px; border-radius: 4px; }}
        .button-group {{ margin-top: 20px; display: flex; gap: 10px; }}
        .btn {{ background: #00F0FF; color: #000; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; }}
        .btn:hover {{ background: #00D0E0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>EEG Paradox Decoder - {band.upper()} Power Topomap</h1>
            <p>{freq_range} • {epoch.upper() if epoch else 'All Epochs'}</p>
        </div>
        <div class="content">
            <div class="image-section">
                <img src="{image_path.name}" alt="{band} Topomap">
                <div class="button-group">
                    <a href="{image_path.name}" download class="btn">📥 Download Image</a>
                    <button onclick="window.print()" class="btn">🖨️ Print</button>
                </div>
            </div>
            <div class="info-section">
                <h3>📊 Summary Statistics</h3>
                <div class="stat-box">
                    <p><b>Mean:</b> {_fmt(mean_val)}</p>
                    <p><b>Peak:</b> {_fmt(max_val)}</p>
                    <p><b>Min:</b> {_fmt(min_val)}</p>
                    <p><b>Std Dev:</b> {_fmt(std_val)}</p>
                    <p><b>Active Channels:</b> {len(non_zero_values)}/{len(values)}</p>
                </div>
                <h3>💡 Clinical Insights</h3>
                <div class="insight-box">
                    {'<br>'.join(insights)}
                </div>
                <h3>📊 How to Read This Map</h3>
                <div class="insight-box">
                    • <b>Color intensity</b> shows power level at each electrode<br>
                    • <b>Warmer colors</b> (red/orange) = Higher power<br>
                    • <b>Cooler colors</b> (blue/purple) = Lower power<br>
                    • <b>Frequency range:</b> {freq_range}<br>
                    • <b>Unit:</b> Power (µV²) - squared amplitude<br><br>
                    <b>🎯 Interpretation:</b><br>
                    • Compare left vs right hemispheres<br>
                    • Look for focal areas of high/low activity<br>
                    • Check for symmetry patterns<br>
                    • Review with clinical context
                </div>
                {self._generate_clinical_keys_section(band, epoch, clinical_keys) if clinical_keys else ''}
            </div>
        </div>
    </div>
</body>
</html>"""
            
            # Save HTML file
            html_filename = image_path.stem + '.html'
            html_filepath = output_dir / html_filename
            
            with open(html_filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return html_filepath
            
        except Exception as e:
            logger.warning(f"Failed to create HTML wrapper for topomap: {e}")
            return None
    
    def _init_clinical_interpretations(self):
        """Initialize comprehensive clinical interpretation database from JSON"""
        import json
        data_path = Path(__file__).parent / 'data' / 'clinical_interpretations.json'
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.clinical_db = {
                tuple(None if p == 'null' else p for p in k.split('|')): v
                for k, v in data.get('clinical_db', {}).items()
            }
            self.asymmetry_db = {
                tuple(k.split('|')): v
                for k, v in data.get('asymmetry_db', {}).items()
            }
        except Exception as e:
            logger.warning("Could not load clinical interpretations: %s", e)
            self.clinical_db = {}
            self.asymmetry_db = {}
    
    def _get_clinical_interpretation(self, channel: str, band: str, direction: str, epoch: Optional[str]) -> Optional[Dict[str, str]]:
        """
        Get clinical interpretation for a specific channel/band combination
        
        Args:
            channel: Channel name (e.g., 'F3', 'Cz')
            band: Frequency band (e.g., 'alpha', 'beta')
            direction: 'high' or 'low'
            epoch: Epoch type ('EO', 'EC', etc.)
            
        Returns:
            Dictionary with clinical interpretation or None
        """
        channel_upper = channel.upper()
        band_lower = band.lower()
        direction_lower = direction.lower()
        
        # Define region for channel
        region = None
        if channel_upper in ['FP1', 'FP2', 'F3', 'F4', 'F7', 'F8', 'FZ']:
            region = 'frontal'
        elif channel_upper in ['C3', 'C4', 'CZ']:
            region = 'central'
        elif channel_upper in ['P3', 'P4', 'P7', 'P8', 'PZ']:
            region = 'parietal'
        elif channel_upper in ['O1', 'O2', 'OZ']:
            region = 'occipital'
        elif channel_upper in ['T7', 'T8']:
            region = 'temporal'
        
        # Try specific channel first, then region-level, then general
        keys_to_try = [
            (band_lower, direction_lower, region, channel_upper),
            (band_lower, direction_lower, region, None),
            (band_lower, direction_lower, None, None),
        ]
        
        for key in keys_to_try:
            if key in self.clinical_db:
                result = self.clinical_db[key].copy()
                result['location'] = channel
                return result
        
        return None
    
    def _get_hemispheric_interpretation(self, band: str, hemisphere: str, epoch: Optional[str]) -> str:
        """Get clinical interpretation for hemispheric asymmetry"""
        band_lower = band.lower()
        key = (band_lower, hemisphere)
        return self.asymmetry_db.get(key, f'{hemisphere.capitalize()} hemisphere {band} asymmetry - requires clinical correlation')
    
    def _generate_comparison_clinical_keys(self, band: str, eo_keys: List[Dict[str, str]], ec_keys: List[Dict[str, str]]) -> str:
        """Generate clinical keys section for comparison view"""
        if not eo_keys and not ec_keys:
            return ""
        
        eo_html = ""
        if eo_keys:
            # Show all keys, not just first 3
            for i, key in enumerate(eo_keys, 1):
                # Support both 'pattern' and 'location' keys
                location = key.get('location') or key.get('pattern', '')
                interpretation = key.get('interpretation', '')
                clinical_context = key.get('clinical_context', '')
                eo_html += f"""
                    <div style="margin-bottom: 0.75rem; padding: 0.75rem; background: rgba(0, 255, 136, 0.1); border-left: 3px solid #00FF88; border-radius: 4px;">
                        <div style="font-weight: bold; color: #00FF88; margin-bottom: 0.25rem; font-size: 0.95rem;">{location}</div>
                        <div style="font-size: 0.85em; color: rgba(255, 255, 255, 0.9); line-height: 1.4;">{interpretation}</div>
                        {f'<div style="font-size: 0.8em; color: rgba(0, 255, 136, 0.9); margin-top: 0.25rem; font-style: italic;">{clinical_context}</div>' if clinical_context else ''}
                    </div>
                """
        else:
            eo_html = '<p style="color: rgba(255,255,255,0.6); font-size: 0.9em;">No specific clinical keys identified for EO state.</p>'
        
        ec_html = ""
        if ec_keys:
            # Show all keys, not just first 3
            for i, key in enumerate(ec_keys, 1):
                # Support both 'pattern' and 'location' keys
                location = key.get('location') or key.get('pattern', '')
                interpretation = key.get('interpretation', '')
                clinical_context = key.get('clinical_context', '')
                ec_html += f"""
                    <div style="margin-bottom: 0.75rem; padding: 0.75rem; background: rgba(0, 255, 136, 0.1); border-left: 3px solid #00FF88; border-radius: 4px;">
                        <div style="font-weight: bold; color: #00FF88; margin-bottom: 0.25rem; font-size: 0.95rem;">{location}</div>
                        <div style="font-size: 0.85em; color: rgba(255, 255, 255, 0.9); line-height: 1.4;">{interpretation}</div>
                        {f'<div style="font-size: 0.8em; color: rgba(0, 255, 136, 0.9); margin-top: 0.25rem; font-style: italic;">{clinical_context}</div>' if clinical_context else ''}
                    </div>
                """
        else:
            ec_html = '<p style="color: rgba(255,255,255,0.6); font-size: 0.9em;">No specific clinical keys identified for EC state.</p>'
        
        return f'''
        <div class="clinical-keys-section" style="margin-top: 30px; margin-bottom: 30px;">
            <h3 style="color: #00FF88; margin-bottom: 1rem; font-size: 1.3em;">🔑 Clinical Interpretation Keys</h3>
            <p style="color: rgba(255, 255, 255, 0.7); font-size: 0.9em; margin-bottom: 1rem;">Location-specific clinical interpretations based on power distribution patterns and detection results:</p>
            <div class="clinical-keys-grid">
                <div class="clinical-key-box">
                    <h4>👁️ Eyes Open (EO) Findings</h4>
                    <div style="padding-top: 0.5rem;">
                        {eo_html}
                    </div>
                </div>
                <div class="clinical-key-box">
                    <h4>👁️‍🗨️ Eyes Closed (EC) Findings</h4>
                    <div style="padding-top: 0.5rem;">
                        {ec_html}
                    </div>
                </div>
            </div>
        </div>
        '''
    
    def _generate_clinical_keys_section(self, band: str, epoch: Optional[str], clinical_keys: List[Dict[str, str]]) -> str:
        """Generate HTML section for clinical interpretation keys"""
        if not clinical_keys:
            return ""
        
        epoch_label = epoch.upper() if epoch else "All Epochs"
        band_label = band.upper()
        
        html = f"""
                <h3>🔑 Clinical Interpretation Keys</h3>
                <div class="insight-box" style="background: rgba(255, 165, 0, 0.1); border-left: 3px solid #FFA500; max-height: 400px; overflow-y: auto;">
                    <p style="margin-top: 0;"><b>Band:</b> {band_label} ({epoch_label})</p>
                    <p style="font-size: 0.9em; color: rgba(255, 255, 255, 0.8); margin-bottom: 0.5rem;">
                        <b>⚠️ Note:</b> These interpretations are pattern-based observations, not diagnoses. 
                        Clinical correlation with patient history and symptoms is essential.
                    </p>
                    <div style="margin-top: 1rem;">
        """
        
        for i, key in enumerate(clinical_keys[:5], 1):  # Limit to top 5
            location = key.get('location', 'Unknown')
            pattern = key.get('pattern', '')
            interpretation = key.get('interpretation', '')
            clinical_context = key.get('clinical_context', '')
            neurofeedback = key.get('neurofeedback', '')
            
            html += f"""
                        <div style="margin-bottom: 1rem; padding: 0.75rem; background: rgba(0, 0, 0, 0.3); border-radius: 4px;">
                            <div style="color: #FFA500; font-weight: bold; margin-bottom: 0.25rem;">{i}. {pattern}</div>
                            <div style="font-size: 0.85em; color: rgba(255, 255, 255, 0.9); line-height: 1.4; margin-bottom: 0.5rem;">
                                {interpretation}
                            </div>
            """
            
            if clinical_context:
                html += f"""
                            <div style="font-size: 0.8em; color: rgba(0, 255, 136, 0.9); margin-bottom: 0.25rem;">
                                <b>Clinical Context:</b> {clinical_context}
                            </div>
                """
            
            if neurofeedback:
                html += f"""
                            <div style="font-size: 0.8em; color: rgba(0, 240, 255, 0.9);">
                                <b>Neurofeedback:</b> {neurofeedback}
                            </div>
                """
            
            html += """
                        </div>
            """
        
        html += """
                    </div>
                </div>
        """
        
        return html
    
    def generate_coherence_topomaps(self, coherence_metrics: Dict[str, Any],
                                   output_dir: Path,
                                   subject_id: str,
                                   session_id: str) -> Dict[str, Path]:
        """
        Generate coherence topomaps showing connectivity patterns
        
        Args:
            coherence_metrics: Dictionary containing network_coherence and all_pairs_coherence
            output_dir: Output directory for images
            subject_id: Subject identifier
            session_id: Session identifier
            
        Returns:
            Dictionary mapping band_epoch names to file paths
        """
        if not self.config.get('coherence.generate_topomaps', False):
            return {}
        
        output_paths = {}
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Get all pairs coherence data
        all_pairs_coherence = coherence_metrics.get('all_pairs_coherence', {})
        if not all_pairs_coherence:
            logger.info("No all_pairs_coherence data available for topomap generation")
            return {}
        
        # Extract channel names from all pairs
        all_channels = set()
        for segment_key, pairs_data in all_pairs_coherence.items():
            if isinstance(pairs_data, dict):
                for pair_key in pairs_data.keys():
                    # Pair keys are typically "CH1-CH2" format
                    if '-' in pair_key:
                        ch1, ch2 = pair_key.split('-', 1)
                        all_channels.add(ch1.strip())
                        all_channels.add(ch2.strip())
        
        if not all_channels:
            logger.warning("No channel pairs found in coherence data")
            return {}
        
        # Get standard channel positions
        channel_names = sorted(list(all_channels))
        positions = []
        valid_channels = []
        
        for ch in channel_names:
            ch_clean = clean_channel_name(ch)
            if ch_clean in CLINICAL_1020_POSITIONS:
                pos = CLINICAL_1020_POSITIONS[ch_clean]
                positions.append(pos)
                valid_channels.append(ch)
        
        if len(valid_channels) < 3:
            logger.warning(f"Insufficient valid channels ({len(valid_channels)}) for coherence topomap")
            return {}
        
        positions = np.array(positions)
        
        # Process each segment/epoch
        bands = ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma', 'SMR', 'HiBeta']
        
        for segment_key, pairs_data in all_pairs_coherence.items():
            if not isinstance(pairs_data, dict):
                continue
            
            # Extract epoch from segment key (e.g., "eo_epoch" -> "EO")
            epoch = None
            if 'eo' in segment_key.lower():
                epoch = 'EO'
            elif 'ec' in segment_key.lower():
                epoch = 'EC'
            
            epoch_suffix = f"_{epoch.lower()}" if epoch else ""
            
            # Aggregate coherence per channel for each band
            for band in bands:
                channel_coherence = np.zeros(len(valid_channels))
                channel_counts = np.zeros(len(valid_channels))
                
                for pair_key, band_data in pairs_data.items():
                    if not isinstance(band_data, dict):
                        continue
                    
                    band_value = band_data.get(band, band_data.get(band.lower(), 0.0))
                    if isinstance(band_value, (int, float)) and band_value > 0:
                        # Parse channel pair
                        if '-' in pair_key:
                            ch1, ch2 = pair_key.split('-', 1)
                            ch1 = ch1.strip()
                            ch2 = ch2.strip()
                            
                            # Add coherence to both channels
                            for idx, ch in enumerate(valid_channels):
                                if ch == ch1 or ch == ch2:
                                    channel_coherence[idx] += band_value
                                    channel_counts[idx] += 1
                
                # Average coherence per channel
                for idx in range(len(valid_channels)):
                    if channel_counts[idx] > 0:
                        channel_coherence[idx] /= channel_counts[idx]
                
                # Only generate if we have meaningful data
                if np.max(channel_coherence) > 0:
                    band_label = band.capitalize()
                    title = f"Coherence - {band_label}"
                    if epoch:
                        title += f" ({epoch})"
                    
                    fig = self._plot_topomap(
                        channel_coherence,
                        valid_channels,
                        title=title,
                        is_zscore=False,
                        frequency_band=band_label,
                        condition=epoch or '',
                        unit_label="Coherence"
                    )
                    
                    if fig:
                        filename = f"topomap_coherence_{band.lower()}{epoch_suffix}.png"
                        filepath = output_dir / filename
                        self._save_fig_with_fallback(
                            fig, filepath,
                            facecolor='black', edgecolor='none'
                        )
                        key = f"coherence_{band.lower()}{epoch_suffix}"
                        output_paths[key] = filepath
                        logger.info(f"Generated coherence topomap: {filename}")
        
        return output_paths
