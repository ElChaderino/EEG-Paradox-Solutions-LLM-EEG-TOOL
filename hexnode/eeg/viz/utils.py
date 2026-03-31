#!/usr/bin/env python3
"""
Visualization Utilities

Shared utilities for visualization components including channel mapping,
interpolation, and data structure handling.

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
from typing import Dict, Any, List, Tuple, Optional, Union
import logging

logger = logging.getLogger(__name__)


def remove_overlapping_channels(info, tol: float = 0.05) -> Tuple[Any, List[int]]:
    """
    Remove channels with overlapping positions to improve topomap clarity.

    Keeps one channel per unique spatial position (within tolerance).
    Inspired by Squiggle Interpreter plotting.remove_overlapping_channels.

    Args:
        info: MNE Info object with channel positions in info['chs'][i]['loc'][:3]
        tol: Distance tolerance for considering channels overlapping (default 0.05)

    Returns:
        Tuple of (cleaned_info, list of kept indices into original ch_names)
    """
    try:
        import mne
    except ImportError:
        logger.debug("MNE not available for remove_overlapping_channels")
        return info, list(range(len(info['ch_names'])))

    ch_names = info['ch_names']
    n_ch = len(ch_names)
    if n_ch == 0:
        return info, []

    # Get positions from info (3D loc: x,y,z)
    pos = []
    for i in range(n_ch):
        loc = info['chs'][i].get('loc')
        if loc is not None and len(loc) >= 3:
            pos.append(loc[:3])
        else:
            pos.append((0.0, 0.0, 0.0))
    pos = np.array(pos)

    unique_idx = []
    for i in range(n_ch):
        duplicate = False
        for j in unique_idx:
            if np.linalg.norm(pos[i] - pos[j]) < tol:
                duplicate = True
                break
        if not duplicate:
            unique_idx.append(i)

    try:
        info_clean = mne.pick_info(info, sel=unique_idx, copy=True)
    except Exception as e:
        logger.debug(f"mne.pick_info failed: {e}, returning original")
        return info, list(range(n_ch))

    return info_clean, unique_idx


def clean_channel_name(name: str) -> str:
    """Clean channel names to clinical 10-20 format"""
    name = str(name).strip()
    
    # Remove suffixes first
    for suffix in ['-LE', '-RE', '-REF', '-M1', '-M2', '-A1', '-A2', '-Av', '-AV']:
        name = name.replace(suffix, '')
    
    # Convert to uppercase for processing
    name_upper = name.upper()
    
    # Convert old to new nomenclature
    replacements = {'T3': 'T7', 'T4': 'T8', 'T5': 'P7', 'T6': 'P8'}
    for old, new in replacements.items():
        name_upper = name_upper.replace(old, new)
    
    # Convert to proper case format
    mne_case_map = {
        'FP1': 'Fp1', 'FP2': 'Fp2',
        'FZ': 'Fz', 'CZ': 'Cz', 'PZ': 'Pz', 'OZ': 'Oz',
        'F3': 'F3', 'F4': 'F4', 'F7': 'F7', 'F8': 'F8',
        'C3': 'C3', 'C4': 'C4', 'T7': 'T7', 'T8': 'T8',
        'P3': 'P3', 'P4': 'P4', 'P7': 'P7', 'P8': 'P8',
        'O1': 'O1', 'O2': 'O2'
    }
    
    return mne_case_map.get(name_upper, name_upper.title())


def get_channel_positions(channel_names: List[str]) -> Tuple[np.ndarray, List[str]]:
    """
    Get clinical 10-20 positions for channels
    
    Args:
        channel_names: List of channel names
        
    Returns:
        Tuple of (positions_array, valid_channels_list)
    """
    from hexnode.eeg.viz.theme_manager import CLINICAL_1020_POSITIONS
    
    positions = []
    valid_channels = []
    
    for ch in channel_names:
        clean_ch = clean_channel_name(ch)
        if clean_ch in CLINICAL_1020_POSITIONS:
            positions.append(CLINICAL_1020_POSITIONS[clean_ch])
            valid_channels.append(clean_ch)
        else:
            # Estimate position
            from hexnode.eeg.viz.theme_manager import get_theme_manager
            theme = get_theme_manager()
            pos = theme._estimate_position(clean_ch)
            positions.append(pos)
            valid_channels.append(clean_ch)
    
    return np.array(positions), valid_channels


def is_nested_structure(metrics_by_site: Dict[str, Any]) -> bool:
    """
    Check if metrics_by_site has nested structure (EO/EC epochs)
    
    Args:
        metrics_by_site: Dictionary of metrics by site
        
    Returns:
        True if nested structure detected
    """
    if not metrics_by_site:
        return False
    
    first_site = list(metrics_by_site.keys())[0]
    first_site_data = metrics_by_site[first_site]
    
    if not isinstance(first_site_data, dict):
        return False
    
    # Check for epoch keys
    epoch_keys = ['EO', 'EC', 'EOT', 'EO1', 'EO2', 'EC1', 'EC2', 'UT', 'UT1', 'UT2']
    return any(epoch in first_site_data for epoch in epoch_keys)


def extract_band_values(metrics_by_site: Dict[str, Any], 
                       band: str,
                       epoch: Optional[str] = None) -> Tuple[List[str], np.ndarray]:
    """
    Extract band values from metrics_by_site structure
    
    Args:
        metrics_by_site: Dictionary of metrics by site
        band: Frequency band name (Delta, Theta, Alpha, Beta, Gamma, SMR, HiBeta)
        epoch: Optional epoch name (EO, EC) - if None, uses first available or averages
        
    Returns:
        Tuple of (channel_names, values_array)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    channel_names = []
    values = []
    
    # Map band names to metric keys
    band_map = {
        'delta': 'Delta',
        'theta': 'Theta',
        'alpha': 'Alpha',
        'beta': 'Beta',
        'gamma': 'Gamma',
        'smr': 'SMR',
        'hibeta': 'HiBeta'
    }
    
    metric_key = band_map.get(band.lower(), band.capitalize())
    
    is_nested = is_nested_structure(metrics_by_site)
    
    # Debug: track extraction statistics
    found_count = 0
    zero_count = 0
    missing_epoch_count = 0
    
    # Track problematic sites specifically
    problematic_sites_data = {}
    
    problematic_sites = ['OZ', 'CZ', 'PZ', 'FZ', 'Oz', 'Cz', 'Pz', 'Fz']
    
    for site, site_data in metrics_by_site.items():
        channel_names.append(site)
        
        # Debug: track problematic sites
        is_problematic = site.upper() in [s.upper() for s in problematic_sites]
        
        if is_nested:
            # Handle nested structure with case-insensitive epoch lookup
            if epoch:
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
                    # Use specific epoch
                    epoch_metrics = site_data[epoch_key]
                    if isinstance(epoch_metrics, dict):
                        value = epoch_metrics.get(metric_key, 0.0)
                        if value != 0.0:
                            found_count += 1
                            if is_problematic:
                                logger.info(f"✅ extract_band_values: {site} epoch {epoch_key} band {metric_key} = {value:.4f}")
                                problematic_sites_data[site] = {'value': value, 'found': True, 'epoch_found': True}
                        else:
                            zero_count += 1
                            if is_problematic:
                                logger.warning(f"⚠️ extract_band_values: {site} epoch {epoch_key} band {metric_key} = 0.0 (zero value)")
                                problematic_sites_data[site] = {'value': 0.0, 'found': False, 'epoch_found': True}
                    else:
                        value = 0.0
                        zero_count += 1
                        if is_problematic:
                            logger.warning(f"⚠️ extract_band_values: {site} epoch {epoch_key} is not a dict: {type(epoch_metrics)}")
                else:
                    # Epoch not found for this site
                    value = 0.0
                    missing_epoch_count += 1
                    if is_problematic:
                        available_epochs = list(site_data.keys()) if isinstance(site_data, dict) else []
                        logger.warning(f"⚠️ extract_band_values: {site} epoch {epoch} not found. Available: {available_epochs}")
                        problematic_sites_data[site] = {'value': 0.0, 'found': False, 'epoch_found': False, 'available_epochs': available_epochs}
            else:
                # Average across available epochs
                epoch_values = []
                for ep_key, ep_metrics in site_data.items():
                    if isinstance(ep_metrics, dict) and ep_key in ['EO', 'EC', 'EOT', 'EO1', 'EO2', 'EC1', 'EC2']:
                        band_val = ep_metrics.get(metric_key, 0.0)
                        epoch_values.append(band_val)
                        if band_val != 0.0:
                            found_count += 1
                
                if epoch_values:
                    value = np.mean(epoch_values)
                    if value == 0.0:
                        zero_count += 1
                else:
                    value = 0.0
                    zero_count += 1
        else:
            # Flat structure
            if isinstance(site_data, dict):
                value = site_data.get(metric_key, 0.0)
                if value != 0.0:
                    found_count += 1
                else:
                    zero_count += 1
            else:
                value = 0.0
                zero_count += 1
        
        values.append(float(value))
    
    # Debug logging
    total_channels = len(channel_names)
    if total_channels > 0:
        logger.debug(f"Extracted {band} ({metric_key}) values: "
                    f"{found_count}/{total_channels} non-zero, "
                    f"{zero_count}/{total_channels} zero, "
                    f"{missing_epoch_count} missing epoch")
        if found_count > 0:
            non_zero_values = [v for v in values if v != 0.0]
            if non_zero_values:
                logger.debug(f"  Range: [{min(non_zero_values):.4f}, {max(non_zero_values):.4f}]")
    
    # Log summary for problematic sites
    if problematic_sites_data:
        logger.warning(f"[SUMMARY] extract_band_values for {band} ({epoch or 'all'}):")
        for site, info in problematic_sites_data.items():
            logger.warning(f"   {site}: value={info.get('value', 0.0):.4f}, found={info.get('found', False)}, epoch_found={info.get('epoch_found', False)}")
            if not info.get('epoch_found', False):
                logger.warning(f"      Available epochs: {info.get('available_epochs', [])}")
    
    return channel_names, np.array(values)


