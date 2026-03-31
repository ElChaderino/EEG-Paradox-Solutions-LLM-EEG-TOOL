#!/usr/bin/env python3
"""
Connectivity Renderer for Topo Sheets

Draws line diagrams between electrodes on a head outline for:
- Amplitude Asymmetry (left-right differences, red/blue clinical convention)
- Coherence (pair connectivity, thickness/color by value, NeuroGuide-style)
- Phase Lag (pair phase differences when data available)

NeuroGuide-style: red = left dominant/elevated, blue = right dominant/reduced;
line thickness encodes magnitude; blue-yellow-red colormap for coherence/phase.

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

from hexnode.eeg.viz.theme_manager import get_theme_manager, CLINICAL_1020_POSITIONS
from hexnode.eeg.viz.utils import clean_channel_name

logger = logging.getLogger(__name__)

# Homologous left-right pairs for amplitude asymmetry (RyHa style)
ASYMMETRY_PAIRS = [
    ('Fp1', 'Fp2'), ('F7', 'F8'), ('F3', 'F4'), ('T7', 'T8'),
    ('C3', 'C4'), ('P7', 'P8'), ('P3', 'P4'), ('O1', 'O2')
]

# Interhemispheric pairs commonly used for coherence display
COHERENCE_PAIRS_INTERHEM = [
    ('Fp1', 'Fp2'), ('F3', 'F4'), ('C3', 'C4'), ('P3', 'P4'), ('O1', 'O2'),
    ('F7', 'F8'), ('T7', 'T8'), ('P7', 'P8')
]


def _get_position(ch: str, theme=None) -> Optional[Tuple[float, float]]:
    """Get (x, y) position for channel, normalized to head circle.
    Falls back to theme._estimate_position for channels not in 10-20 map."""
    clean = clean_channel_name(ch)
    if clean in CLINICAL_1020_POSITIONS:
        return CLINICAL_1020_POSITIONS[clean]
    # Try uppercase
    c_upper = clean.upper()
    for k, v in CLINICAL_1020_POSITIONS.items():
        if k.upper() == c_upper:
            return v
    # Fallback: estimate from naming (F/C/P/O + 1,2,Z)
    if theme is None:
        theme = get_theme_manager()
    return theme._estimate_position(clean)


def plot_connectivity_cell(
    ax,
    pairs_data: List[Tuple[str, str, float]],
    title: str,
    mode: str = 'asymmetry',
    theme=None,
    min_threshold: Optional[float] = None,
    show_legend: bool = True,
    options: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Plot connectivity lines between electrode pairs on a head outline.
    
    Args:
        ax: Matplotlib axes
        pairs_data: List of (ch1, ch2, value). For asymmetry: value = L-R (positive=left>right).
                    For coherence/phase: value = coherence (0-1) or phase (0-1 normalized).
        title: Cell title
        mode: 'asymmetry' | 'coherence' | 'phase'
        theme: ThemeManager instance (uses get_theme_manager if None)
        min_threshold: Minimum |value| to draw (filter weak connections). Auto if None.
        show_legend: Whether to add a small legend/key.
        options: Optional dict with min_threshold, max_pairs (cap number of pairs by |value|).
    
    Returns:
        True if any lines were drawn
    """
    if theme is None:
        theme = get_theme_manager()
    opts = options or {}
    if 'min_threshold' in opts and opts['min_threshold'] is not None:
        min_threshold = float(opts['min_threshold'])
    if opts.get('max_pairs') and len(pairs_data) > int(opts['max_pairs']):
        # Keep top max_pairs by |value|
        pairs_data = sorted(pairs_data, key=lambda x: -abs(x[2]))[: int(opts['max_pairs'])]

    def get_pos(c):
        return _get_position(c, theme)

    # Threshold: filter weak connections
    if not pairs_data:
        ax.set_title(title, color=theme.get_foreground_color(), fontsize=10, fontweight='bold')
        ax.axis('off')
        return False
    vals = [abs(v) for _, _, v in pairs_data]
    max_abs = max(vals) if vals else 0.0
    if min_threshold is None:
        # Auto: exclude bottom ~10% of range to reduce clutter
        pct = np.percentile(vals, 10) if len(vals) >= 4 else 0.0
        min_threshold = min(0.08 * max_abs, pct) if max_abs > 1e-12 else 0.0
    filtered = [(c1, c2, v) for c1, c2, v in pairs_data if abs(v) >= min_threshold]

    # Head outline (NeuroGuide-style: simple clinical schematic)
    head_color = theme.get_foreground_color()
    head_circle = plt.Circle((0, 0), 1.0, fill=False, color=head_color, linewidth=1.2, alpha=0.85)
    ax.add_patch(head_circle)
    ax.plot([0, -0.08, 0.08, 0], [1.0, 1.12, 1.12, 1.0], color=head_color, linewidth=1.0, alpha=0.85)
    for sx in (-1.0, 1.0):
        ear = plt.Circle((sx, 0), 0.08, fill=False, color=head_color, linewidth=1.0, alpha=0.85)
        ax.add_patch(ear)

    from matplotlib.colors import Normalize
    from matplotlib import cm

    drawn = 0
    if mode == 'asymmetry' and filtered:
        # Asymmetry: color by magnitude (blue-white-red), thickness 1-6
        f_vals = [v for _, _, v in filtered]
        vmin, vmax = min(f_vals), max(f_vals)
        span = max(abs(vmax - vmin), 1e-12)
        # Normalize to [-1, 1] for diverging colormap
        norm = Normalize(vmin=-span, vmax=span)
        cmap = cm.get_cmap('RdBu_r')  # red=positive (L>R), blue=negative (R>L)
        val_range = max_abs if max_abs > 1e-12 else 1.0
        for ch1, ch2, value in filtered:
            pos1, pos2 = get_pos(ch1), get_pos(ch2)
            if pos1 is None or pos2 is None:
                continue
            x1, y1, x2, y2 = pos1[0], pos1[1], pos2[0], pos2[1]
            val_abs = abs(value)
            # Thickness 1 to 6 (wider range)
            lw = 1.0 + 5.0 * (val_abs / val_range) if val_range > 0 else 1.0
            lw = min(6.0, max(1.0, lw))
            color = cmap(norm(value))
            ax.plot([x1, x2], [y1, y2], color=color, linewidth=lw, alpha=0.9, zorder=5)
            drawn += 1
    else:
        v_norm = 0.5
        for ch1, ch2, value in filtered:
            pos1, pos2 = get_pos(ch1), get_pos(ch2)
            if pos1 is None or pos2 is None:
                continue
            x1, y1, x2, y2 = pos1[0], pos1[1], pos2[0], pos2[1]
            val_abs = abs(value)
            v_norm = max(0, min(1, float(value))) if mode in ('coherence', 'phase') else 0.5
            norm = Normalize(vmin=0, vmax=1)
            cmap_obj = cm.get_cmap('RdYlBu_r')
            color = cmap_obj(norm(v_norm))
            lw = 1.0 + 5.0 * v_norm  # thickness 1-6
            lw = min(6.0, max(1.0, lw))
            if mode == 'phase' and abs(v_norm - 0.5) > 0.08:
                from matplotlib.patches import FancyArrowPatch
                if v_norm > 0.5:
                    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle='->', mutation_scale=14,
                                                 color=color, linewidth=lw, alpha=0.9, zorder=5))
                else:
                    ax.add_patch(FancyArrowPatch((x2, y2), (x1, y1), arrowstyle='->', mutation_scale=14,
                                                 color=color, linewidth=lw, alpha=0.9, zorder=5))
            else:
                ax.plot([x1, x2], [y1, y2], color=color, linewidth=lw, alpha=0.9, zorder=5)
            drawn += 1

    # Electrode dots
    seen = set()
    for ch1, ch2, _ in filtered:
        for ch in (ch1, ch2):
            if ch in seen:
                continue
            seen.add(ch)
            pos = get_pos(ch)
            if pos is not None:
                ax.scatter(pos[0], pos[1], c=head_color, s=20,
                          edgecolors=theme.get_background_color(), linewidths=0.5, zorder=10, alpha=0.95)

    # Legend / key
    if show_legend and drawn > 0:
        _add_connectivity_legend(ax, mode, theme, max_abs if mode == 'asymmetry' else None)

    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-1.3, 1.3)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title(title, color=theme.get_foreground_color(), fontsize=10, fontweight='bold')
    return drawn > 0


