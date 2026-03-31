#!/usr/bin/env python3
"""
EEG Paradox Theme Manager

Manages color schemes, palettes, and visual styling for EEG visualizations
with the EEG Paradox dark theme aesthetic. Supports config and user-selectable
palettes via enhanced_color_palettes, with fallback to built-in Paradox theme.

Adapted from EEG Paradox Decoder (cracker.visualization.theme_manager)
for the Super Bot / hexnode project. Optional cracker-specific imports
(config_manager, enhanced_color_palettes, z_score_severity) have been
removed; all try/except blocks fall through to their built-in defaults.

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
from matplotlib import patheffects as pe
from matplotlib.colors import LinearSegmentedColormap
from pathlib import Path
from typing import Dict, Tuple, Optional, Any
import logging

logger = logging.getLogger(__name__)

# Path for user palette preferences (overrides config)
_VIZ_PREFS_PATH: Optional[Path] = None

def _get_viz_prefs_path() -> Path:
    global _VIZ_PREFS_PATH
    if _VIZ_PREFS_PATH is None:
        try:
            raise ImportError("config_manager not available in hexnode")
        except Exception:
            base = Path(__file__).parent.parent.parent
        _VIZ_PREFS_PATH = base / "config" / "viz_preferences.json"
    return _VIZ_PREFS_PATH

def _load_palette_preferences() -> Dict[str, str]:
    """Load user palette preferences from file. Returns {} if not found."""
    try:
        p = _get_viz_prefs_path()
        if p.exists():
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("palettes", {})
    except Exception as e:
        logger.debug(f"Could not load viz preferences: {e}")
    return {}

def _save_palette_preferences(prefs: Dict[str, Any]) -> None:
    """Save user palette preferences to file."""
    try:
        p = _get_viz_prefs_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {"palettes": prefs}
        if p.exists():
            with open(p, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            existing.update(data)
            data = existing
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save viz preferences: {e}")


def get_remontage_preference() -> str:
    """Load remontage/reference method preference. Returns '', 'average', or 'laplacian'."""
    try:
        p = _get_viz_prefs_path()
        if p.exists():
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            ref = (data.get("remontage_reference") or "").strip().lower()
            if ref in ("", "none", "average", "laplacian", "csd"):
                return "" if ref in ("", "none") else ref
    except Exception as e:
        logger.debug(f"Could not load remontage preference: {e}")
    return ""


def set_remontage_preference(ref: str) -> None:
    """Save remontage/reference method preference."""
    ref = (ref or "").strip().lower()
    if ref in ("none", "skip"):
        ref = ""
    if ref and ref not in ("average", "laplacian", "csd"):
        ref = ""
    try:
        p = _get_viz_prefs_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {"remontage_reference": ref}
        if p.exists():
            with open(p, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            existing.update(data)
            data = existing
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save remontage preference: {e}")

# ===== EEG PARADOX THEME COLORS =====

CYBER_BG = '#0a0f17'      # deep ink background
CYBER_FG = '#d6f6ff'       # pale neon text
NEON_CYAN = '#52e8fc'
NEON_MAGENTA = '#ff2bd6'
NEON_LIME = '#b7ff00'
NEON_YELLOW = '#ffe600'
NEON_ORANGE = '#ff8a00'
NEON_RED = '#ff3355'
NEON_PURPLE = '#9b5cff'

# Optional band colors for legends/labels (paradox theme; power colormap unchanged)
PARADOX_BAND_COLORS = {
    "delta": "#FF006E",
    "theta": "#00FF88",
    "alpha": "#00D4FF",
    "beta": "#FF6B35",
    "gamma": "#FFD700",
    "smr": "#B967DB",
    "hibeta": "#00FFE5",
}

# Clinical-grade 10-20 positions (exact NeuroGuide coordinates)
CLINICAL_1020_POSITIONS = {
    'Fp1': (-0.31, 0.95), 'Fpz': (0.0, 0.95), 'Fp2': (0.31, 0.95),
    'F7': (-0.71, 0.71), 'F3': (-0.45, 0.71), 'Fz': (0.0, 0.71), 
    'F4': (0.45, 0.71), 'F8': (0.71, 0.71),
    'T7': (-0.95, 0.31), 'C3': (-0.45, 0.31), 'Cz': (0.0, 0.31),
    'C4': (0.45, 0.31), 'T8': (0.95, 0.31),
    'T3': (-0.95, 0.31), 'T4': (0.95, 0.31),  # Old nomenclature
    'P7': (-0.71, -0.31), 'P3': (-0.45, -0.31), 'Pz': (0.0, -0.31),
    'P4': (0.45, -0.31), 'P8': (0.71, -0.31),
    'T5': (-0.71, -0.31), 'T6': (0.71, -0.31),  # Old nomenclature
    'O1': (-0.31, -0.95), 'Oz': (0.0, -0.95), 'O2': (0.31, -0.95),
    'FP1': (-0.31, 0.95), 'FPZ': (0.0, 0.95), 'FP2': (0.31, 0.95),
    'FZ': (0.0, 0.71), 'CZ': (0.0, 0.31), 'PZ': (0.0, -0.31), 'OZ': (0.0, -0.95)
}


class ThemeManager:
    """Manages EEG Paradox theme colors, palettes, and styling"""
    
    def __init__(self):
        """Initialize theme manager with EEG Paradox color scheme"""
        self.bg_color = CYBER_BG
        self.fg_color = CYBER_FG
        self.NEON_CYAN = NEON_CYAN
        self.NEON_MAGENTA = NEON_MAGENTA
        self.NEON_LIME = NEON_LIME
        self.NEON_YELLOW = NEON_YELLOW
        self.NEON_ORANGE = NEON_ORANGE
        self.NEON_RED = NEON_RED
        self.NEON_PURPLE = NEON_PURPLE
        self._paradox_div_cmap = None
        self._paradox_seq_cmap = None
        self._palette_manager = None
        self._palette_seq_cache: Dict[str, LinearSegmentedColormap] = {}
        self._palette_div_cache: Dict[str, LinearSegmentedColormap] = {}
        self._initialize_colormaps()
    
    def _initialize_colormaps(self):
        """Initialize EEG Paradox colormaps (built-in fallback)"""
        self._paradox_div_cmap = LinearSegmentedColormap.from_list(
            'paradox_div',
            ['#2166ac', '#4393c3', '#92c5de', '#d1e5f0', '#f7f7f7',
             '#fddbc7', '#f4a582', '#d6604d', '#b2182b'],
            N=256
        )

        self._paradox_seq_cmap = LinearSegmentedColormap.from_list(
            'paradox_seq',
            ['#162133', '#173a5e', '#1c6aa7', NEON_CYAN, NEON_LIME, NEON_YELLOW, NEON_ORANGE],
            N=256
        )
    
    def _get_palette_manager(self):
        """Lazy-load ColorPaletteManager. Returns None (no enhanced palettes in hexnode)."""
        if self._palette_manager is None:
            try:
                raise ImportError("enhanced_color_palettes not available in hexnode")
            except ImportError as e:
                logger.warning(f"Could not load enhanced_color_palettes: {e}")
        return self._palette_manager
    
    def _get_effective_palette_names(self) -> Tuple[str, str]:
        """Get effective palette names: user prefs override config."""
        seq, div = "paradox", "paradox"
        prefs = _load_palette_preferences()
        if prefs:
            seq = prefs.get("sequential", seq)
            div = prefs.get("diverging", div)
        if seq == "paradox" and div == "paradox":
            try:
                raise ImportError("config_manager not available in hexnode")
            except Exception as e:
                logger.debug(f"Could not load palette config: {e}")
        return (seq or "paradox", div or "paradox")
    
    def set_palette_preference(self, sequential: str, diverging: str) -> None:
        """Set user palette preference (saved to viz_preferences.json)."""
        _save_palette_preferences({"sequential": sequential, "diverging": diverging})
        self._palette_seq_cache.clear()
        self._palette_div_cache.clear()
    
    def get_palette_preferences(self) -> Dict[str, str]:
        """Get current effective palette preferences."""
        seq, div = self._get_effective_palette_names()
        return {"sequential": seq, "diverging": div}
    
    def get_diverging_colormap(self):
        """Get diverging colormap for z-scores. Uses config/prefs or fallback to Paradox."""
        _, div_name = self._get_effective_palette_names()
        if not div_name or div_name.lower() in ("paradox", "default"):
            return self._paradox_div_cmap
        if div_name in self._palette_div_cache:
            return self._palette_div_cache[div_name]
        pm = self._get_palette_manager()
        if pm:
            try:
                palette = pm.get_palette(div_name)
                if palette and palette.is_diverging:
                    cmap = pm.create_diverging_colormap(div_name)
                else:
                    cmap = pm.create_colormap(div_name)
                self._palette_div_cache[div_name] = cmap
                return cmap
            except Exception as e:
                logger.warning(f"Could not load palette '{div_name}', using Paradox: {e}")
        return self._paradox_div_cmap
    
    def get_sequential_colormap(self):
        """Get sequential colormap for power. Uses config/prefs or fallback to Paradox."""
        seq_name, _ = self._get_effective_palette_names()
        if not seq_name or seq_name.lower() in ("paradox", "default"):
            return self._paradox_seq_cmap
        if seq_name in self._palette_seq_cache:
            return self._palette_seq_cache[seq_name]
        pm = self._get_palette_manager()
        if pm:
            try:
                cmap = pm.create_colormap(seq_name)
                self._palette_seq_cache[seq_name] = cmap
                return cmap
            except Exception as e:
                logger.warning(f"Could not load palette '{seq_name}', using Paradox: {e}")
        return self._paradox_seq_cmap
    
    def get_background_color(self) -> str:
        """Get background color"""
        return self.bg_color
    
    def get_foreground_color(self) -> str:
        """Get foreground/text color"""
        return self.fg_color
    
    def apply_dark_theme(self, fig=None, ax=None):
        """Apply dark theme to figure and/or axes"""
        if fig is not None:
            fig.patch.set_facecolor(self.bg_color)
        
        if ax is not None:
            ax.set_facecolor(self.bg_color)
            ax.spines['bottom'].set_color(self.fg_color)
            ax.spines['top'].set_color(self.fg_color)
            ax.spines['right'].set_color(self.fg_color)
            ax.spines['left'].set_color(self.fg_color)
            ax.tick_params(colors=self.fg_color)
            ax.xaxis.label.set_color(self.fg_color)
            ax.yaxis.label.set_color(self.fg_color)
            ax.title.set_color(self.fg_color)
    
    def get_region_color(self, channel: str) -> str:
        """
        Get color for brain region based on channel name
        
        Args:
            channel: Channel name (e.g., 'F3', 'Cz', 'O1')
            
        Returns:
            Color hex string
        """
        ch = channel.upper()
        if ch.startswith('F'):
            return NEON_MAGENTA
        if ch.startswith('C'):
            return NEON_CYAN
        if ch.startswith('P'):
            return NEON_LIME
        if ch.startswith('O'):
            return NEON_YELLOW
        if ch.startswith('T'):
            return NEON_PURPLE
        return self.fg_color
    
    def get_severity_color(self, z_score: float) -> str:
        """
        Get color for severity based on z-score.
        Thresholds: |z| >= 2.5 Severe (red), >= 2.0 Abnormal (orange), >= 1.5 Moderate (yellow).
        """
        az = abs(float(z_score))
        try:
            raise ImportError("z_score_severity not available in hexnode")
        except Exception:
            severe_t, abnormal_t, moderate_t = 2.5, 2.0, 1.5
        if az >= severe_t:
            return NEON_RED
        if az >= abnormal_t:
            return NEON_ORANGE
        if az >= moderate_t:
            return NEON_YELLOW
        return self.fg_color

    def get_band_color(self, band: str) -> str:
        """
        Optional: get paradox theme color for a frequency band (legends, labels).
        Returns hex string; unknown band returns foreground color.
        """
        key = (band or "").strip().lower()
        return PARADOX_BAND_COLORS.get(key, self.fg_color)
    
    TRACE_ANNOTATION_COLORS = {
        'condition': '#00FF41',
        'norm_violation': '#FF6B00',
        'seizure': '#FF0040',
        'artifact': '#FFAA00',
        'coherence': '#00FFFF',
        'phenotype': '#BF00FF',
        'tbi': '#FF3333',
        'epoch_boundary': '#00FF88',
        'mne_annotation': '#00D4FF',
    }
    
    def get_trace_annotation_style(
        self,
        ann_type: str,
        base_color: str = '#FFD700',
        overlay_style: str = 'clinical'
    ) -> Dict[str, Any]:
        """
        Get annotation style for trace viewer (skin only).
        overlay_style: 'clinical' (subtle) or 'esp' (color + line weight only; no extra geometry).
        """
        color = self.TRACE_ANNOTATION_COLORS.get(ann_type, base_color) if overlay_style == 'esp' else base_color
        if overlay_style == 'esp':
            return {'opacity': 0.9, 'line_width': 3, 'color': color, 'glow': False, 'glow_spread': 0}
        return {'opacity': 0.4, 'line_width': 2, 'color': color, 'glow': False, 'glow_spread': 0}
    
    def get_halo_effect(self, linewidth: float = 3.5, color: str = 'black', alpha: float = 0.9):
        """Get path effects for text/lines with outer glow"""
        return [pe.withStroke(linewidth=linewidth, foreground=color, alpha=alpha)]
    
    def get_channel_positions(self, channel_names: list) -> Dict[str, Tuple[float, float]]:
        """
        Get 10-20 positions for channels
        
        Args:
            channel_names: List of channel names
            
        Returns:
            Dictionary mapping channel names to (x, y) positions
        """
        positions = {}
        for ch_name in channel_names:
            clean_name = ch_name.replace('-LE', '').replace('-RE', '').replace('-REF', '')
            clean_name = clean_name.replace('-M1', '').replace('-M2', '')
            clean_name = ''.join(c for c in clean_name if c.isalnum() or c in '-_')
            clean_name = clean_name.strip()
            
            if clean_name in CLINICAL_1020_POSITIONS:
                positions[ch_name] = CLINICAL_1020_POSITIONS[clean_name]
            else:
                found = False
                for key, pos in CLINICAL_1020_POSITIONS.items():
                    if key.upper() == clean_name.upper():
                        positions[ch_name] = pos
                        found = True
                        break
                
                if not found:
                    positions[ch_name] = self._estimate_position(clean_name)
        
        return positions
    
    def _estimate_position(self, channel_name: str) -> Tuple[float, float]:
        """Estimate channel position based on naming conventions"""
        letters = ''.join([c for c in channel_name if c.isalpha()])
        numbers = ''.join([c for c in channel_name if c.isdigit()])
        
        if 'F' in letters.upper():
            y = 0.7
        elif 'C' in letters.upper():
            y = 0.5
        elif 'P' in letters.upper():
            y = 0.3
        elif 'O' in letters.upper():
            y = 0.1
        else:
            y = 0.5
        
        if any(side in numbers for side in ['1', '3', '5', '7', '9']):
            x = -0.35
        elif any(side in numbers for side in ['2', '4', '6', '8', '10']):
            x = 0.35
        elif 'Z' in letters.upper():
            x = 0.0
        else:
            x = 0.0
        
        return (x, y)
    
    def get_frequency_band_color(self, band: str) -> str:
        """
        Get color for frequency band
        
        Args:
            band: Frequency band name (delta, theta, alpha, beta, gamma, smr, hibeta)
            
        Returns:
            Color hex string
        """
        band_lower = band.lower()
        color_map = {
            'delta': NEON_RED,
            'theta': NEON_YELLOW,
            'alpha': NEON_CYAN,
            'beta': NEON_MAGENTA,
            'gamma': NEON_PURPLE,
            'smr': NEON_LIME,
            'hibeta': NEON_ORANGE
        }
        return color_map.get(band_lower, self.fg_color)


# Global theme manager instance
_theme_manager = None

def get_theme_manager() -> ThemeManager:
    """Get global theme manager instance"""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager
