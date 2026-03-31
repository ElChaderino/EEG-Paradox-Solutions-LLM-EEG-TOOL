#!/usr/bin/env python3
"""
Norm Manager
Unified manager for all normative databases

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


# EEG Norms Reference Table
# Sources: Swingle (2015), Cuban Norms (2017), Average Adult (various)
# Values are typical means or cutoffs for adults unless otherwise noted.

import logging
from typing import Dict, Any, Optional, List

import numpy as np

logger = logging.getLogger(__name__)


class NormManager:
    """
    Unified manager for all normative databases.
    Provides consistent interface for accessing norms from different databases.
    """
    
    def __init__(self):
        """Initialize norm manager."""
        self._cuban2ndwave_loaded: Optional[Dict[str, Dict[str, Any]]] = None  # lazy-loaded from CSV
        self.norms: Dict[str, Dict[str, Any]] = {
            'swingle': {
                'cz': {
                    'theta/beta': {'normal': 2.2, 'borderline': 2.5, 'abnormal': 3.0, 'severe': 4.0},
                    'alpha': {'normal': 50, 'low': 40, 'very_low': 30, 'high': 70},
                    'smr': {'normal': 12, 'low': 8, 'very_low': 6, 'high': 18},
                    'beta': {'normal': 20, 'high': 25, 'very_high': 30, 'low': 12},
                    'delta': {'normal': 15, 'high': 25, 'very_high': 35, 'low': 8},
                    'theta': {'normal': 25, 'high': 35, 'very_high': 50, 'low': 15},
                    'gamma': {'normal': 3, 'high': 6, 'very_high': 10, 'low': 1},
                    'hibeta': {'normal': 12, 'high': 18, 'very_high': 25, 'low': 6}
                },
                'fz': {
                    'theta/beta': {'normal': 2.2, 'borderline': 2.5, 'abnormal': 3.0, 'severe': 4.0},
                    'alpha': {'normal': 40, 'low': 30, 'very_low': 20, 'high': 55},
                    'beta': {'normal': 18, 'high': 25, 'very_high': 32, 'low': 10},
                    'smr': {'normal': 10, 'low': 7, 'very_low': 5, 'high': 15},
                    'delta': {'normal': 12, 'high': 20, 'very_high': 30, 'low': 6},
                    'theta': {'normal': 22, 'high': 32, 'very_high': 45, 'low': 12},
                    'gamma': {'normal': 2.5, 'high': 5, 'very_high': 8, 'low': 1},
                    'hibeta': {'normal': 10, 'high': 16, 'very_high': 22, 'low': 5}
                },
                'o1': {
                    'alpha': {'normal': 40, 'low': 30, 'very_low': 20, 'high': 60},
                    'theta/beta': {'normal': 2.0, 'low': 1.8, 'high': 3.0, 'very_high': 4.0},
                    'beta': {'normal': 15, 'high': 20, 'very_high': 28, 'low': 8},
                    'delta': {'normal': 10, 'high': 18, 'very_high': 28, 'low': 5},
                    'theta': {'normal': 18, 'high': 28, 'very_high': 40, 'low': 10},
                    'smr': {'normal': 8, 'low': 5, 'very_low': 3, 'high': 12},
                    'gamma': {'normal': 2, 'high': 4, 'very_high': 7, 'low': 0.5}
                },
                'o2': {
                    'alpha': {'normal': 40, 'low': 30, 'very_low': 20, 'high': 60},
                    'theta/beta': {'normal': 2.0, 'low': 1.8, 'high': 3.0, 'very_high': 4.0},
                    'beta': {'normal': 15, 'high': 20, 'very_high': 28, 'low': 8},
                    'delta': {'normal': 10, 'high': 18, 'very_high': 28, 'low': 5},
                    'theta': {'normal': 18, 'high': 28, 'very_high': 40, 'low': 10},
                    'smr': {'normal': 8, 'low': 5, 'very_low': 3, 'high': 12},
                    'gamma': {'normal': 2, 'high': 4, 'very_high': 7, 'low': 0.5}
                },
                'pz': {
                    'alpha': {'normal': 45, 'low': 35, 'very_low': 25, 'high': 65},
                    'theta/beta': {'normal': 2.0, 'borderline': 2.3, 'abnormal': 2.8, 'severe': 3.5},
                    'beta': {'normal': 18, 'high': 22, 'very_high': 28, 'low': 12},
                    'delta': {'normal': 12, 'high': 20, 'very_high': 30, 'low': 6},
                    'theta': {'normal': 20, 'high': 30, 'very_high': 42, 'low': 12},
                    'smr': {'normal': 9, 'low': 6, 'very_low': 4, 'high': 14}
                },
                'f3': {
                    'alpha': {'normal': 35, 'low': 25, 'very_low': 15, 'high': 50},
                    'theta/beta': {'normal': 2.1, 'borderline': 2.4, 'abnormal': 2.9, 'severe': 3.8},
                    'beta': {'normal': 18, 'high': 22, 'very_high': 30, 'low': 10},
                    'delta': {'normal': 11, 'high': 18, 'very_high': 28, 'low': 6},
                    'theta': {'normal': 21, 'high': 31, 'very_high': 44, 'low': 12},
                    'smr': {'normal': 9, 'low': 6, 'very_low': 4, 'high': 14},
                    'gamma': {'normal': 2.2, 'high': 4.5, 'very_high': 7.5, 'low': 0.8}
                },
                'f4': {
                    'alpha': {'normal': 35, 'low': 25, 'very_low': 15, 'high': 50},
                    'theta/beta': {'normal': 2.1, 'borderline': 2.4, 'abnormal': 2.9, 'severe': 3.8},
                    'beta': {'normal': 18, 'high': 22, 'very_high': 30, 'low': 10},
                    'delta': {'normal': 11, 'high': 18, 'very_high': 28, 'low': 6},
                    'theta': {'normal': 21, 'high': 31, 'very_high': 44, 'low': 12},
                    'smr': {'normal': 9, 'low': 6, 'very_low': 4, 'high': 14},
                    'gamma': {'normal': 2.2, 'high': 4.5, 'very_high': 7.5, 'low': 0.8}
                },
                't3': {
                    'alpha': {'normal': 30, 'low': 20, 'very_low': 12, 'high': 45},
                    'theta/beta': {'normal': 2.0, 'borderline': 2.3, 'abnormal': 2.8, 'severe': 3.6},
                    'beta': {'normal': 15, 'high': 20, 'very_high': 28, 'low': 8},
                    'delta': {'normal': 10, 'high': 16, 'very_high': 25, 'low': 5},
                    'theta': {'normal': 19, 'high': 28, 'very_high': 40, 'low': 11},
                    'smr': {'normal': 8, 'low': 5, 'very_low': 3, 'high': 12},
                    'gamma': {'normal': 2, 'high': 4, 'very_high': 6.5, 'low': 0.7}
                },
                't4': {
                    'alpha': {'normal': 30, 'low': 20, 'very_low': 12, 'high': 45},
                    'theta/beta': {'normal': 2.0, 'borderline': 2.3, 'abnormal': 2.8, 'severe': 3.6},
                    'beta': {'normal': 15, 'high': 20, 'very_high': 28, 'low': 8},
                    'delta': {'normal': 10, 'high': 16, 'very_high': 25, 'low': 5},
                    'theta': {'normal': 19, 'high': 28, 'very_high': 40, 'low': 11},
                    'smr': {'normal': 8, 'low': 5, 'very_low': 3, 'high': 12},
                    'gamma': {'normal': 2, 'high': 4, 'very_high': 6.5, 'low': 0.7}
                },
            },
            'cuban': {
                'cz': {
                    'theta/beta': {'mean': 1.8, 'sd': 0.4, 'normal': 1.8, 'high': 2.6, 'very_high': 3.4},
                    'alpha': {'mean': 45, 'sd': 10, 'normal': 45, 'low': 25, 'high': 65},
                    'beta': {'mean': 18, 'sd': 5, 'normal': 18, 'low': 8, 'high': 28},
                    'delta': {'mean': 12, 'sd': 4, 'normal': 12, 'high': 20, 'very_high': 28},
                    'theta': {'mean': 20, 'sd': 6, 'normal': 20, 'high': 32, 'very_high': 44},
                    'smr': {'mean': 11, 'sd': 3, 'normal': 11, 'low': 5, 'high': 17}
                },
                'fz': {
                    'theta/beta': {'mean': 1.9, 'sd': 0.4, 'normal': 1.9, 'high': 2.7, 'very_high': 3.5},
                    'alpha': {'mean': 38, 'sd': 9, 'normal': 38, 'low': 20, 'high': 56},
                    'beta': {'mean': 16, 'sd': 4, 'normal': 16, 'low': 8, 'high': 24},
                    'delta': {'mean': 10, 'sd': 3, 'normal': 10, 'high': 16, 'very_high': 22},
                    'theta': {'mean': 18, 'sd': 5, 'normal': 18, 'high': 28, 'very_high': 38},
                    'smr': {'mean': 10, 'sd': 3, 'normal': 10, 'low': 4, 'high': 16}
                },
                'o1': {
                    'alpha': {'mean': 38, 'sd': 8, 'normal': 38, 'low': 22, 'high': 54},
                    'theta/beta': {'mean': 1.7, 'sd': 0.3, 'normal': 1.7, 'high': 2.3, 'very_high': 2.9},
                    'beta': {'mean': 13, 'sd': 3, 'normal': 13, 'low': 7, 'high': 19},
                    'delta': {'mean': 8, 'sd': 2, 'normal': 8, 'high': 12, 'very_high': 16},
                    'theta': {'mean': 15, 'sd': 4, 'normal': 15, 'high': 23, 'very_high': 31},
                    'smr': {'mean': 8, 'sd': 2.5, 'normal': 8, 'low': 3, 'high': 13}
                },
                'o2': {
                    'alpha': {'mean': 38, 'sd': 8, 'normal': 38, 'low': 22, 'high': 54},
                    'theta/beta': {'mean': 1.7, 'sd': 0.3, 'normal': 1.7, 'high': 2.3, 'very_high': 2.9},
                    'beta': {'mean': 13, 'sd': 3, 'normal': 13, 'low': 7, 'high': 19},
                    'delta': {'mean': 8, 'sd': 2, 'normal': 8, 'high': 12, 'very_high': 16},
                    'theta': {'mean': 15, 'sd': 4, 'normal': 15, 'high': 23, 'very_high': 31},
                    'smr': {'mean': 8, 'sd': 2.5, 'normal': 8, 'low': 3, 'high': 13}
                },
                'f3': {
                    'alpha': {'mean': 32, 'sd': 7, 'normal': 32, 'low': 18, 'high': 46},
                    'theta/beta': {'mean': 1.9, 'sd': 0.4, 'normal': 1.9, 'high': 2.7, 'very_high': 3.5},
                    'beta': {'mean': 15, 'sd': 4, 'normal': 15, 'low': 7, 'high': 23},
                    'delta': {'mean': 9, 'sd': 3, 'normal': 9, 'high': 15, 'very_high': 21},
                    'theta': {'mean': 17, 'sd': 4, 'normal': 17, 'high': 25, 'very_high': 33},
                    'smr': {'mean': 9, 'sd': 2.5, 'normal': 9, 'low': 4, 'high': 14}
                },
                'f4': {
                    'alpha': {'mean': 32, 'sd': 7, 'normal': 32, 'low': 18, 'high': 46},
                    'theta/beta': {'mean': 1.9, 'sd': 0.4, 'normal': 1.9, 'high': 2.7, 'very_high': 3.5},
                    'beta': {'mean': 15, 'sd': 4, 'normal': 15, 'low': 7, 'high': 23},
                    'delta': {'mean': 9, 'sd': 3, 'normal': 9, 'high': 15, 'very_high': 21},
                    'theta': {'mean': 17, 'sd': 4, 'normal': 17, 'high': 25, 'very_high': 33},
                    'smr': {'mean': 9, 'sd': 2.5, 'normal': 9, 'low': 4, 'high': 14}
                },
                'pz': {
                    'alpha': {'mean': 40, 'sd': 9, 'normal': 40, 'low': 22, 'high': 58},
                    'theta/beta': {'mean': 1.8, 'sd': 0.4, 'normal': 1.8, 'high': 2.6, 'very_high': 3.4},
                    'beta': {'mean': 17, 'sd': 4, 'normal': 17, 'low': 9, 'high': 25},
                    'delta': {'mean': 11, 'sd': 3, 'normal': 11, 'high': 17, 'very_high': 23},
                    'theta': {'mean': 19, 'sd': 5, 'normal': 19, 'high': 29, 'very_high': 39},
                    'smr': {'mean': 9, 'sd': 2.5, 'normal': 9, 'low': 4, 'high': 14}
                },
                't3': {
                    'alpha': {'mean': 28, 'sd': 7, 'normal': 28, 'low': 14, 'high': 42},
                    'theta/beta': {'mean': 1.8, 'sd': 0.4, 'normal': 1.8, 'high': 2.6, 'very_high': 3.4},
                    'beta': {'mean': 14, 'sd': 4, 'normal': 14, 'low': 6, 'high': 22},
                    'delta': {'mean': 10, 'sd': 3, 'normal': 10, 'high': 16, 'very_high': 22},
                    'theta': {'mean': 16, 'sd': 5, 'normal': 16, 'high': 26, 'very_high': 36},
                    'smr': {'mean': 8, 'sd': 2.5, 'normal': 8, 'low': 3, 'high': 13}
                },
                't4': {
                    'alpha': {'mean': 28, 'sd': 7, 'normal': 28, 'low': 14, 'high': 42},
                    'theta/beta': {'mean': 1.8, 'sd': 0.4, 'normal': 1.8, 'high': 2.6, 'very_high': 3.4},
                    'beta': {'mean': 14, 'sd': 4, 'normal': 14, 'low': 6, 'high': 22},
                    'delta': {'mean': 10, 'sd': 3, 'normal': 10, 'high': 16, 'very_high': 22},
                    'theta': {'mean': 16, 'sd': 5, 'normal': 16, 'high': 26, 'very_high': 36},
                    'smr': {'mean': 8, 'sd': 2.5, 'normal': 8, 'low': 3, 'high': 13}
                },
                'c3': {
                    'alpha': {'mean': 35, 'sd': 8, 'normal': 35, 'low': 19, 'high': 51},
                    'theta/beta': {'mean': 1.9, 'sd': 0.4, 'normal': 1.9, 'high': 2.7, 'very_high': 3.5},
                    'beta': {'mean': 16, 'sd': 4, 'normal': 16, 'low': 8, 'high': 24},
                    'delta': {'mean': 11, 'sd': 3, 'normal': 11, 'high': 17, 'very_high': 23},
                    'theta': {'mean': 18, 'sd': 5, 'normal': 18, 'high': 28, 'very_high': 38},
                    'smr': {'mean': 10, 'sd': 3, 'normal': 10, 'low': 4, 'high': 16}
                },
                'c4': {
                    'alpha': {'mean': 35, 'sd': 8, 'normal': 35, 'low': 19, 'high': 51},
                    'theta/beta': {'mean': 1.9, 'sd': 0.4, 'normal': 1.9, 'high': 2.7, 'very_high': 3.5},
                    'beta': {'mean': 16, 'sd': 4, 'normal': 16, 'low': 8, 'high': 24},
                    'delta': {'mean': 11, 'sd': 3, 'normal': 11, 'high': 17, 'very_high': 23},
                    'theta': {'mean': 18, 'sd': 5, 'normal': 18, 'high': 28, 'very_high': 38},
                    'smr': {'mean': 10, 'sd': 3, 'normal': 10, 'low': 4, 'high': 16}
                },
                'p3': {
                    'alpha': {'mean': 36, 'sd': 8, 'normal': 36, 'low': 20, 'high': 52},
                    'theta/beta': {'mean': 1.8, 'sd': 0.4, 'normal': 1.8, 'high': 2.6, 'very_high': 3.4},
                    'beta': {'mean': 16, 'sd': 4, 'normal': 16, 'low': 8, 'high': 24},
                    'delta': {'mean': 10, 'sd': 3, 'normal': 10, 'high': 16, 'very_high': 22},
                    'theta': {'mean': 18, 'sd': 5, 'normal': 18, 'high': 28, 'very_high': 38},
                    'smr': {'mean': 9, 'sd': 2.5, 'normal': 9, 'low': 4, 'high': 14}
                },
                'p4': {
                    'alpha': {'mean': 36, 'sd': 8, 'normal': 36, 'low': 20, 'high': 52},
                    'theta/beta': {'mean': 1.8, 'sd': 0.4, 'normal': 1.8, 'high': 2.6, 'very_high': 3.4},
                    'beta': {'mean': 16, 'sd': 4, 'normal': 16, 'low': 8, 'high': 24},
                    'delta': {'mean': 10, 'sd': 3, 'normal': 10, 'high': 16, 'very_high': 22},
                    'theta': {'mean': 18, 'sd': 5, 'normal': 18, 'high': 28, 'very_high': 38},
                    'smr': {'mean': 9, 'sd': 2.5, 'normal': 9, 'low': 4, 'high': 14}
                },
            },
            'cuban2ndwave': {
                # Cuban 2nd Wave normative values (extracted from database with site-specific data)
                # Extracted from z_scores.csv using channel_index mapping to calculate site-specific norms
                'cz': {
                    'theta/beta': {'mean': 2.76, 'sd': 0.55, 'normal': 2.76, 'high': 3.31, 'very_high': 3.87},
                    'alpha': {'mean': 33.98, 'sd': 18.85, 'normal': 33.98, 'low': 15.13, 'high': 52.83},
                    'beta': {'mean': 23.31, 'sd': 13.30, 'normal': 23.31, 'low': 10.01, 'high': 36.61},
                    'delta': {'mean': 75.41, 'sd': 14.43, 'normal': 75.41, 'low': 60.98, 'high': 89.84},
                    'theta': {'mean': 64.36, 'sd': 15.42, 'normal': 64.36, 'low': 48.94, 'high': 79.78},
                    'gamma': {'mean': 67.00, 'sd': 6.26, 'normal': 67.00, 'low': 60.74, 'high': 73.25},
                    'hibeta': {'mean': 73.89, 'sd': 10.23, 'normal': 73.89, 'low': 63.66, 'high': 84.12}
                },
                'fz': {
                    'theta/beta': {'mean': 3.03, 'sd': 0.61, 'normal': 3.03, 'high': 3.64, 'very_high': 4.25},
                    'alpha': {'mean': 33.65, 'sd': 22.29, 'normal': 33.65, 'low': 11.36, 'high': 55.94},
                    'beta': {'mean': 21.88, 'sd': 12.17, 'normal': 21.88, 'low': 9.72, 'high': 34.05},
                    'delta': {'mean': 75.27, 'sd': 16.91, 'normal': 75.27, 'low': 58.36, 'high': 92.18},
                    'theta': {'mean': 66.37, 'sd': 14.46, 'normal': 66.37, 'low': 51.91, 'high': 80.83},
                    'gamma': {'mean': 67.11, 'sd': 5.74, 'normal': 67.11, 'low': 61.37, 'high': 72.84},
                    'hibeta': {'mean': 75.22, 'sd': 9.63, 'normal': 75.22, 'low': 65.59, 'high': 84.84}
                },
                'f3': {
                    'theta/beta': {'mean': 2.75, 'sd': 0.55, 'normal': 2.75, 'high': 3.30, 'very_high': 3.86},
                    'alpha': {'mean': 34.82, 'sd': 18.83, 'normal': 34.82, 'low': 15.99, 'high': 53.65},
                    'beta': {'mean': 24.13, 'sd': 13.33, 'normal': 24.13, 'low': 10.79, 'high': 37.46},
                    'delta': {'mean': 75.72, 'sd': 16.79, 'normal': 75.72, 'low': 58.93, 'high': 92.50},
                    'theta': {'mean': 66.44, 'sd': 15.21, 'normal': 66.44, 'low': 51.23, 'high': 81.65},
                    'gamma': {'mean': 67.70, 'sd': 6.82, 'normal': 67.70, 'low': 60.88, 'high': 74.51},
                    'hibeta': {'mean': 74.95, 'sd': 9.59, 'normal': 74.95, 'low': 65.36, 'high': 84.53}
                },
                'f4': {
                    'theta/beta': {'mean': 2.98, 'sd': 0.60, 'normal': 2.98, 'high': 3.58, 'very_high': 4.17},
                    'alpha': {'mean': 33.05, 'sd': 20.47, 'normal': 33.05, 'low': 12.58, 'high': 53.52},
                    'beta': {'mean': 23.28, 'sd': 13.43, 'normal': 23.28, 'low': 9.85, 'high': 36.71},
                    'delta': {'mean': 71.45, 'sd': 17.75, 'normal': 71.45, 'low': 53.70, 'high': 89.20},
                    'theta': {'mean': 69.37, 'sd': 13.70, 'normal': 69.37, 'low': 55.67, 'high': 83.06},
                    'gamma': {'mean': 68.07, 'sd': 6.81, 'normal': 68.07, 'low': 61.26, 'high': 74.89},
                    'hibeta': {'mean': 75.71, 'sd': 9.66, 'normal': 75.71, 'low': 66.05, 'high': 85.38}
                },
                'o1': {
                    'theta/beta': {'mean': 3.40, 'sd': 0.68, 'normal': 3.40, 'high': 4.08, 'very_high': 4.76},
                    'alpha': {'mean': 37.51, 'sd': 21.06, 'normal': 37.51, 'low': 16.45, 'high': 58.57},
                    'beta': {'mean': 19.73, 'sd': 13.70, 'normal': 19.73, 'low': 6.03, 'high': 33.43},
                    'delta': {'mean': 73.36, 'sd': 14.91, 'normal': 73.36, 'low': 58.45, 'high': 88.27},
                    'theta': {'mean': 67.08, 'sd': 14.14, 'normal': 67.08, 'low': 52.93, 'high': 81.22},
                    'gamma': {'mean': 65.84, 'sd': 7.99, 'normal': 65.84, 'low': 57.85, 'high': 73.84},
                    'hibeta': {'mean': 74.44, 'sd': 10.58, 'normal': 74.44, 'low': 63.86, 'high': 85.01}
                },
                'o2': {
                    'theta/beta': {'mean': 2.98, 'sd': 0.60, 'normal': 2.98, 'high': 3.58, 'very_high': 4.18},
                    'alpha': {'mean': 37.39, 'sd': 17.86, 'normal': 37.39, 'low': 19.53, 'high': 55.25},
                    'beta': {'mean': 21.92, 'sd': 13.56, 'normal': 21.92, 'low': 8.36, 'high': 35.47},
                    'delta': {'mean': 78.06, 'sd': 16.90, 'normal': 78.06, 'low': 61.17, 'high': 94.96},
                    'theta': {'mean': 65.37, 'sd': 14.58, 'normal': 65.37, 'low': 50.79, 'high': 79.95},
                    'gamma': {'mean': 67.04, 'sd': 7.94, 'normal': 67.04, 'low': 59.10, 'high': 74.98},
                    'hibeta': {'mean': 76.62, 'sd': 9.28, 'normal': 76.62, 'low': 67.34, 'high': 85.89}
                },
                'pz': {
                    'theta/beta': {'mean': 2.93, 'sd': 0.59, 'normal': 2.93, 'high': 3.51, 'very_high': 4.10},
                    'alpha': {'mean': 32.99, 'sd': 19.91, 'normal': 32.99, 'low': 13.08, 'high': 52.90},
                    'beta': {'mean': 21.96, 'sd': 13.80, 'normal': 21.96, 'low': 8.16, 'high': 35.76},
                    'delta': {'mean': 72.11, 'sd': 15.37, 'normal': 72.11, 'low': 56.74, 'high': 87.49},
                    'theta': {'mean': 64.28, 'sd': 16.03, 'normal': 64.28, 'low': 48.26, 'high': 80.31},
                    'gamma': {'mean': 68.24, 'sd': 6.13, 'normal': 68.24, 'low': 62.11, 'high': 74.37},
                    'hibeta': {'mean': 75.21, 'sd': 8.95, 'normal': 75.21, 'low': 66.26, 'high': 84.16}
                },
                't3': {
                    'theta/beta': {'mean': 3.14, 'sd': 0.63, 'normal': 3.14, 'high': 3.77, 'very_high': 4.40},
                    'alpha': {'mean': 36.03, 'sd': 19.15, 'normal': 36.03, 'low': 16.88, 'high': 55.18},
                    'beta': {'mean': 21.05, 'sd': 14.92, 'normal': 21.05, 'low': 6.13, 'high': 35.97},
                    'delta': {'mean': 77.00, 'sd': 15.61, 'normal': 77.00, 'low': 61.38, 'high': 92.61},
                    'theta': {'mean': 66.09, 'sd': 14.16, 'normal': 66.09, 'low': 51.93, 'high': 80.25},
                    'gamma': {'mean': 66.52, 'sd': 6.86, 'normal': 66.52, 'low': 59.66, 'high': 73.39},
                    'hibeta': {'mean': 75.30, 'sd': 9.16, 'normal': 75.30, 'low': 66.14, 'high': 84.46}
                },
                't4': {
                    'theta/beta': {'mean': 3.02, 'sd': 0.60, 'normal': 3.02, 'high': 3.62, 'very_high': 4.23},
                    'alpha': {'mean': 33.34, 'sd': 18.52, 'normal': 33.34, 'low': 14.83, 'high': 51.86},
                    'beta': {'mean': 22.36, 'sd': 14.21, 'normal': 22.36, 'low': 8.14, 'high': 36.57},
                    'delta': {'mean': 76.05, 'sd': 16.86, 'normal': 76.05, 'low': 59.19, 'high': 92.91},
                    'theta': {'mean': 67.53, 'sd': 14.53, 'normal': 67.53, 'low': 53.00, 'high': 82.06},
                    'gamma': {'mean': 66.87, 'sd': 6.28, 'normal': 66.87, 'low': 60.59, 'high': 73.15},
                    'hibeta': {'mean': 74.56, 'sd': 9.60, 'normal': 74.56, 'low': 64.96, 'high': 84.16}
                },
                'c3': {
                    'theta/beta': {'mean': 3.01, 'sd': 0.60, 'normal': 3.01, 'high': 3.61, 'very_high': 4.21},
                    'alpha': {'mean': 35.43, 'sd': 19.87, 'normal': 35.43, 'low': 15.56, 'high': 55.31},
                    'beta': {'mean': 21.47, 'sd': 11.87, 'normal': 21.47, 'low': 9.61, 'high': 33.34},
                    'delta': {'mean': 72.97, 'sd': 16.24, 'normal': 72.97, 'low': 56.73, 'high': 89.21},
                    'theta': {'mean': 64.60, 'sd': 13.37, 'normal': 64.60, 'low': 51.23, 'high': 77.97},
                    'gamma': {'mean': 67.80, 'sd': 6.87, 'normal': 67.80, 'low': 60.94, 'high': 74.67},
                    'hibeta': {'mean': 75.01, 'sd': 8.88, 'normal': 75.01, 'low': 66.13, 'high': 83.89}
                },
                'c4': {
                    'theta/beta': {'mean': 2.79, 'sd': 0.56, 'normal': 2.79, 'high': 3.35, 'very_high': 3.91},
                    'alpha': {'mean': 38.26, 'sd': 20.01, 'normal': 38.26, 'low': 18.26, 'high': 58.27},
                    'beta': {'mean': 23.92, 'sd': 12.13, 'normal': 23.92, 'low': 11.79, 'high': 36.05},
                    'delta': {'mean': 75.92, 'sd': 16.98, 'normal': 75.92, 'low': 58.94, 'high': 92.90},
                    'theta': {'mean': 66.79, 'sd': 14.62, 'normal': 66.79, 'low': 52.17, 'high': 81.42},
                    'gamma': {'mean': 67.32, 'sd': 6.86, 'normal': 67.32, 'low': 60.46, 'high': 74.19},
                    'hibeta': {'mean': 76.43, 'sd': 10.99, 'normal': 76.43, 'low': 65.44, 'high': 87.42}
                },
                'p3': {
                    'theta/beta': {'mean': 3.02, 'sd': 0.60, 'normal': 3.02, 'high': 3.63, 'very_high': 4.23},
                    'alpha': {'mean': 31.54, 'sd': 18.26, 'normal': 31.54, 'low': 13.28, 'high': 49.80},
                    'beta': {'mean': 22.02, 'sd': 11.95, 'normal': 22.02, 'low': 10.07, 'high': 33.97},
                    'delta': {'mean': 75.67, 'sd': 15.57, 'normal': 75.67, 'low': 60.10, 'high': 91.24},
                    'theta': {'mean': 66.57, 'sd': 15.49, 'normal': 66.57, 'low': 51.08, 'high': 82.05},
                    'gamma': {'mean': 67.46, 'sd': 7.34, 'normal': 67.46, 'low': 60.12, 'high': 74.81},
                    'hibeta': {'mean': 75.39, 'sd': 10.14, 'normal': 75.39, 'low': 65.26, 'high': 85.53}
                },
                'p4': {
                    'theta/beta': {'mean': 2.96, 'sd': 0.59, 'normal': 2.96, 'high': 3.55, 'very_high': 4.14},
                    'alpha': {'mean': 35.46, 'sd': 16.49, 'normal': 35.46, 'low': 18.97, 'high': 51.94},
                    'beta': {'mean': 23.15, 'sd': 14.88, 'normal': 23.15, 'low': 8.27, 'high': 38.02},
                    'delta': {'mean': 76.99, 'sd': 15.63, 'normal': 76.99, 'low': 61.36, 'high': 92.61},
                    'theta': {'mean': 68.48, 'sd': 15.89, 'normal': 68.48, 'low': 52.59, 'high': 84.36},
                    'gamma': {'mean': 66.79, 'sd': 6.58, 'normal': 66.79, 'low': 60.21, 'high': 73.38},
                    'hibeta': {'mean': 75.28, 'sd': 9.31, 'normal': 75.28, 'low': 65.97, 'high': 84.58}
                },
            },
            'gunkelman': {
                # Gunkelman normative values (2006, 2014)
                'cz': {
                    'theta/beta': {'normal': 2.0, 'adhd_threshold': 2.8, 'severe': 3.5},
                    'alpha': {'normal': 48, 'low': 35, 'very_low': 25},
                    'smr': {'normal': 11, 'low': 7, 'add_threshold': 6},
                    'beta': {'normal': 19, 'anxiety_threshold': 26, 'severe': 32}
                },
                'fz': {
                    'theta/beta': {'normal': 2.1, 'adhd_threshold': 2.9, 'severe': 3.6},
                    'alpha': {'normal': 41, 'depression_threshold': 28, 'severe': 20},
                    'beta': {'normal': 17, 'anxiety_threshold': 24, 'severe': 30}
                },
                'f3': {
                    'alpha': {'normal': 34, 'depression_left': 22, 'severe': 15},
                    'beta': {'normal': 16, 'anxiety_left': 23, 'rumination': 28}
                },
                'f4': {
                    'alpha': {'normal': 34, 'depression_right': 22, 'severe': 15},
                    'beta': {'normal': 16, 'anxiety_right': 23, 'activation': 28}
                }
            },
            'published_norms': {
                # Published normative database values (age-dependent, 2005, 2012)
                'cz': {
                    'alpha': {'mean': 46.2, 'sd': 12.3, 'normal': 46, 'low': 22, 'high': 70},
                    'theta': {'mean': 22.1, 'sd': 7.2, 'normal': 22, 'high': 36, 'very_high': 50},
                    'beta': {'mean': 18.7, 'sd': 5.8, 'normal': 19, 'low': 7, 'high': 30},
                    'delta': {'mean': 13.4, 'sd': 4.9, 'normal': 13, 'high': 23, 'very_high': 33}
                },
                'fz': {
                    'alpha': {'mean': 39.8, 'sd': 11.1, 'normal': 40, 'low': 18, 'high': 62},
                    'theta': {'mean': 19.5, 'sd': 6.8, 'normal': 20, 'high': 33, 'very_high': 46},
                    'beta': {'mean': 16.9, 'sd': 5.2, 'normal': 17, 'low': 6, 'high': 27}
                },
                'o1': {
                    'alpha': {'mean': 37.6, 'sd': 9.4, 'normal': 38, 'low': 19, 'high': 56},
                    'theta': {'mean': 16.2, 'sd': 5.1, 'normal': 16, 'high': 26, 'very_high': 36},
                    'beta': {'mean': 13.8, 'sd': 4.2, 'normal': 14, 'low': 5, 'high': 22}
                },
                'o2': {
                    'alpha': {'mean': 37.6, 'sd': 9.4, 'normal': 38, 'low': 19, 'high': 56},
                    'theta': {'mean': 16.2, 'sd': 5.1, 'normal': 16, 'high': 26, 'very_high': 36},
                    'beta': {'mean': 13.8, 'sd': 4.2, 'normal': 14, 'low': 5, 'high': 22}
                }
            },
            'averageadult': {
                # Combined normative values from multiple sources
               'cz': {
                    'theta/beta': {'mean': 2.0, 'sd': 0.5, 'normal': 2.0, 'adhd': 3.0, 'severe': 4.0},
                    'alpha': {'mean': 48, 'sd': 12, 'normal': 48, 'low': 24, 'high': 72},
                    'beta': {'mean': 19, 'sd': 6, 'normal': 19, 'low': 7, 'high': 31},
                    'delta': {'mean': 13, 'sd': 5, 'normal': 13, 'high': 23, 'very_high': 33},
                    'theta': {'mean': 21, 'sd': 7, 'normal': 21, 'high': 35, 'very_high': 49},
                    'smr': {'mean': 11, 'sd': 3.5, 'normal': 11, 'low': 4, 'high': 18}
                },
                'fz': {
                    'theta/beta': {'mean': 2.1, 'sd': 0.5, 'normal': 2.1, 'adhd': 3.1, 'severe': 4.1},
                    'alpha': {'mean': 39, 'sd': 10, 'normal': 39, 'low': 19, 'high': 59},
                    'beta': {'mean': 17, 'sd': 5, 'normal': 17, 'low': 7, 'high': 27},
                    'delta': {'mean': 10, 'sd': 4, 'normal': 10, 'high': 18, 'very_high': 26},
                    'theta': {'mean': 19, 'sd': 6, 'normal': 19, 'high': 31, 'very_high': 43}
                },
                'o1': {
                    'alpha': {'mean': 39, 'sd': 9, 'normal': 39, 'low': 21, 'high': 57},
                    'theta/beta': {'mean': 1.8, 'sd': 0.4, 'normal': 1.8, 'high': 2.6, 'very_high': 3.4},
                    'beta': {'mean': 14, 'sd': 4, 'normal': 14, 'low': 6, 'high': 22},
                    'delta': {'mean': 9, 'sd': 3, 'normal': 9, 'high': 15, 'very_high': 21},
                    'theta': {'mean': 16, 'sd': 5, 'normal': 16, 'high': 26, 'very_high': 36}
                },
                'o2': {
                    'alpha': {'mean': 39, 'sd': 9, 'normal': 39, 'low': 21, 'high': 57},
                    'theta/beta': {'mean': 1.8, 'sd': 0.4, 'normal': 1.8, 'high': 2.6, 'very_high': 3.4},
                    'beta': {'mean': 14, 'sd': 4, 'normal': 14, 'low': 6, 'high': 22},
                    'delta': {'mean': 9, 'sd': 3, 'normal': 9, 'high': 15, 'very_high': 21},
                    'theta': {'mean': 16, 'sd': 5, 'normal': 16, 'high': 26, 'very_high': 36}
                },
                'f3': {
                    'alpha': {'mean': 33, 'sd': 8, 'normal': 33, 'depression': 20, 'severe': 15},
                    'beta': {'mean': 16, 'sd': 5, 'normal': 16, 'anxiety': 24, 'severe': 30},
                    'theta/beta': {'mean': 2.0, 'sd': 0.5, 'normal': 2.0, 'adhd': 3.0, 'severe': 4.0}
                },
                'f4': {
                    'alpha': {'mean': 33, 'sd': 8, 'normal': 33, 'depression': 20, 'severe': 15},
                    'beta': {'mean': 16, 'sd': 5, 'normal': 16, 'anxiety': 24, 'severe': 30},
                    'theta/beta': {'mean': 2.0, 'sd': 0.5, 'normal': 2.0, 'adhd': 3.0, 'severe': 4.0}
                },
                't3': {
                    'alpha': {'mean': 28, 'sd': 7, 'normal': 28, 'low': 14, 'high': 42},
                    'theta': {'mean': 17, 'sd': 5, 'normal': 17, 'trauma': 28, 'severe': 38},
                    'beta': {'mean': 14, 'sd': 4, 'normal': 14, 'low': 6, 'high': 22}
                },
                't4': {
                    'alpha': {'mean': 28, 'sd': 7, 'normal': 28, 'low': 14, 'high': 42},
                    'theta': {'mean': 17, 'sd': 5, 'normal': 17, 'trauma': 28, 'severe': 38},
                    'beta': {'mean': 14, 'sd': 4, 'normal': 14, 'low': 6, 'high': 22}
                },
            },
        }
        
        # Asymmetry thresholds (based on Gunkelman, Davidson, and others)
        self.asymmetry: Dict[str, Dict[str, Any]] = {
            'f3_f4_alpha': {
                'normal_ratio': {'min': 0.8, 'max': 1.2},  # f3/f4 ratio
                'depression_threshold': 0.65,  # f3 < 65% of f4 suggests depression
                'mania_threshold': 1.5,  # f3 > 150% of f4 suggests mania/activation
                'moderate_asym': 0.7,  # moderate asymmetry threshold
                'severe_asym': 0.5     # severe asymmetry threshold
            },
            'o1_o2_alpha': {
                'normal_ratio': {'min': 0.85, 'max': 1.15},  # o1/o2 ratio
                'significant_asym': 0.75,  # clinically significant asymmetry
                'severe_asym': 0.6     # severe asymmetry
            },
            't3_t4_theta': {
                'normal_ratio': {'min': 0.8, 'max': 1.2},  # t3/t4 ratio
                'trauma_left': 1.3,    # left temporal theta elevation (trauma)
                'trauma_right': 0.7,   # right temporal theta reduction
                'severe_asym': 1.5     # severe temporal asymmetry
            }
        }
        
        # Reactivity norms (EO to EC changes)
        self.reactivity: Dict[str, Dict[str, Any]] = {
            'alpha_reactivity': {
                'normal_increase': {'min': 10, 'max': 40},  # normal alpha increase ec vs eo (µv)
                'poor_reactivity': 5,    # poor reactivity threshold
                'hyperreactivity': 50,   # excessive reactivity
                'paradoxical': -5        # paradoxical reactivity (alpha decreases)
            },
            'smr_reactivity': {
                'normal_change': {'min': -2, 'max': 5},  # normal smr change ec vs eo
                'excessive_increase': 8,  # excessive smr increase
                'excessive_decrease': -5  # excessive smr decrease
            }
        }
    
    # 10-20 site aliases: fallback when site not in norms (e.g. P7->P3, T7->T3)
    _SITE_ALIASES = {
        't7': 't3', 't8': 't4', 'fp1': 'f3', 'fp2': 'f4',
        'p7': 'p3', 'p8': 'p4', 'f7': 'f3', 'f8': 'f4',
    }

    def _ensure_cuban2ndwave_loaded(self) -> None:
        """Lazy-load Cuban 2nd wave norms from CSV (keeps hardcoded as fallback)."""
        if self._cuban2ndwave_loaded is not None:
            return
        try:
            from .cuban_database_loader import load_cuban2ndwave_from_csv
            loaded = load_cuban2ndwave_from_csv()
            if loaded:
                # Merge into cuban2ndwave: loaded fills gaps (P7, P8, Fp1, etc.); hardcoded preferred when both
                nm = self.norms.get('cuban2ndwave', {})
                for site, metrics in loaded.items():
                    if site not in nm:
                        nm[site] = metrics
                    else:
                        for metric, vals in metrics.items():
                            if metric not in nm[site]:
                                nm[site][metric] = vals
                self.norms['cuban2ndwave'] = nm
                self._cuban2ndwave_loaded = loaded
        except Exception as e:
            logger.debug("Cuban CSV load skipped: %s", e)
        self._cuban2ndwave_loaded = self._cuban2ndwave_loaded or {}  # mark attempted

    def get_norm(self, norm_set: str, site: str, metric: str) -> Optional[Dict[str, Any]]:
        """
        Get norm values for a specific site/metric.
        For cuban2ndwave: tries hardcoded first, then dynamically loaded from CSV, then site aliases.
        
        Args:
            norm_set: Normative database name
            site: EEG site
            metric: Metric name
            
        Returns:
            Dictionary of norm values or None
        """
        norm_set_lower = norm_set.lower()
        if norm_set_lower == 'cuban2ndwave':
            self._ensure_cuban2ndwave_loaded()

        if norm_set_lower not in self.norms:
            return None

        norm_data = self.norms[norm_set_lower]
        # Normalize site: EDF names like "EEG Fp1-LE" must map to "fp1" for norm lookup
        try:
            from hexnode.eeg.viz.utils import clean_channel_name

            site_key = clean_channel_name(str(site)).lower()
        except Exception:
            site_key = str(site).lower()
        site_data = norm_data.get(site_key, {})
        if not site_data and site_key in self._SITE_ALIASES:
            site_data = norm_data.get(self._SITE_ALIASES[site_key], {})
        
        # Handle different metric name formats
        metric_key = metric.lower()
        if metric_key not in site_data:
            metric_alt = metric.replace('/', '_').replace(' ', '_')
            if metric_alt in site_data:
                metric_key = metric_alt
            elif site_key in self._SITE_ALIASES:
                # Site from loaded CSV may lack theta/beta, smr; try alias site
                alt_site_data = norm_data.get(self._SITE_ALIASES[site_key], {})
                if metric_key in alt_site_data:
                    return alt_site_data.get(metric_key)
                if metric_alt in alt_site_data:
                    return alt_site_data.get(metric_alt)
                return None
            else:
                return None

        return site_data.get(metric_key)
    
    def get_asymmetry_norm(self, asymmetry_type):
        """Get asymmetry normative values."""
        return self.asymmetry[asymmetry_type]

    def get_reactivity_norm(self, reactivity_type):
        """Get reactivity normative values."""
        return self.reactivity[reactivity_type]

    def _load_advanced_metric_norms(self):
        """Load SEF and alpha peak norms from Cuban CSV data (aggregate stats)."""
        import csv
        from pathlib import Path

        from hexnode.eeg.norms_paths import get_cuban_databases_dir

        base = get_cuban_databases_dir()
        if base is None:
            return

        # --- SEF norms from Cuban 2nd wave (eyes-closed) ---
        sef_path = (
            base / 'cuban_2nd_wave_database' / 'condition_specific_analysis'
            / 'eyes_closed' / 'eyes_closed_spectral_edge_frequencies.csv'
        )
        if sef_path.exists():
            try:
                rows = []
                with open(sef_path, newline='', encoding='utf-8') as fh:
                    for row in csv.DictReader(fh):
                        rows.append(row)
                if rows:
                    def _col_stats(col):
                        vals = []
                        for r in rows:
                            try:
                                vals.append(float(r[col]))
                            except (KeyError, TypeError, ValueError):
                                pass
                        if len(vals) < 5:
                            return None
                        arr = np.array(vals)
                        return {'mean': float(np.mean(arr)), 'sd': float(np.std(arr, ddof=1))}

                    sef90 = _col_stats('spectral_edge_90')
                    sef95 = _col_stats('spectral_edge_95')
                    pf = _col_stats('peak_frequency')

                    global_norms = self.norms.setdefault('cuban2ndwave_advanced', {}).setdefault('_global', {})
                    if sef90:
                        global_norms['sef_90'] = sef90
                    if sef95:
                        global_norms['sef_95'] = sef95
                    if pf:
                        global_norms['peak_frequency'] = pf
                    logger.debug("Loaded advanced norms from Cuban 2nd wave SEF CSV")
            except Exception as exc:
                logger.debug("Could not load SEF norms: %s", exc)

        # --- Alpha peak norms from Cuban 1st wave ---
        apk_path = base / 'cuban_database' / 'data' / 'alpha_peak_table.csv'
        if apk_path.exists():
            try:
                vals = []
                with open(apk_path, newline='', encoding='utf-8') as fh:
                    for row in csv.DictReader(fh):
                        try:
                            vals.append(float(row['alpha_peak_hz']))
                        except (KeyError, TypeError, ValueError):
                            pass
                if len(vals) >= 10:
                    arr = np.array(vals)
                    global_norms = self.norms.setdefault('cuban2ndwave_advanced', {}).setdefault('_global', {})
                    global_norms['alpha_peak'] = {
                        'mean': float(np.mean(arr)),
                        'sd': float(np.std(arr, ddof=1)),
                    }
                    logger.debug("Loaded alpha peak norms from Cuban 1st wave CSV (n=%d)", len(vals))
            except Exception as exc:
                logger.debug("Could not load alpha peak norms: %s", exc)

    def get_advanced_norm(self, metric: str) -> Optional[Dict[str, Any]]:
        """Get normative mean/SD for an advanced metric (SEF, alpha peak, etc.).

        These are global (not site-specific) norms derived from Cuban databases.
        Returns dict with 'mean' and 'sd' keys, or None.
        """
        if 'cuban2ndwave_advanced' not in self.norms:
            self._load_advanced_metric_norms()
        adv = self.norms.get('cuban2ndwave_advanced', {})
        global_norms = adv.get('_global', {})
        return global_norms.get(metric.lower())

    def list_available_norms(self) -> List[str]:
        """List all available norm sets"""
        return list(self.norms.keys())