def _add_connectivity_legend(ax, mode: str, theme, asymm_max: Optional[float] = None) -> None:
    """Add a compact legend/key below the head (inside axes, bottom)."""
    fg = theme.get_foreground_color()
    if mode == 'asymmetry':
        ax.text(0.5, 0.02, 'Red=L>R | Blue=R>L | Thick=strong', fontsize=6, color=fg,
                ha='center', va='bottom', transform=ax.transAxes)
    elif mode == 'coherence':
        ax.text(0.5, 0.02, 'Blue=low | Red=high | Thick=strong', fontsize=6, color=fg,
                ha='center', va='bottom', transform=ax.transAxes)
    else:
        ax.text(0.5, 0.02, 'Arrow=direction | Thick=strong', fontsize=6, color=fg,
                ha='center', va='bottom', transform=ax.transAxes)


def _channel_in_set(ch: str, available_clean: set) -> bool:
    """Check if channel (any casing/variant) is in available set of cleaned names."""
    c = clean_channel_name(ch)
    return c in available_clean


def compute_asymmetry_pairs(
    metrics_by_site: Dict[str, Any],
    band: str,
    epoch: Optional[str],
    extract_fn,
) -> List[Tuple[str, str, float]]:
    """
    Compute left-right amplitude asymmetry for homologous pairs.
    Returns list of (left_ch, right_ch, asymmetry) where asymmetry = left_val - right_val.
    Only includes pairs where BOTH channels have data.
    """
    ch_names, values = extract_fn(metrics_by_site, band, epoch)
    if len(ch_names) < 2:
        return []
    ch_to_val = {}
    available_clean = set()
    for i, ch in enumerate(ch_names):
        clean = clean_channel_name(ch)
        ch_to_val[clean] = float(values[i]) if i < len(values) else 0.0
        available_clean.add(clean)
    # Also add uppercase keys for lookup
    for ch in list(ch_to_val.keys()):
        if ch.upper() not in ch_to_val:
            ch_to_val[ch.upper()] = ch_to_val[ch]

    def _get_val(side_ch: str) -> Optional[float]:
        c = clean_channel_name(side_ch)
        if c in ch_to_val:
            return ch_to_val[c]
        if c.upper() in ch_to_val:
            return ch_to_val[c.upper()]
        return None

    pairs = []
    for left, right in ASYMMETRY_PAIRS:
        if not _channel_in_set(left, available_clean) or not _channel_in_set(right, available_clean):
            continue
        vl = _get_val(left)
        vr = _get_val(right)
        if vl is None or vr is None:
            continue
        asymmetry = vl - vr
        pairs.append((left, right, asymmetry))
    return pairs


