#!/usr/bin/env python3
"""
Cuban Database Loader
Loads normative mean/SD from Cuban 2nd wave CSV files. Fallback when hardcoded norms missing.

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


import csv
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# Metric name mapping (Cuban CSV bands -> norm_manager keys)
_BAND_TO_METRIC = {
    'delta': 'delta',
    'theta': 'theta',
    'alpha': 'alpha',
    'beta': 'beta',
    'gamma': 'gamma',
    'high_gamma': 'hibeta',  # map high_gamma to hibeta for compatibility
}

# Standard 10-20 sites (include P7, P8, F7, F8, T7, T8, Fp1, Fp2 from channels_bids)
_STANDARD_SITES = [
    'fp1', 'fp2', 'f7', 'f8', 'f3', 'f4', 'fz',
    't7', 't8', 'c3', 'c4', 'cz',
    'p7', 'p8', 'p3', 'p4', 'pz',
    'o1', 'o2',
]


def _find_cuban_base() -> Optional[Path]:
    """Find Cuban 2nd wave database base path (DLC, ProgramData, or repo)."""
    try:
        from hexnode.eeg.norms_paths import get_cuban_databases_dir

        cuban = get_cuban_databases_dir()
        if cuban:
            w2 = cuban / "cuban_2nd_wave_database"
            if w2.is_dir():
                return w2
    except Exception:
        pass
    return None


def load_cuban2ndwave_from_csv() -> Optional[Dict[str, Dict[str, Dict[str, Any]]]]:
    """
    Load normative mean/SD from Cuban 2nd wave CSV files.
    Uses eyes_closed normative_database for band-level norms, then applies to all standard sites.
    Returns structure: {site: {metric: {mean, sd, normal, low, high, ...}}}

    Returns None if files missing or on error (caller falls back to hardcoded).
    """
    base = _find_cuban_base()
    if not base:
        logger.debug("Cuban 2nd wave base path not found")
        return None

    # Prefer eyes_closed condition (most common for EO/EC protocols)
    norm_files = [
        base / 'condition_specific_analysis' / 'eyes_closed' / 'eyes_closed_normative_database.csv',
        base / 'qeeg_analysis_tables' / 'normative_database.csv',
    ]

    csv_path = None
    for p in norm_files:
        if p.exists():
            csv_path = p
            break

    if not csv_path:
        logger.debug("Cuban normative CSV not found")
        return None

    try:
        band_data = defaultdict(lambda: {'means': [], 'sds': []})

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                band = (row.get('frequency_band') or '').strip().lower()
                mean_s = (row.get('normative_mean') or '').strip()
                sd_s = (row.get('normative_std') or '').strip()

                if band not in _BAND_TO_METRIC:
                    continue
                try:
                    mean_val = float(mean_s)
                    sd_val = float(sd_s)
                    if mean_val > 0 and sd_val > 0:
                        band_data[band]['means'].append(mean_val)
                        band_data[band]['sds'].append(sd_val)
                except (ValueError, TypeError):
                    continue

        if not band_data:
            logger.debug("No valid normative data extracted from CSV")
            return None

        # Use median for robustness (outlier-resistant)
        def _median(vals):
            if not vals:
                return None
            s = sorted(vals)
            n = len(s)
            return (s[n // 2] + s[(n - 1) // 2]) / 2 if n else s[0]

        norms_by_band = {}
        for band, data in band_data.items():
            m = _median(data['means'])
            sd = _median(data['sds'])
            if m is not None and sd is not None and sd > 0:
                metric = _BAND_TO_METRIC[band]
                norms_by_band[metric] = {
                    'mean': round(m, 2),
                    'sd': round(sd, 2),
                    'normal': round(m, 2),
                    'low': round(max(0, m - 2 * sd), 2),
                    'high': round(m + 2 * sd, 2),
                    'very_low': round(max(0, m - 2 * sd), 2),
                    'very_high': round(m + 2 * sd, 2),
                }

        if not norms_by_band:
            return None

        # Apply same band-level norms to all standard sites (global norms, no per-channel in CSV)
        result = {}
        for site in _STANDARD_SITES:
            result[site] = dict(norms_by_band)

        logger.info(f"Cuban loader: loaded norms for {len(result)} sites, {len(norms_by_band)} metrics from CSV")
        return result

    except Exception as e:
        logger.warning(f"Cuban CSV loader failed: {e}")
        return None


def load_channel_specific_from_z_scores() -> Optional[Dict[str, Dict[str, Dict[str, Any]]]]:
    """
    Attempt to build channel-specific norms from z_scores + channels_bids.
    The z_scores have (channel_index, band) but only z-score, not mean/sd.
    Returns None (reserved for future use when raw power available).
    """
    return None