def extract_band_instability(
    metrics_by_site: Dict[str, Any],
    band: str,
) -> Tuple[List[str], np.ndarray]:
    """
    Extract band power variance (instability) across epochs per channel.

    For each channel, collects band power from each epoch (EO, EC, etc.)
    and computes variance. Requires nested structure with multiple epochs.
    Returns empty arrays if single epoch or flat structure.

    Args:
        metrics_by_site: Dictionary of metrics by site
        band: Frequency band name (Delta, Theta, Alpha, Beta, Gamma, SMR, HiBeta)

    Returns:
        Tuple of (channel_names, variance_array). Empty if fewer than 2 epochs.
    """
    if not is_nested_structure(metrics_by_site):
        return [], np.array([])

    band_map = {
        'delta': 'Delta', 'theta': 'Theta', 'alpha': 'Alpha',
        'beta': 'Beta', 'gamma': 'Gamma', 'smr': 'SMR', 'hibeta': 'HiBeta'
    }
    metric_key = band_map.get(band.lower(), band.capitalize())
    epoch_keys = ['EO', 'EC', 'EOT', 'EO1', 'EO2', 'EC1', 'EC2', 'UT', 'UT1', 'UT2']

    channel_names = []
    variances = []
    for site, site_data in metrics_by_site.items():
        if not isinstance(site_data, dict):
            continue
        epoch_values = []
        for ep_key in epoch_keys:
            if ep_key in site_data:
                ep_metrics = site_data[ep_key]
                if isinstance(ep_metrics, dict):
                    v = ep_metrics.get(metric_key, 0.0)
                    epoch_values.append(float(v))
        if len(epoch_values) < 2:
            continue
        channel_names.append(site)
        variances.append(float(np.var(epoch_values)))

    return channel_names, np.array(variances) if variances else np.array([])