def get_coherence_pairs_for_band(
    all_pairs_coherence: Dict[str, Dict[str, Dict[str, float]]],
    band: str,
    epoch: Optional[str],
    segments_info: Optional[Dict[str, str]] = None,
    max_pairs: int = 12,
) -> List[Tuple[str, str, float]]:
    """
    Extract coherence values for interhemispheric pairs for a given band.
    Returns list of (ch1, ch2, coherence_value).
    """
    band_map = {'delta': 'Delta', 'theta': 'Theta', 'alpha': 'Alpha', 'beta': 'Beta',
                'hibeta': 'HiBeta', 'smr': 'SMR', 'gamma': 'Gamma'}
    band_key = band_map.get(band.lower(), band.capitalize())
    
    pair_values = []
    for seg_key, pairs_data in all_pairs_coherence.items():
        if not isinstance(pairs_data, dict):
            continue
        seg_epoch = (segments_info or {}).get(seg_key, '')
        if not seg_epoch and isinstance(seg_key, str):
            seg_epoch = 'EO' if 'eo' in seg_key.lower() else ('EC' if 'ec' in seg_key.lower() else '')
        if epoch and seg_epoch and str(seg_epoch).upper() != str(epoch).upper():
            continue
        for pair_key, band_data in pairs_data.items():
            if not isinstance(band_data, dict):
                continue
            val = band_data.get(band_key, band_data.get(band_key.lower(), None))
            if val is None:
                continue
            val = float(val)
            if '-' in pair_key:
                parts = pair_key.replace('_', '-').split('-', 1)
                ch1, ch2 = parts[0].strip(), parts[1].strip()
            else:
                continue
            pair_values.append((ch1, ch2, val))
    
    if not pair_values:
        return []
    from collections import defaultdict
    agg = defaultdict(list)
    for ch1, ch2, v in pair_values:
        k1, k2 = clean_channel_name(ch1), clean_channel_name(ch2)
        key = (min(k1, k2), max(k1, k2))
        agg[key].append(v)
    averaged = [(k[0], k[1], float(np.mean(vals))) for k, vals in agg.items()]
    # Prioritize interhemispheric pairs, then sort by coherence value
    interhem_set = {(min(a, b), max(a, b)) for a, b in COHERENCE_PAIRS_INTERHEM}
    def sort_key(item):
        ch1, ch2, val = item
        k = (min(clean_channel_name(ch1), clean_channel_name(ch2)),
             max(clean_channel_name(ch1), clean_channel_name(ch2)))
        prio = 0 if k in interhem_set else 1
        return (prio, -val)  # interhem first, then by value descending
    averaged.sort(key=sort_key)
    return averaged[:max_pairs]


