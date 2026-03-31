#!/usr/bin/env python3
"""
Channel Utilities
Channel name cleaning and standardization

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


from __future__ import annotations

import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def clean_channel_name(name: str) -> str:
    """
    Clean channel names to standard 10-20 format.
    
    Removes common EDF suffixes and standardizes naming.
    
    Args:
        name: Raw channel name from EDF or other source
        
    Returns:
        Cleaned channel name in standard 10-20 format
        
    Examples:
        'Fp1-LE' -> 'Fp1'
        'fp1-le' -> 'Fp1'
        'FP1-REF' -> 'Fp1'
        'T3' -> 'T7' (old to new nomenclature)
    """
    name = str(name).strip()
    
    # Remove common EDF prefixes (EEG , EEG-, Eeg , etc.) so we get bare 10-20 names
    name = re.sub(r'^EEG[\s\-]+', '', name, flags=re.IGNORECASE)
    name = name.strip()
    
    # Remove suffixes first (case-insensitive by using regex)
    # Order matters! Longer patterns must come first to avoid partial matches
    suffixes = ['-REF', '-LE', '-RE', '-M1', '-M2', '-A1', '-A2', '-Av', '-AV']
    
    for suffix in suffixes:
        # Remove suffix regardless of case
        name = re.sub(re.escape(suffix), '', name, flags=re.IGNORECASE)
    
    # Strip any remaining whitespace
    name = name.strip()
    
    # Standardize case: First letter uppercase, rest lowercase
    # Special handling for common patterns
    name_upper = name.upper()
    
    # Handle special cases first
    if name_upper == 'FPZ':
        return 'Fpz'
    elif name_upper.startswith('FP'):
        # Fp1, Fp2
        return 'Fp' + name_upper[2:]
    elif len(name_upper) == 2 and name_upper[1] == 'Z':
        # Fz, Cz, Pz, Oz
        return name_upper[0] + 'z'
    elif len(name_upper) >= 2:
        # F3, F4, C3, C4, P3, P4, O1, O2, T3, T4, T5, T6, etc.
        result = name_upper[0] + name_upper[1:].lower()
        
        # Convert old to new nomenclature
        old_to_new = {'T3': 'T7', 'T4': 'T8', 'T5': 'P7', 'T6': 'P8'}
        return old_to_new.get(result, result)
    
    return name


def standardize_channel_names(channel_names: List[str]) -> Dict[str, str]:
    """
    Create a mapping from raw channel names to standardized names.
    
    Args:
        channel_names: List of raw channel names
        
    Returns:
        Dictionary mapping raw names to standardized names
        
    Example:
        ['Fp1-LE', 'fp2-le', 'F3-REF'] -> {'Fp1-LE': 'Fp1', 'fp2-le': 'Fp2', 'F3-REF': 'F3'}
    """
    return {ch: clean_channel_name(ch) for ch in channel_names}


def get_standard_1020_channels() -> List[str]:
    """
    Get the standard 19-channel 10-20 EEG montage.
    Uses modern nomenclature (T7/T8, P7/P8) to match clean_channel_name() output.
    
    Returns:
        List of standard channel names
    """
    return [
        'Fp1', 'Fp2',
        'F7', 'F3', 'Fz', 'F4', 'F8',
        'T7', 'C3', 'Cz', 'C4', 'T8',  # T3->T7, T4->T8 (modern nomenclature)
        'P7', 'P3', 'Pz', 'P4', 'P8',  # T5->P7, T6->P8 (modern nomenclature)
        'O1', 'O2', 'Oz'
    ]
