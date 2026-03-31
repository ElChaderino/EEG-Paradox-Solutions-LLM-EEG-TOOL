#!/usr/bin/env python3
"""
Single source of truth for EEG frequency band bounds (Hz).
Used by topomap, waveform grid, and other visualization generators.
Config can override via hexnode.eeg.viz.band_definitions.
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

from typing import Dict, Tuple, Optional, Any

# Default band (name -> (fmin_hz, fmax_hz)) used when config has no override
DEFAULT_BAND_DEFINITIONS: Dict[str, Tuple[float, float]] = {
    'delta': (0.5, 4.0),
    'theta': (4.0, 8.0),
    'alpha': (8.0, 13.0),
    'smr': (12.0, 15.0),
    'beta': (13.0, 30.0),
    'hibeta': (20.0, 30.0),
    'gamma': (30.0, 40.0),
}


def get_band_definitions(config: Optional[Any] = None) -> Dict[str, Tuple[float, float]]:
    """
    Return band name -> (fmin_hz, fmax_hz). Merges config overrides with defaults.
    config: VisualizationConfig or dict with optional 'band_definitions' key
            (e.g. { delta: [1, 4], theta: [4, 8], ... }).
    """
    result = dict(DEFAULT_BAND_DEFINITIONS)
    if config is None:
        return result
    try:
        bd = config.get('band_definitions', {}) if hasattr(config, 'get') else {}
        if not bd or not isinstance(bd, dict):
            return result
        for k, v in bd.items():
            key = k.lower() if isinstance(k, str) else k
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                result[key] = (float(v[0]), float(v[1]))
    except Exception:
        pass
    return result


def get_band_frequency_range_str(band: str, definitions: Optional[Dict[str, Tuple[float, float]]] = None) -> str:
    """
    Return frequency range string for a band (e.g. "4.0-8.0 Hz").
    definitions: optional band -> (fmin, fmax); if None, uses get_band_definitions().
    """
    defs = definitions if definitions is not None else get_band_definitions()
    band_lower = band.lower() if isinstance(band, str) else band
    if band_lower in defs:
        low, high = defs[band_lower]
        return f"{low:.1f}-{high:.1f} Hz"
    return ""