def extract_all_sites(metrics_by_site: Dict[str, Any]) -> List[str]:
    """
    Extract all site/channel names from metrics_by_site
    
    Args:
        metrics_by_site: Dictionary of metrics by site
        
    Returns:
        List of site names
    """
    return list(metrics_by_site.keys())


def get_epochs_for_site(metrics_by_site: Dict[str, Any], site: str) -> List[str]:
    """
    Get available epochs for a specific site
    
    Args:
        metrics_by_site: Dictionary of metrics by site
        site: Site name
        
    Returns:
        List of epoch names (EO, EC, etc.)
    """
    if site not in metrics_by_site:
        return []
    
    site_data = metrics_by_site[site]
    if not isinstance(site_data, dict):
        return []
    
    epoch_keys = ['EO', 'EC', 'EOT', 'EO1', 'EO2', 'EC1', 'EC2', 'UT', 'UT1', 'UT2']
    return [ep for ep in epoch_keys if ep in site_data]


def get_all_available_epochs(metrics_by_site: Dict[str, Any]) -> List[str]:
    """
    Get all epochs that are available across all sites
    
    Args:
        metrics_by_site: Dictionary of metrics by site
        
    Returns:
        List of epoch names available in at least one site
    """
    if not is_nested_structure(metrics_by_site):
        return []
    
    all_epochs = set()
    epoch_keys = ['EO', 'EC', 'EOT', 'EO1', 'EO2', 'EC1', 'EC2', 'UT', 'UT1', 'UT2']
    
    for site, site_data in metrics_by_site.items():
        if isinstance(site_data, dict):
            for epoch in epoch_keys:
                if epoch in site_data:
                    all_epochs.add(epoch)
    
    # Sort epochs in priority order (EO, EC first)
    priority_order = ['EO', 'EC', 'EOT', 'EO1', 'EO2', 'EC1', 'EC2', 'UT', 'UT1', 'UT2']
    sorted_epochs = [ep for ep in priority_order if ep in all_epochs]
    
    # Add any remaining epochs not in priority list
    for ep in sorted(all_epochs):
        if ep not in sorted_epochs:
            sorted_epochs.append(ep)
    
    return sorted_epochs


def format_qc_callout_plain(qc_summary: Optional[Dict[str, Any]], ica_applied: bool) -> str:
    """
    Format a short Data quality callout for matplotlib figures (plain text).
    Used by topomap, spectrum, and other viz that render QC on the figure.
    """
    if not qc_summary and not ica_applied:
        return ""
    lines = []
    if ica_applied:
        lines.append("ICA applied before metrics.")
    if qc_summary:
        if qc_summary.get("duration_min_s") is not None and qc_summary.get("duration_max_s") is not None:
            lines.append(f"Segment duration: {qc_summary['duration_min_s']:.1f}s\u2013{qc_summary['duration_max_s']:.1f}s")
        for key, label in [
            ("flatline_sites", "Flatline/invalid"),
            ("clipping_sites", "Possible clipping"),
            ("line_noise_sites", "Line noise"),
            ("sites_with_range_flags", "Out-of-range metrics"),
            ("sites_with_high_amplitude_note", "High-amplitude"),
            ("sites_with_emg_note", "EMG note"),
        ]:
            sites = qc_summary.get(key)
            if sites and len(sites) > 0:
                s = ", ".join(sites[:3]) + (" ..." if len(sites) > 3 else "")
                lines.append(f"{label}: {s}")
    return " | ".join(lines) if lines else ""


def format_qc_callout_html(qc_summary: Optional[Dict[str, Any]], ica_applied: bool) -> str:
    """
    Format Signal/Data Quality HTML for HTML views (LORETA, trace viewer, etc.).
    Matches Mahalanobis _format_qc_panel style.
    """
    lines = ["<b>Signal Quality</b><br>"]
    if not qc_summary and not ica_applied:
        lines.append("No QC summary provided.<br>")
        return "".join(lines)
    if ica_applied:
        lines.append("Artifact correction (ICA) was applied before metrics.<br>")
    if qc_summary:
        if qc_summary.get("duration_min_s") is not None and qc_summary.get("duration_max_s") is not None:
            lines.append(f"Segment duration: {qc_summary['duration_min_s']:.1f}s \u2013 {qc_summary['duration_max_s']:.1f}s<br>")
        for key, label in [
            ("flatline_sites", "Flatline/invalid"),
            ("clipping_sites", "Possible clipping"),
            ("line_noise_sites", "Line noise"),
            ("sites_with_range_flags", "Out-of-range metrics"),
            ("sites_with_high_amplitude_note", "High-amplitude segments"),
            ("sites_with_emg_note", "EMG note"),
        ]:
            sites = qc_summary.get(key)
            if sites and len(sites) > 0:
                s = ", ".join(sites[:5]) + (" ..." if len(sites) > 5 else "")
                lines.append(f"{label}: {s}<br>")
    if len(lines) == 1 and ica_applied:
        lines.append("No notable artifacts reported.")
    elif len(lines) == 1:
        lines.append("No notable artifacts reported.")
    return "".join(lines)
