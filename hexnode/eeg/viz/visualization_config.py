#!/usr/bin/env python3
"""
Visualization Configuration Manager

Manages visualization settings from YAML config and web UI overrides.

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


import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


class VisualizationConfig:
    """Manages visualization configuration from YAML and UI overrides"""
    
    def __init__(self, config_path: Optional[Path] = None, feature_flags_path: Optional[Path] = None):
        """
        Initialize visualization configuration
        
        Args:
            config_path: Path to default.yaml config file (optional; uses hardcoded defaults when absent)
            feature_flags_path: Path to feature_flags.yaml (optional; empty flags when absent)
        """
        self.config_path = config_path
        self.feature_flags_path = feature_flags_path
        self._config = {}
        self._feature_flags = {}
        self._ui_overrides = {}
        self._enhancement_failed = False

        self._load_config()
        self._load_feature_flags()
    
    def _load_config(self):
        """Load configuration from YAML file when a path is provided, otherwise use hardcoded defaults."""
        if self.config_path is None:
            self._config = self._get_default_config()
            logger.info("Using hardcoded default visualization configuration")
            return

        if yaml is None:
            logger.warning("PyYAML not installed; falling back to default config")
            self._config = self._get_default_config()
            return

        try:
            with open(self.config_path, 'r') as f:
                full_config = yaml.safe_load(f) or {}
                self._config = full_config.get('cracker', {}).get('visualization', {})
            user_opts_path = self.config_path.parent / "user_options.yaml"
            if user_opts_path.exists():
                try:
                    with open(user_opts_path, 'r') as uf:
                        user_opts = yaml.safe_load(uf) or {}
                    viz_opts = user_opts.get('cracker', {}).get('visualization', {})
                    if viz_opts:
                        self._config = self._deep_merge(self._config, viz_opts)
                        logger.info("Merged user_options.yaml into visualization config")
                except Exception as ue:
                    logger.debug(f"Could not merge user_options: {ue}")
            logger.info("Loaded visualization configuration")
        except Exception as e:
            logger.warning(f"Failed to load visualization config: {e}")
            self._config = self._get_default_config()

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Recursively merge override into base. Override values take precedence."""
        result = dict(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = VisualizationConfig._deep_merge(result[k], v)
            else:
                result[k] = v
        return result
    
    def _load_feature_flags(self):
        """Load feature flags from YAML file when a path is provided, otherwise empty."""
        if self.feature_flags_path is None:
            self._feature_flags = {}
            return

        if yaml is None:
            logger.warning("PyYAML not installed; feature flags unavailable")
            self._feature_flags = {}
            return

        try:
            with open(self.feature_flags_path, 'r') as f:
                full_flags = yaml.safe_load(f) or {}
                self._feature_flags = full_flags.get('feature_flags', {})
                logger.info("Loaded visualization feature flags")
        except Exception as e:
            logger.warning(f"Failed to load feature flags: {e}")
            self._feature_flags = {}
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration if file loading fails"""
        return {
            'enabled': True,
            'generate_on_report': True,
            'default_format': 'png',
            'default_dpi': 300,
            'theme': 'paradox',
            'cuban_database': {
                'enabled': True,
                'wave1_path': 'data/cuban_databases/cuban_database/data',
                'wave2_path': 'data/cuban_databases/cuban_2nd_wave_database',
                'use_for_z_scores': True,
                'use_for_topomaps': True
            },
            'topomaps': {
                'enabled': True,
                'generate_all_bands': True,
                'generate_z_scores': True,
                'bands': ['delta', 'theta', 'alpha', 'beta', 'gamma', 'smr', 'hibeta'],
                'show_sensors': True,
                'show_contours': True,
                'resolution': 128,
                'paradox_theme': True,
                'use_cuban_database': True,
                'topo_sheets': {
                    'enabled': True,
                    'zscore_summary': True,
                    'zscore_extended': True,
                    'zscore_ratio': True,
                    'bandpower': True,
                    'absolute': True,
                    'relative': True,
                    'diff': True,
                }
            },
            'power_spectra': {
                'enabled': True,
                'frequency_range': [0, 50],
                # 'wineeog_1020' = fixed 5×5 scalp grid; 'spatial_auto' = legacy column packing from positions
                'layout': 'wineeog_1020',
                'grid_layout': 'auto',
                'show_band_colors': True,
                'show_channel_labels': True
            },
            'hypnogram': {
                'enabled': True,
                'generate_on_report': True,
                'resolution': 300,
                'show_confidence': True,
                'show_transitions': True,
                'state_colors': {
                    'alert': '#2E8B57',
                    'relaxed': '#32CD32',
                    'drowsy': '#FFD700',
                    'microsleep': '#FF8C00',
                    'light_sleep': '#4169E1',
                    'deep_sleep': '#000080',
                    'rem_sleep': '#8A2BE2'
                }
            },
            'coherence': {
                'enabled': False,
                'generate_heatmaps': False,
                'generate_topomaps': False
            },
            'visualization_enhancements': {
                'use_high_res': True,
                'use_modern_ui': True,
                'enhanced_dpi': 400,
                'enhanced_topomap_resolution': 256,
                'iframe_height_px': 700,
                'viz_border_radius': 8,
            }
        }
    
    def set_ui_overrides(self, overrides: Dict[str, Any]):
        """
        Set UI overrides for current session
        
        Args:
            overrides: Dictionary of UI override settings
        """
        self._ui_overrides = overrides
        logger.debug(f"Set UI overrides: {overrides}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with UI override support
        
        Args:
            key: Configuration key (supports dot notation, e.g., 'topomaps.enabled')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        if key in self._ui_overrides:
            return self._ui_overrides[key]
        
        if key in self._feature_flags:
            return self._feature_flags[key]
        
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value if value is not None else default
    
    def is_enabled(self) -> bool:
        """Check if visualizations are enabled"""
        return self.get('enabled', True) and self._feature_flags.get('visualizations_enabled', True)
    
    def are_topomaps_enabled(self) -> bool:
        """Check if topomaps are enabled"""
        return (self.is_enabled() and 
                self.get('topomaps.enabled', True) and 
                self._feature_flags.get('topomaps_enabled', True))
    
    def are_power_spectra_enabled(self) -> bool:
        """Check if power spectra are enabled"""
        return (self.is_enabled() and 
                self.get('power_spectra.enabled', True) and 
                self._feature_flags.get('power_spectra_enabled', True))
    
    def are_hypnograms_enabled(self) -> bool:
        """Check if hypnograms are enabled"""
        return (self.is_enabled() and 
                self.get('hypnogram.enabled', True) and 
                self._feature_flags.get('hypnogram_enabled', True))
    
    def are_loreta_enabled(self) -> bool:
        """Check if LORETA visualizations are enabled"""
        return (self.is_enabled() and 
                self.get('loreta.enabled', True))
    
    def are_mahalanobis_enabled(self) -> bool:
        """Check if Mahalanobis visualizations are enabled"""
        return (self.is_enabled() and 
                self.get('mahalanobis.enabled', True))
    
    def are_brain_3d_enabled(self) -> bool:
        """Check if 3D brain visualizations are enabled"""
        return (self.is_enabled() and 
                self.get('brain_3d.enabled', True))
    
    def get_topomap_bands(self) -> List[str]:
        """Get list of bands to generate topomaps for"""
        return self.get('topomaps.bands', ['delta', 'theta', 'alpha', 'beta', 'gamma', 'smr', 'hibeta'])
    
    def get_cuban_database_paths(self) -> Dict[str, str]:
        """Cuban DB paths: absolute when DLC/repo data present, else configured relative strings."""
        try:
            from hexnode.eeg.norms_paths import get_cuban_databases_dir

            cuban = get_cuban_databases_dir()
            if cuban is not None:
                w1 = cuban / "cuban_database" / "data"
                w2 = cuban / "cuban_2nd_wave_database"
                out: Dict[str, str] = {}
                if w1.is_dir():
                    out["wave1"] = str(w1.resolve())
                if w2.is_dir():
                    out["wave2"] = str(w2.resolve())
                if out:
                    return out
        except Exception:
            pass
        return {
            "wave1": self.get("cuban_database.wave1_path", "data/cuban_databases/cuban_database/data"),
            "wave2": self.get("cuban_database.wave2_path", "data/cuban_databases/cuban_2nd_wave_database"),
        }
    
    def should_use_cuban_database(self) -> bool:
        """Check if Cuban database should be used"""
        return (self.get('cuban_database.enabled', True) and 
                self._feature_flags.get('cuban_database_enabled', True))
    
    def get_format(self) -> str:
        """Get default image format"""
        return self.get('default_format', 'png')
    
    def set_enhancement_fallback(self):
        """Mark that enhanced generation failed; get_dpi/get_topomap_resolution will return defaults until next run."""
        self._enhancement_failed = True
        logger.warning("Visualization enhancement failed; using default resolution/DPI for remainder of run.")

    def get_dpi(self) -> int:
        """Get default DPI. Use enhanced_dpi when use_high_res and no prior failure; else fallback to default_dpi."""
        if self._enhancement_failed:
            return self.get('default_dpi', 300)
        enh = self.get('visualization_enhancements') or {}
        if enh.get('use_high_res'):
            dpi = enh.get('enhanced_dpi')
            if isinstance(dpi, (int, float)) and dpi > 0:
                return int(dpi)
        return self.get('default_dpi', 300)

    def get_topomap_resolution(self) -> int:
        """Get topomap grid resolution. Use enhanced when use_high_res and no prior failure; else fallback."""
        if self._enhancement_failed:
            return self.get('topomaps.resolution', 128)
        enh = self.get('visualization_enhancements') or {}
        if enh.get('use_high_res'):
            r = enh.get('enhanced_topomap_resolution')
            if isinstance(r, (int, float)) and r > 0:
                return int(r)
        return self.get('topomaps.resolution', 128)
    
    def get_theme(self) -> str:
        """Get theme name"""
        return self.get('theme', 'paradox')


_config_instance = None

def get_visualization_config(ui_overrides: Optional[Dict[str, Any]] = None) -> VisualizationConfig:
    """
    Get global visualization config instance
    
    Args:
        ui_overrides: Optional UI override settings
        
    Returns:
        VisualizationConfig instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = VisualizationConfig()
    
    if ui_overrides:
        _config_instance.set_ui_overrides(ui_overrides)
    
    return _config_instance