def get_phase_lag_pairs_for_band(
    all_pairs_phase_lag: Dict[str, Dict[str, Dict[str, float]]],
    band: str,
    epoch: Optional[str],
    segments_info: Optional[Dict[str, str]] = None,
    max_pairs: int = 12,
) -> List[Tuple[str, str, float]]:
    """
    Extract phase lag values (radians) for pairs for a given band.
    Returns list of (ch1, ch2, phase_value).
    Phase is normalized to [0, 1] for display: 0.5 = no lag, 0 = -pi, 1 = +pi.
    """
    band_map = {'delta': 'Delta', 'theta': 'Theta', 'alpha': 'Alpha', 'beta': 'Beta',
                'hibeta': 'HiBeta', 'smr': 'SMR', 'gamma': 'Gamma'}
    band_key = band_map.get(band.lower(), band.capitalize())

    pair_values = []
    for seg_key, pairs_data in all_pairs_phase_lag.items():
        if not isinstance(pairs_data, dict):
            continue
        seg_epoch = (segments_info or {}).get(seg_key, '')
        if not seg_epoch and isinstance(seg_key, str):
            seg_epoch = 'EO' if 'eo' in seg_key.lower() else ('EC' if 'ec' in seg_key.lower() else '')
        if epoch and seg_epoch and str(seg_epoch).upper() != str(epoch).upper():
            continue
        for pair_key, band_data in pairs_data.items():
            if not isinstance(band_data, dict):
                continue
            val = band_data.get(band_key, band_data.get(band_key.lower(), None))
            if val is None:
                continue
            val = float(val)
            if '-' in pair_key:
                parts = pair_key.replace('_', '-').split('-', 1)
                ch1, ch2 = parts[0].strip(), parts[1].strip()
            else:
                continue
            # Normalize phase to [0, 1] for display: (phase + pi) / (2*pi)
            val_norm = (val + np.pi) / (2.0 * np.pi)
            val_norm = max(0, min(1, val_norm))
            pair_values.append((ch1, ch2, val_norm))

    if not pair_values:
        return []
    from collections import defaultdict
    agg = defaultdict(list)
    for ch1, ch2, v in pair_values:
        k1, k2 = clean_channel_name(ch1), clean_channel_name(ch2)
        key = (min(k1, k2), max(k1, k2))
        agg[key].append(v)
    averaged = [(k[0], k[1], float(np.mean(vals))) for k, vals in agg.items()]
    # Prioritize interhemispheric pairs (same as coherence)
    interhem_set = {(min(a, b), max(a, b)) for a, b in COHERENCE_PAIRS_INTERHEM}
    def sort_key(item):
        ch1, ch2, val = item
        k = (min(clean_channel_name(ch1), clean_channel_name(ch2)),
             max(clean_channel_name(ch1), clean_channel_name(ch2)))
        prio = 0 if k in interhem_set else 1
        return (prio, -abs(val - 0.5))  # interhem first, then by phase magnitude
    averaged.sort(key=sort_key)
    return averaged[:max_pairs]
