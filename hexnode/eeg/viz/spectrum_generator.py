#!/usr/bin/env python3
"""
Spectrum Generator

Generates FFT power spectra histograms in WinEEG-style grid layout.

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


import json
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import logging

from hexnode.eeg.viz.theme_manager import get_theme_manager, CLINICAL_1020_POSITIONS
from hexnode.eeg.viz.visualization_config import get_visualization_config
from hexnode.eeg.viz.utils import extract_all_sites, is_nested_structure, get_epochs_for_site, clean_channel_name, get_all_available_epochs, format_qc_callout_plain

logger = logging.getLogger(__name__)

# Fixed 5×5 scalp layout (common WinEEG-style 19-channel 10–20); None = empty cell
WINEEG_1020_SLOTS: Tuple[Tuple[Optional[str], ...], ...] = (
    (None, "Fp1", None, "Fp2", None),
    ("F7", "F3", "Fz", "F4", "F8"),
    ("T7", "C3", "Cz", "C4", "T8"),
    ("P7", "P3", "Pz", "P4", "P8"),
    (None, "O1", None, "O2", None),
)


class SpectrumGenerator:
    """Generates FFT power spectra histograms"""
    
    def __init__(self, config=None):
        """
        Initialize spectrum generator
        
        Args:
            config: VisualizationConfig instance (optional)
        """
        self.config = config or get_visualization_config()
        self.theme = get_theme_manager()
    
    def _calculate_psd(self, channel_data: np.ndarray, sfreq: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate power spectral density using Welch's method
        
        Args:
            channel_data: 1D array of EEG samples
            sfreq: Sampling frequency
            
        Returns:
            Tuple of (frequencies, psd)
        """
        n = len(channel_data)
        nperseg = min(max(256, min(2048, n // 4)), n)
        if nperseg < 16:
            logger.warning(f"Segment too short for PSD: {n} samples")
            return np.array([]), np.array([])
        
        noverlap = nperseg // 2
        
        freqs, psd = signal.welch(
            channel_data,
            fs=sfreq,
            nperseg=nperseg,
            noverlap=noverlap,
            window='hann',
            detrend='constant',
            scaling='density'
        )
        
        return freqs, psd
    
    def _sort_channels_spatially(self, channel_names: List[str]) -> List[Tuple[str, float, float]]:
        """
        Sort channels by their spatial position (Y: anterior-posterior, X: left-right)
        
        Spectrum grid alignment overrides:
        - Fp1 above F3 (left), Fp2 above F4 (right), open space above Fz
        - O2 aligns below P4
        
        Args:
            channel_names: List of channel names
            
        Returns:
            List of (channel_name, x_pos, y_pos) tuples sorted by position
        """
        channel_positions = []
        # Spectrum-specific: Fp1 above F3, Fp2 above F4, O2 below P4.
        # Use x=0.55 for Fp2/O2 so they map to col 3 (F4/P4) not col 2 (Fz) in 5-col grid.
        SPECTRUM_X_OVERRIDES = {'Fp1': -0.45, 'FP1': -0.45, 'Fp2': 0.55, 'FP2': 0.55, 'O2': 0.55}
        
        for ch_name in channel_names:
            clean_ch = clean_channel_name(ch_name)
            
            # Get position from CLINICAL_1020_POSITIONS
            if clean_ch in CLINICAL_1020_POSITIONS:
                x, y = CLINICAL_1020_POSITIONS[clean_ch]
            else:
                # Try uppercase
                clean_upper = clean_ch.upper()
                if clean_upper in CLINICAL_1020_POSITIONS:
                    x, y = CLINICAL_1020_POSITIONS[clean_upper]
                else:
                    # Estimate position
                    pos = self.theme._estimate_position(clean_ch)
                    x, y = pos
            
            # Apply spectrum grid alignment overrides (Fp1 above F3, Fp2 above F4, O2 below P4)
            if clean_ch in SPECTRUM_X_OVERRIDES:
                x = SPECTRUM_X_OVERRIDES[clean_ch]
            elif clean_ch.upper() in SPECTRUM_X_OVERRIDES:
                x = SPECTRUM_X_OVERRIDES[clean_ch.upper()]
            
            channel_positions.append((ch_name, x, y))
        
        # Sort by Y (anterior-posterior: high Y = frontal, low Y = occipital)
        # Then by X (left-right: negative X = left, positive X = right)
        channel_positions.sort(key=lambda item: (-item[2], item[1]))  # -y for descending, then x
        
        return channel_positions
    
    def _create_spatial_grid_layout(self, sorted_channels: List[Tuple[str, float, float]]) -> Dict[str, Any]:
        """
        Create a grid layout that matches the spatial arrangement of electrodes
        
        Args:
            sorted_channels: List of (channel_name, x_pos, y_pos) tuples sorted by position
            
        Returns:
            Dictionary with 'n_rows', 'n_cols', and 'grid' (2D array)
        """
        if not sorted_channels:
            return {'n_rows': 1, 'n_cols': 1, 'grid': [[None]]}
        
        # Group channels by Y position (anterior-posterior rows)
        y_groups = {}
        for ch_name, x, y in sorted_channels:
            # Round Y to nearest 0.1 to group similar positions
            y_key = round(y, 1)
            if y_key not in y_groups:
                y_groups[y_key] = []
            y_groups[y_key].append((ch_name, x, y))
        
        # Sort Y groups (frontal to occipital)
        sorted_y_groups = sorted(y_groups.items(), reverse=True)  # High Y (frontal) first
        
        # Determine grid dimensions
        n_rows = len(sorted_y_groups)
        n_cols = max(len(group) for _, group in sorted_y_groups)
        
        # Ensure at least 5 columns for standard 10-20 layout
        if n_cols < 5:
            n_cols = 5
        
        # Create grid
        grid = [[None for _ in range(n_cols)] for _ in range(n_rows)]
        
        # Fill grid with channels using actual X positions for proper alignment
        # Get global X range across all channels for consistent mapping
        all_x_positions = [x for _, x, _ in sorted_channels]
        if len(all_x_positions) > 0:
            global_min_x = min(all_x_positions)
            global_max_x = max(all_x_positions)
            global_x_range = global_max_x - global_min_x if global_max_x > global_min_x else 2.0
        else:
            global_min_x = -1.0
            global_max_x = 1.0
            global_x_range = 2.0
        
        # Fill grid with channels
        for row_idx, (y_key, group) in enumerate(sorted_y_groups):
            # Sort group by X position (left to right)
            group_sorted = sorted(group, key=lambda item: item[1])  # Sort by x
            
            # Map X positions to grid columns using global X range
            # This ensures right-side channels (Fp2, F8, P8, O2) are positioned correctly
            for ch_name, x, y in group_sorted:
                # Normalize X position to 0-1 range using global range
                # This ensures consistent positioning across all rows
                normalized_x = (x - global_min_x) / global_x_range
                
                # Map to grid column (0 to n_cols-1)
                # Use the full grid width for proper alignment
                col_idx = int(normalized_x * (n_cols - 1))
                
                # Ensure column index is within bounds
                col_idx = max(0, min(col_idx, n_cols - 1))
                
                # If column is already occupied, try adjacent columns
                # For right-side channels (positive X), prefer moving right
                if grid[row_idx][col_idx] is None:
                    grid[row_idx][col_idx] = ch_name
                else:
                    # For right-side channels, try right first
                    if x > 0 and col_idx < n_cols - 1 and grid[row_idx][col_idx + 1] is None:
                        grid[row_idx][col_idx + 1] = ch_name
                    # For left-side channels or if right is occupied, try left
                    elif col_idx > 0 and grid[row_idx][col_idx - 1] is None:
                        grid[row_idx][col_idx - 1] = ch_name
                    # If both adjacent are occupied, use the calculated position anyway
                    else:
                        grid[row_idx][col_idx] = ch_name
        
        return {
            'n_rows': n_rows,
            'n_cols': n_cols,
            'grid': grid
        }

    def _create_wineeog_1020_grid(self, channel_names: List[str]) -> Dict[str, Any]:
        """Map recording channels onto a fixed WinEEG-like 5×5 grid (19 standard sites)."""
        grid: List[List[Optional[str]]] = [[None for _ in range(5)] for _ in range(5)]
        used: set[str] = set()

        def slot_to_original(slot: str) -> Optional[str]:
            want = clean_channel_name(slot)
            for orig in channel_names:
                if clean_channel_name(orig) == want:
                    return orig
            return None

        for r, row in enumerate(WINEEG_1020_SLOTS):
            for c, slot in enumerate(row):
                if slot is None:
                    continue
                orig = slot_to_original(slot)
                if orig is not None and orig not in used:
                    grid[r][c] = orig
                    used.add(orig)
        return {"n_rows": 5, "n_cols": 5, "grid": grid}
    
    def generate_power_spectra(self, metrics_by_site: Dict[str, Any],
                               raw_data: Optional[Any] = None,
                               sfreq: float = 250.0,
                               output_dir: Path = None,
                               subject_id: str = "",
                               session_id: str = "",
                               qc_summary: Optional[Dict[str, Any]] = None,
                               ica_applied_before_metrics: bool = False,
                               export_band_power: bool = False) -> Optional[Path]:
        """
        Generate FFT power spectra histogram grid
        
        Args:
            metrics_by_site: Dictionary of metrics by site (may contain PSD data)
            raw_data: Optional MNE Raw object or dict of channel arrays
            sfreq: Sampling frequency (if raw_data provided)
            output_dir: Output directory for images
            subject_id: Subject identifier
            session_id: Session identifier
            qc_summary: Optional session QC summary for Data quality note on figure
            ica_applied_before_metrics: Whether ICA was applied before metrics
            export_band_power: If True, write power_spectra_band_power_{subject}_{session}.json
            
        Returns:
            Path to generated spectrum image or None
        """
        if not self.config.are_power_spectra_enabled():
            logger.info("Power spectra disabled in configuration")
            return None
        
        try:
            # Get channel names; exclude reference electrodes (A1, A2) - they often have anomalous power
            all_sites = extract_all_sites(metrics_by_site)
            channel_names = [
                ch for ch in all_sites
                if clean_channel_name(ch).upper() not in ('A1', 'A2')
            ]
            # Fallback: if metrics_by_site has very few sites but raw_data has many channels, use raw
            # (handles cases where metrics_by_site keys are collapsed or from single-site aggregation)
            if len(channel_names) < 4 and raw_data is not None and hasattr(raw_data, 'ch_names'):
                raw_chs = [ch for ch in raw_data.ch_names
                           if clean_channel_name(ch).upper() not in ('A1', 'A2')]
                if len(raw_chs) > len(channel_names):
                    channel_names = raw_chs
                    logger.info(f"Using {len(channel_names)} channels from raw_data (metrics_by_site had {len(all_sites)})")
            if len(channel_names) == 0:
                logger.warning("No channels found for spectrum generation")
                return None
            
            freq_range = self.config.get('power_spectra.frequency_range', [0, 50])
            freq_min, freq_max = freq_range[0], freq_range[1]
            
            # Frequency band colors - use theme manager method
            band_colors = {}
            for band in ['delta', 'theta', 'alpha', 'beta', 'gamma', 'smr', 'hibeta']:
                band_colors[band] = self.theme.get_frequency_band_color(band)
            
            band_ranges = {
                'delta': (0.5, 4.0),
                'theta': (4.0, 8.0),
                'alpha': (8.0, 13.0),
                'smr': (12.0, 15.0),
                'beta': (13.0, 30.0),
                'hibeta': (20.0, 30.0),
                'gamma': (30.0, 40.0),
            }
            
            # Determine epochs to process (if nested structure)
            is_nested = is_nested_structure(metrics_by_site)
            epochs_to_process = []
            
            if is_nested:
                # Get all available epochs
                epochs_to_process = get_all_available_epochs(metrics_by_site)
                if not epochs_to_process:
                    epochs_to_process = [None]
            else:
                epochs_to_process = [None]
            
            # Generate spectra for each epoch
            all_spectra_paths = []
            
            for epoch in epochs_to_process:
                # Grid layout: WinEEG-style fixed 5×5 (default) or legacy auto spatial packing
                layout_mode = (self.config.get("power_spectra.layout", "wineeog_1020") or "wineeog_1020").lower()
                if layout_mode == "wineeog_1020":
                    grid_layout = self._create_wineeog_1020_grid(channel_names)
                else:
                    sorted_channels = self._sort_channels_spatially(channel_names)
                    grid_layout = self._create_spatial_grid_layout(sorted_channels)
                n_rows, n_cols = grid_layout['n_rows'], grid_layout['n_cols']
                channel_grid = grid_layout['grid']  # 2D array mapping (row, col) -> channel_name
                
                # Create a mapping from cleaned names back to original names for lookup
                # This handles case mismatches (e.g., "Cz" -> "CZ")
                cleaned_to_original = {}
                for orig_name in channel_names:
                    cleaned = clean_channel_name(orig_name)
                    if cleaned not in cleaned_to_original:
                        cleaned_to_original[cleaned] = orig_name
                
                # Create figure with appropriate size
                fig, axes = plt.subplots(n_rows, n_cols, 
                                       figsize=(3.5 * n_cols, 2.8 * n_rows),
                                       facecolor=self.theme.get_background_color())
                fig.patch.set_facecolor(self.theme.get_background_color())
                
                # Handle axes configuration
                if n_rows == 1 and n_cols == 1:
                    axes = np.array([[axes]])
                elif n_rows == 1:
                    axes = axes.reshape(1, -1)
                elif n_cols == 1:
                    axes = axes.reshape(-1, 1)
                
                # Generate spectrum for each channel in spatial order
                for row in range(n_rows):
                    for col in range(n_cols):
                        channel_name = channel_grid[row][col]
                        if channel_name is None:
                            # Empty grid cell - hide it
                            axes[row, col].axis('off')
                            continue
                        
                        ax = axes[row, col]
                        ax.set_facecolor(self.theme.get_background_color())
                        
                        try:
                            # channel_name from grid is the original name from extract_all_sites
                            # It should match a key in metrics_by_site, but handle case mismatches
                            # Try to get PSD data from raw_data first
                            freqs = None
                            psd = None
                            
                            if raw_data is not None:
                                # Extract channel data from raw_data
                                # raw may have standardized names (Fp1, F7) while channel_name from metrics_by_site may be original (EEG Fp1-LE)
                                if hasattr(raw_data, 'get_data'):  # MNE Raw object
                                    try:
                                        import mne
                                        _picks = mne.pick_types(
                                            raw_data.info, meg=False, eeg=True, exclude=[],
                                        )
                                        raw_ch_names = [raw_data.ch_names[i] for i in _picks]
                                    except Exception:
                                        _picks = list(range(len(raw_data.ch_names)))
                                        raw_ch_names = list(raw_data.ch_names)
                                    ch_idx = None
                                    if channel_name in raw_ch_names:
                                        ch_idx = raw_ch_names.index(channel_name)
                                    else:
                                        cleaned = clean_channel_name(channel_name)
                                        if cleaned in raw_ch_names:
                                            ch_idx = raw_ch_names.index(cleaned)
                                        else:
                                            ch_upper = channel_name.upper()
                                            for i, rn in enumerate(raw_ch_names):
                                                if rn.upper() == ch_upper or clean_channel_name(rn).upper() == ch_upper:
                                                    ch_idx = i
                                                    break
                                    if ch_idx is not None and ch_idx < len(_picks):
                                        pi = _picks[ch_idx]
                                        channel_data = raw_data.get_data(picks=[pi])[0, :]
                                        freqs, psd = self._calculate_psd(channel_data, sfreq)
                                    elif ch_idx is not None:
                                        channel_data = raw_data.get_data()[ch_idx, :]
                                        freqs, psd = self._calculate_psd(channel_data, sfreq)
                                    else:
                                        logger.warning(
                                            f"Channel {channel_name} not found in raw_data (tried cleaned/case-insensitive)"
                                        )
                                elif isinstance(raw_data, dict) and channel_name in raw_data:
                                    # Dict of channel arrays
                                    channel_data = raw_data[channel_name]
                                    if isinstance(channel_data, np.ndarray):
                                        freqs, psd = self._calculate_psd(channel_data, sfreq)
                            
                            # If no PSD from raw/dict, use metrics (stored Welch PSD if present, else synthetic bands)
                            if freqs is None or len(freqs) == 0:
                                # Get band powers from metrics
                                # channel_name from grid is the original name from extract_all_sites
                                # But we need to handle case mismatches
                                site_data = None
                                
                                # First try direct lookup (channel_name is from grid, which uses original names)
                                if channel_name in metrics_by_site:
                                    site_data = metrics_by_site[channel_name]
                                else:
                                    # Try to find original name from cleaned name mapping
                                    cleaned_ch = clean_channel_name(channel_name)
                                    if cleaned_ch in cleaned_to_original:
                                        orig_name = cleaned_to_original[cleaned_ch]
                                        if orig_name in metrics_by_site:
                                            site_data = metrics_by_site[orig_name]
                                    
                                    # If still not found, try case-insensitive match
                                    if site_data is None:
                                        channel_upper = channel_name.upper()
                                        channel_lower = channel_name.lower()
                                        channel_title = channel_name.title()
                                        for key in metrics_by_site.keys():
                                            if isinstance(key, str):
                                                if key.upper() == channel_upper or key.lower() == channel_lower or key.title() == channel_title:
                                                    site_data = metrics_by_site[key]
                                                    break
                                
                                if site_data is None:
                                    logger.warning(f"Could not find site_data for channel {channel_name} in metrics_by_site. Available keys: {list(metrics_by_site.keys())[:10]}")
                                    site_data = {}
                                else:
                                    # Check if site_data is a list (should be dict after TQ7 fix)
                                    if isinstance(site_data, list):
                                        logger.warning(f"Site data for {channel_name} is a list (length {len(site_data)}), expected dict. This may indicate TQ7 combination issue.")
                                        # Try to convert list of dicts to single dict
                                        if site_data and isinstance(site_data[0], dict):
                                            merged = {}
                                            for item in site_data:
                                                if isinstance(item, dict):
                                                    merged.update(item)
                                            site_data = merged
                                            logger.info(f"Converted list to dict for {channel_name}")
                                        else:
                                            site_data = {}
                                
                                # Handle nested structure with epoch
                                if is_nested and epoch:
                                    # Normalize epoch to uppercase for lookup (EO, EC, etc.)
                                    epoch_upper = epoch.upper()
                                    
                                    if isinstance(site_data, dict):
                                        # Try exact match first
                                        if epoch_upper in site_data:
                                            site_metrics = site_data[epoch_upper]
                                        elif epoch in site_data:
                                            # Try original case
                                            site_metrics = site_data[epoch]
                                        else:
                                            available_epochs = list(site_data.keys())
                                            logger.debug(f"Epoch {epoch} (normalized: {epoch_upper}) not found for channel {channel_name}. Available: {available_epochs}")
                                            ax.axis('off')
                                            continue
                                        
                                        if not isinstance(site_metrics, dict):
                                            logger.warning(f"Epoch {epoch_upper} data for {channel_name} is not a dict: {type(site_metrics)}")
                                            ax.axis('off')
                                            continue
                                    else:
                                        logger.debug(f"Site data for {channel_name} is not a dict: {type(site_data)}")
                                        ax.axis('off')
                                        continue
                                elif is_nested and not epoch:
                                    # Average across available epochs
                                    epoch_values = []
                                    for ep_key, ep_metrics in site_data.items():
                                        if isinstance(ep_metrics, dict) and ep_key in ['EO', 'EC', 'EOT', 'EO1', 'EO2', 'EC1', 'EC2']:
                                            epoch_values.append(ep_metrics)
                                    
                                    if epoch_values:
                                        # Average metrics across epochs
                                        site_metrics = {}
                                        for band_key in ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma', 'SMR', 'HiBeta']:
                                            values = [ep.get(band_key, 0.0) for ep in epoch_values]
                                            site_metrics[band_key] = np.mean(values) if values else 0.0
                                    else:
                                        site_metrics = {}
                                else:
                                    # Flat structure
                                    site_metrics = site_data if isinstance(site_data, dict) else {}

                                from_metrics_psd = False
                                if isinstance(site_metrics, dict):
                                    pl = site_metrics.get("psd")
                                    fl = site_metrics.get("freqs")
                                    if pl is not None and fl is not None:
                                        try:
                                            _f = np.asarray(fl, dtype=float).ravel()
                                            _p = np.asarray(pl, dtype=float).ravel()
                                            if _f.size > 0 and _f.size == _p.size:
                                                freqs = _f
                                                psd = _p
                                                from_metrics_psd = True
                                        except Exception:
                                            pass

                                if not from_metrics_psd:
                                    freqs = np.linspace(freq_min, freq_max, 1000)
                                    # Map band names to metric keys
                                    band_metric_map = {
                                        'delta': 'Delta',
                                        'theta': 'Theta',
                                        'alpha': 'Alpha',
                                        'beta': 'Beta',
                                        'gamma': 'Gamma',
                                        'smr': 'SMR',
                                        'hibeta': 'HiBeta'
                                    }
                                    # Create synthetic PSD by distributing band powers
                                    psd = np.zeros_like(freqs)
                                    for band_name, (low, high) in band_ranges.items():
                                        band_metric_key = band_metric_map.get(band_name.lower(), band_name.capitalize())
                                        band_power = site_metrics.get(band_metric_key, 0.0)
                                        if band_power > 0:
                                            band_mask = (freqs >= low) & (freqs < high)
                                            if np.any(band_mask):
                                                band_width = high - low
                                                psd_density = band_power / band_width if band_width > 0 else 0
                                                psd[band_mask] = psd_density
                            
                            # Filter to frequency range
                            freq_mask = (freqs >= freq_min) & (freqs <= freq_max)
                            freqs_filtered = freqs[freq_mask]
                            psd_filtered = psd[freq_mask]
                            
                            if len(freqs_filtered) == 0:
                                logger.warning(f"No frequency data for {channel_name} ({epoch or 'all'})")
                                ax.axis('off')
                                continue
                            
                            # Check if we have any non-zero values
                            max_psd_val = np.max(psd_filtered) if len(psd_filtered) > 0 else 0.0
                            if max_psd_val <= 0:
                                logger.warning(f"All PSD values are zero for {channel_name} ({epoch or 'all'}). Site data type: {type(site_data)}, is_nested: {is_nested}, site_metrics keys: {list(site_metrics.keys())[:5] if isinstance(site_metrics, dict) else 'N/A'}")
                                ax.axis('off')
                                continue
                            
                            # Convert PSD to µV²/Hz for display
                            psd_uv2 = psd_filtered * 1e12  # V²/Hz to µV²/Hz
                            
                            # Plot spectrum
                            ax.plot(freqs_filtered, psd_uv2, 
                                   color=self.theme.get_foreground_color(),
                                   linewidth=1.5, alpha=0.9)
                            
                            # Add band color shading if enabled
                            if self.config.get('power_spectra.show_band_colors', True):
                                for band_name, (low, high) in band_ranges.items():
                                    if low >= freq_min and high <= freq_max:
                                        band_mask = (freqs_filtered >= low) & (freqs_filtered < high)
                                        if np.any(band_mask):
                                            color = band_colors.get(band_name, self.theme.get_foreground_color())
                                            ax.fill_between(freqs_filtered, 0, psd_uv2,
                                                           where=band_mask,
                                                           color=color, alpha=0.2, zorder=0)
                            
                            # Styling
                            ax.set_xlim(freq_min, freq_max)
                            
                            # Set ylim with proper bounds checking
                            max_psd = np.max(psd_uv2) if len(psd_uv2) > 0 else 0.0
                            if max_psd > 0:
                                y_max = max_psd * 1.1
                            else:
                                # Default to a small positive value if all values are zero
                                y_max = 1.0
                            
                            # Ensure y_max is always greater than 0
                            if y_max <= 0:
                                y_max = 1.0
                            
                            ax.set_ylim(0, y_max)
                            ax.set_xlabel('Frequency (Hz)', color=self.theme.get_foreground_color(),
                                        fontsize=9)
                            ax.set_ylabel('Power (µV²/Hz)', color=self.theme.get_foreground_color(),
                                        fontsize=9)
                            
                            # Channel label
                            if self.config.get('power_spectra.show_channel_labels', True):
                                ax.set_title(channel_name, color=self.theme.get_region_color(channel_name),
                                           fontsize=11, fontweight='bold', pad=5)
                            
                            # Apply dark theme
                            self.theme.apply_dark_theme(ax=ax)
                            ax.grid(True, alpha=0.2, color=self.theme.get_foreground_color())
                            
                        except Exception as e:
                            logger.error(f"Error generating spectrum for {channel_name}: {e}", exc_info=True)
                            ax.axis('off')

                if layout_mode == "wineeog_1020":
                    for row in range(n_rows):
                        for col in range(n_cols):
                            if channel_grid[row][col] is None:
                                continue
                            lax = axes[row, col]
                            if row < n_rows - 1:
                                lax.set_xlabel("")
                            if col > 0:
                                lax.set_ylabel("")
                            lax.tick_params(
                                axis="x",
                                labelbottom=(row == n_rows - 1),
                                labelsize=8,
                            )
                            lax.tick_params(
                                axis="y",
                                labelleft=(col == 0),
                                labelsize=8,
                            )
                
                # Overall title
                title = "FFT Power Spectra"
                if epoch:
                    title += f" ({epoch})"
                
                fig.suptitle(title, color=self.theme.get_foreground_color(),
                            fontsize=16, fontweight='bold', y=0.995)
                
                # Optional Data quality callout
                qc_text = format_qc_callout_plain(qc_summary, ica_applied_before_metrics)
                if qc_text:
                    fig.text(0.02, 0.02, "Data quality: " + qc_text,
                             fontsize=8, color=self.theme.get_foreground_color(), ha='left', va='bottom',
                             wrap=True, transform=fig.transFigure,
                             bbox=dict(boxstyle='round,pad=0.2', facecolor=self.theme.get_background_color(),
                                       alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=0.8))
                
                plt.tight_layout(rect=[0, 0, 1, 0.98])
                
                # Save
                if epoch:
                    filename = f"fft_spectra_grid_{epoch.lower()}.png"
                else:
                    filename = "fft_spectra_grid.png"
                
                filepath = output_dir / filename
                fig.savefig(filepath, dpi=self.config.get_dpi(),
                           format=self.config.get_format(),
                           facecolor=self.theme.get_background_color(),
                           bbox_inches='tight')
                plt.close(fig)
                
                all_spectra_paths.append(filepath)
                logger.info(f"Generated power spectra grid ({epoch or 'all'}): {filepath}")
                
                # Create HTML wrapper with additional information
                html_filepath = self._create_spectrum_html_wrapper(
                    filepath, epoch, metrics_by_site, output_dir
                )
                if html_filepath:
                    all_spectra_paths.append(html_filepath)
            
            # Optional: export per-channel band power from metrics_for scripting/reporting
            if export_band_power and output_dir and metrics_by_site:
                band_keys = ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma', 'SMR', 'HiBeta']
                export_list = []
                is_nested = is_nested_structure(metrics_by_site)
                for site, site_data in metrics_by_site.items():
                    if not isinstance(site_data, dict):
                        continue
                    if is_nested:
                        for ep_key, ep_data in site_data.items():
                            if ep_key in ('EO', 'EC', 'EOT', 'EO1', 'EO2', 'EC1', 'EC2') and isinstance(ep_data, dict):
                                for band in band_keys:
                                    val = ep_data.get(band)
                                    if val is not None:
                                        export_list.append({'channel': site, 'epoch': ep_key, 'band': band, 'value': round(float(val), 6)})
                    else:
                        for band in band_keys:
                            val = site_data.get(band)
                            if val is not None:
                                export_list.append({'channel': site, 'epoch': '', 'band': band, 'value': round(float(val), 6)})
                if export_list:
                    json_file = output_dir / f'power_spectra_band_power_{subject_id}_{session_id}.json'
                    try:
                        json_file.write_text(json.dumps({'band_power': export_list, 'subject_id': subject_id, 'session_id': session_id}, indent=2), encoding='utf-8')
                        logger.info(f"Saved spectrum band power export: {json_file}")
                    except Exception as e:
                        logger.warning(f"Could not write spectrum band power JSON: {e}")
            
            # Return the first spectra path (or None if none generated)
            # The report generator will handle multiple paths
            return all_spectra_paths[0] if all_spectra_paths else None
            
        except Exception as e:
            logger.error(f"Error generating power spectra: {e}", exc_info=True)
            return None
    
    def _create_spectrum_html_wrapper(self, image_path: Path, epoch: Optional[str],
                                      metrics_by_site: Dict[str, Any],
                                      output_dir: Path) -> Optional[Path]:
        """Create HTML wrapper for spectrum with additional information"""
        try:
            # Extract summary statistics from metrics
            all_psd_values = []
            channel_count = 0
            
            for site, site_data in metrics_by_site.items():
                if is_nested_structure(site_data):
                    epochs = get_all_available_epochs(site_data)
                    if epoch and epoch in epochs:
                        epoch_data = site_data[epoch]
                    elif not epoch and epochs:
                        epoch_data = site_data[epochs[0]]
                    else:
                        continue
                else:
                    epoch_data = site_data
                
                if isinstance(epoch_data, dict):
                    # Try to get PSD data
                    psd_data = epoch_data.get('psd') or epoch_data.get('power_spectrum')
                    if psd_data is not None and isinstance(psd_data, np.ndarray):
                        all_psd_values.extend(psd_data.flatten())
                        channel_count += 1
            
            # Generate insights
            insights = []
            if len(all_psd_values) > 0:
                mean_power = float(np.mean(all_psd_values))
                max_power = float(np.max(all_psd_values))
                
                insights.append(f"• <b>Mean Power:</b> {mean_power:.4f} µV²/Hz")
                insights.append(f"• <b>Peak Power:</b> {max_power:.4f} µV²/Hz")
                insights.append(f"• <b>Channels Analyzed:</b> {channel_count}")
            else:
                insights.append("• Power spectral data available")
            
            insights.append("• Review frequency-specific patterns")
            insights.append("• Compare across channels for asymmetry")
            
            # Create HTML
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>EEG Paradox Decoder - Power Spectra</title>
    <style>
        body {{ font-family: Arial, sans-serif; background: #0a0a0a; color: #ffffff; margin: 0; padding: 20px; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 20px; color: #00F0FF; }}
        .content {{ display: flex; gap: 20px; flex-wrap: wrap; }}
        .image-section {{ flex: 1; min-width: 600px; }}
        .image-section img {{ width: 100%; height: auto; border: 2px solid #00F0FF; border-radius: 8px; }}
        .info-section {{ flex: 0 0 350px; background: rgba(0, 0, 0, 0.8); border: 2px solid #00F0FF; border-radius: 8px; padding: 20px; }}
        .info-section h3 {{ color: #00F0FF; margin-top: 0; }}
        .insight-box {{ background: rgba(0, 255, 136, 0.1); padding: 15px; border-radius: 4px; margin-bottom: 15px; }}
        .button-group {{ margin-top: 20px; display: flex; gap: 10px; }}
        .btn {{ background: #00F0FF; color: #000; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; }}
        .btn:hover {{ background: #00D0E0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>EEG Paradox Decoder - FFT Power Spectra</h1>
            <p>{epoch.upper() if epoch else 'All Epochs'}</p>
        </div>
        <div class="content">
            <div class="image-section">
                <img src="{image_path.name}" alt="Power Spectra">
                <div class="button-group">
                    <a href="{image_path.name}" download class="btn">📥 Download Image</a>
                    <button onclick="window.print()" class="btn">🖨️ Print</button>
                </div>
            </div>
            <div class="info-section">
                <h3>💡 Analysis Insights</h3>
                <div class="insight-box">
                    {'<br>'.join(insights)}
                </div>
                <h3>📊 How to Read This Visualization</h3>
                <div class="insight-box">
                    <b>📈 Understanding the Plots:</b><br>
                    • Each plot shows power vs frequency for one channel<br>
                    • <b>X-axis:</b> Frequency (Hz) - from 0 to 50 Hz<br>
                    • <b>Y-axis:</b> Power (µV²/Hz) - spectral density<br>
                    • <b>Peaks</b> indicate dominant frequencies<br><br>
                    <b>🎯 How to Interpret:</b><br>
                    • Compare across channels for patterns<br>
                    • Look for dominant frequencies (alpha ~10Hz, beta ~20Hz)<br>
                    • Check for asymmetry between hemispheres<br>
                    • Review with clinical context and other visualizations<br>
                    • Higher power = stronger signal at that frequency
                </div>
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
            logger.warning(f"Failed to create HTML wrapper for spectrum: {e}")
            return None

    def generate_psd_overlay(
        self,
        sig_eo: Optional[np.ndarray] = None,
        sig_ec: Optional[np.ndarray] = None,
        sfreq: float = 256.0,
        band: Tuple[float, float] = (8.0, 13.0),
        ch_name: str = "",
        band_name: str = "",
        colors: Tuple[str, str] = ("#52e8fc", "#ff2bd6"),
        output_path: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        Generate EO vs EC PSD overlay for a single channel and band (Squiggle-style).
        Supports single-condition mode when only sig_eo or sig_ec is provided.

        Args:
            sig_eo: Eyes-open signal (1D array), or None for EC-only
            sig_ec: Eyes-closed signal (1D array), or None for EO-only
            sfreq: Sampling frequency
            band: (fmin, fmax) in Hz
            ch_name: Channel name for title
            band_name: Band name for title
            colors: (EO_color, EC_color) - default Paradox cyan/magenta
            output_path: Optional path to save PNG

        Returns:
            Path to saved PNG or None
        """
        import matplotlib.pyplot as plt
        from scipy import signal as scipy_signal

        if sig_eo is None and sig_ec is None:
            logger.warning("generate_psd_overlay: need at least sig_eo or sig_ec")
            return None
        sig_primary = sig_eo if sig_eo is not None else sig_ec
        has_eo = sig_eo is not None and len(sig_eo) > 0
        has_ec = sig_ec is not None and len(sig_ec) > 0

        fmin, fmax = band
        min_len = min(len(sig_eo) if sig_eo is not None else 1e9, len(sig_ec) if sig_ec is not None else 1e9)
        nperseg = min(max(256, int(sfreq * 2)), len(sig_primary) // 2)
        if nperseg < 16:
            logger.warning(f"Segment too short for PSD overlay: {len(sig_primary)} samples")
            return None
        noverlap = nperseg // 2

        freqs, psd_eo = (None, None)
        if has_eo:
            freqs, psd_eo = scipy_signal.welch(sig_eo, fs=sfreq, nperseg=nperseg, noverlap=noverlap)
        if has_ec:
            _f, psd_ec = scipy_signal.welch(sig_ec, fs=sfreq, nperseg=nperseg, noverlap=noverlap)
            if freqs is None:
                freqs = _f
            psd_ec_arr = psd_ec
        else:
            psd_ec_arr = None

        mask = (freqs >= fmin) & (freqs <= fmax)
        freqs_band = freqs[mask]
        psd_eo_band = psd_eo[mask] if has_eo else None
        psd_ec_band = psd_ec_arr[mask] if has_ec else None

        fig, ax = plt.subplots(figsize=(8, 4), facecolor=self.theme.get_background_color(), dpi=self.config.get_dpi())
        ax.set_facecolor(self.theme.get_background_color())
        title_suffix = "EO vs EC" if (has_eo and has_ec) else ("EO only" if has_eo else "EC only")
        if has_eo:
            ax.plot(freqs_band, psd_eo_band, color=colors[0], label="EO", linewidth=2.5)
            ax.fill_between(freqs_band, psd_eo_band, alpha=0.15, color=colors[0])
        if has_ec:
            ax.plot(freqs_band, psd_ec_band, color=colors[1], label="EC", linewidth=2.5)
            ax.fill_between(freqs_band, psd_ec_band, alpha=0.15, color=colors[1])
        ax.set_title(f"{ch_name} {band_name} PSD ({title_suffix})", color=self.theme.get_foreground_color(), fontsize=12)
        ax.set_xlabel("Frequency (Hz)", color=self.theme.get_foreground_color(), fontsize=10)
        ax.set_ylabel("Power (µV²/Hz)", color=self.theme.get_foreground_color(), fontsize=10)
        ax.legend(facecolor=self.theme.get_background_color(), edgecolor=self.theme.get_foreground_color(), labelcolor=self.theme.get_foreground_color())
        ax.tick_params(colors=self.theme.get_foreground_color())
        ax.grid(True, color="#333333", linestyle="--", alpha=0.3)
        fig.text(0.02, 0.98, "EEG Paradox Decoder - Per-Site PSD",
                 fontsize=10, fontweight="bold", color=self.theme.NEON_CYAN, ha="left", va="top",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor=self.theme.get_background_color(),
                          alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5),
                 transform=fig.transFigure, zorder=100)
        fig.tight_layout(rect=[0, 0, 1, 0.96])

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_path, dpi=self.config.get_dpi(), bbox_inches="tight", facecolor=self.theme.get_background_color())
            plt.close(fig)
            logger.info(f"Saved PSD overlay to {output_path}")
            return output_path
        return None

    def generate_waveform_overlay(
        self,
        sig_eo: Optional[np.ndarray] = None,
        sig_ec: Optional[np.ndarray] = None,
        sfreq: float = 256.0,
        band: Tuple[float, float] = (8.0, 13.0),
        ch_name: str = "",
        band_name: str = "",
        colors: Tuple[str, str] = ("#52e8fc", "#ff2bd6"),
        epoch_length: float = 10.0,
        output_path: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        Generate EO vs EC band-filtered waveform overlay (Squiggle-style).
        Supports single-condition mode when only sig_eo or sig_ec is provided.

        Args:
            sig_eo: Eyes-open signal (1D array), or None for EC-only
            sig_ec: Eyes-closed signal (1D array), or None for EO-only
            sfreq: Sampling frequency
            band: (fmin, fmax) in Hz
            ch_name: Channel name for title
            band_name: Band name for title
            colors: (EO_color, EC_color) - default Paradox cyan/magenta
            epoch_length: Length of epoch in seconds
            output_path: Optional path to save PNG

        Returns:
            Path to saved PNG or None
        """
        import matplotlib.pyplot as plt
        import mne

        if sig_eo is None and sig_ec is None:
            logger.warning("generate_waveform_overlay: need at least sig_eo or sig_ec")
            return None
        has_eo = sig_eo is not None and len(sig_eo) > 0
        has_ec = sig_ec is not None and len(sig_ec) > 0
        fmin, fmax = band
        n_samples = int(epoch_length * sfreq)

        sig_eo_filt = None
        sig_ec_filt = None
        if has_eo:
            sig_eo_filt = mne.filter.filter_data(sig_eo.astype(np.float64), sfreq, fmin, fmax, verbose=False)[:n_samples]
        if has_ec:
            sig_ec_filt = mne.filter.filter_data(sig_ec.astype(np.float64), sfreq, fmin, fmax, verbose=False)[:n_samples]

        n_plot = min(n_samples, len(sig_eo_filt) if sig_eo_filt is not None else len(sig_ec_filt))
        t = np.arange(n_plot) / sfreq
        title_suffix = "EO vs EC" if (has_eo and has_ec) else ("EO only" if has_eo else "EC only")

        fig, ax = plt.subplots(figsize=(10, 4), facecolor=self.theme.get_background_color(), dpi=self.config.get_dpi())
        ax.set_facecolor(self.theme.get_background_color())
        if has_eo:
            dat = sig_eo_filt[:n_plot]
            ax.plot(t, dat, color=colors[0], label="EO", linewidth=2, alpha=0.8)
            ax.fill_between(t, dat, alpha=0.1, color=colors[0])
        if has_ec:
            dat = sig_ec_filt[:n_plot]
            ax.plot(t, dat, color=colors[1], label="EC", linewidth=2, alpha=0.8)
            ax.fill_between(t, dat, alpha=0.1, color=colors[1])
        ax.set_title(f"{ch_name} {band_name} Waveform ({title_suffix})", color=self.theme.get_foreground_color(), fontsize=12)
        ax.set_xlabel("Time (s)", color=self.theme.get_foreground_color(), fontsize=10)
        ax.set_ylabel("Amplitude (µV)", color=self.theme.get_foreground_color(), fontsize=10)
        ax.legend(facecolor=self.theme.get_background_color(), edgecolor=self.theme.get_foreground_color(), labelcolor=self.theme.get_foreground_color())
        ax.tick_params(colors=self.theme.get_foreground_color())
        ax.grid(True, color="#333333", linestyle="--", alpha=0.3)
        fig.text(0.02, 0.98, "EEG Paradox Decoder - Per-Site Waveform",
                 fontsize=10, fontweight="bold", color=self.theme.NEON_CYAN, ha="left", va="top",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor=self.theme.get_background_color(),
                          alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5),
                 transform=fig.transFigure, zorder=100)
        fig.tight_layout(rect=[0, 0, 1, 0.96])

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_path, dpi=self.config.get_dpi(), bbox_inches="tight", facecolor=self.theme.get_background_color())
            plt.close(fig)
            logger.info(f"Saved waveform overlay to {output_path}")
            return output_path
        return None

    def generate_rms_overlay(
        self,
        sig_eo: Optional[np.ndarray] = None,
        sig_ec: Optional[np.ndarray] = None,
        sfreq: float = 256.0,
        band: Tuple[float, float] = (8.0, 13.0),
        ch_name: str = "",
        band_name: str = "",
        colors: Tuple[str, str] = ("#52e8fc", "#ff2bd6"),
        epoch_length: float = 10.0,
        window_sec: float = 0.5,
        step_sec: float = 0.1,
        output_path: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        Generate EO vs EC band-filtered RMS (root mean square) overlay.
        Plots sliding-window RMS over time as amplitude envelope.
        Supports single-condition mode when only sig_eo or sig_ec is provided.

        Args:
            sig_eo: Eyes-open signal (1D array), or None for EC-only
            sig_ec: Eyes-closed signal (1D array), or None for EO-only
            sfreq: Sampling frequency
            band: (fmin, fmax) in Hz
            ch_name: Channel name for title
            band_name: Band name for title
            colors: (EO_color, EC_color) - default Paradox cyan/magenta
            epoch_length: Length of epoch in seconds
            window_sec: RMS window duration in seconds
            step_sec: Step between windows in seconds
            output_path: Optional path to save PNG

        Returns:
            Path to saved PNG or None
        """
        import matplotlib.pyplot as plt
        import mne

        if sig_eo is None and sig_ec is None:
            logger.warning("generate_rms_overlay: need at least sig_eo or sig_ec")
            return None
        has_eo = sig_eo is not None and len(sig_eo) > 0
        has_ec = sig_ec is not None and len(sig_ec) > 0
        fmin, fmax = band
        n_samples = int(epoch_length * sfreq)

        sig_eo_filt = None
        sig_ec_filt = None
        if has_eo:
            sig_eo_filt = mne.filter.filter_data(sig_eo.astype(np.float64), sfreq, fmin, fmax, verbose=False)[:n_samples]
        if has_ec:
            sig_ec_filt = mne.filter.filter_data(sig_ec.astype(np.float64), sfreq, fmin, fmax, verbose=False)[:n_samples]

        win_samples = int(window_sec * sfreq)
        step_samples = max(1, int(step_sec * sfreq))
        if win_samples < 4:
            logger.warning("generate_rms_overlay: window too short")
            return None

        def _rms_trace(sig: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
            n = len(sig)
            t_centers = []
            rms_vals = []
            start = 0
            while start + win_samples <= n:
                window = sig[start : start + win_samples]
                rms = np.sqrt(np.mean(window ** 2))
                t_centers.append((start + win_samples / 2) / sfreq)
                rms_vals.append(rms)
                start += step_samples
            return np.array(t_centers), np.array(rms_vals)

        t_eo, rms_eo = _rms_trace(sig_eo_filt) if has_eo else (np.array([]), np.array([]))
        t_ec, rms_ec = _rms_trace(sig_ec_filt) if has_ec else (np.array([]), np.array([]))

        if (len(t_eo) == 0 and len(t_ec) == 0):
            logger.warning("generate_rms_overlay: no RMS points")
            return None

        title_suffix = "EO vs EC" if (has_eo and has_ec) else ("EO only" if has_eo else "EC only")

        fig, ax = plt.subplots(figsize=(10, 4), facecolor=self.theme.get_background_color(), dpi=self.config.get_dpi())
        ax.set_facecolor(self.theme.get_background_color())
        if has_eo and len(t_eo) > 0:
            ax.plot(t_eo, rms_eo, color=colors[0], label="EO", linewidth=2, alpha=0.8)
            ax.fill_between(t_eo, rms_eo, alpha=0.15, color=colors[0])
        if has_ec and len(t_ec) > 0:
            ax.plot(t_ec, rms_ec, color=colors[1], label="EC", linewidth=2, alpha=0.8)
            ax.fill_between(t_ec, rms_ec, alpha=0.15, color=colors[1])
        ax.set_title(f"{ch_name} {band_name} RMS ({title_suffix})", color=self.theme.get_foreground_color(), fontsize=12)
        ax.set_xlabel("Time (s)", color=self.theme.get_foreground_color(), fontsize=10)
        ax.set_ylabel("RMS (µV)", color=self.theme.get_foreground_color(), fontsize=10)
        ax.legend(facecolor=self.theme.get_background_color(), edgecolor=self.theme.get_foreground_color(), labelcolor=self.theme.get_foreground_color())
        ax.tick_params(colors=self.theme.get_foreground_color())
        ax.grid(True, color="#333333", linestyle="--", alpha=0.3)
        fig.text(0.02, 0.98, "EEG Paradox Decoder - Per-Site RMS",
                 fontsize=10, fontweight="bold", color=self.theme.NEON_CYAN, ha="left", va="top",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor=self.theme.get_background_color(),
                          alpha=0.9, edgecolor=self.theme.NEON_CYAN, linewidth=1.5),
                 transform=fig.transFigure, zorder=100)
        fig.tight_layout(rect=[0, 0, 1, 0.96])

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_path, dpi=self.config.get_dpi(), bbox_inches="tight", facecolor=self.theme.get_background_color())
            plt.close(fig)
            logger.info(f"Saved RMS overlay to {output_path}")
            return output_path
        return None
