#!/usr/bin/env python3
"""
EDF Format Detector
Detect EDF format types based on channel names

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
from typing import List

logger = logging.getLogger(__name__)


class EDFFormatDetector:
    """
    Detects EDF format types based on channel naming conventions.
    Supports Cygnet, BioExplorer, Generic, AV Reference formats.
    """
    
    def detect(self, channel_names: List[str]) -> str:
        """
        Detect EDF format type from channel names
        
        Args:
            channel_names: List of channel names
            
        Returns:
            Format type string (cygnet, bioexplorer, generic, av_reference, unknown)
        """
        ch_names_lower = [ch.lower() for ch in channel_names]
        
        av_indicators = ['-av', 'fp1-av', 'fp2-av', 'f3-av', 'f4-av', 'c3-av', 'c4-av', 'cz-av']
        av_matches = sum(1 for ch in ch_names_lower if any(ind in ch for ind in av_indicators))
        if av_matches >= 5:
            return 'av_reference'
        
        cygnet_indicators = ['-le', 'eeg channel', 'peripheral', 'rt_data']
        cygnet_matches = sum(1 for ch in ch_names_lower if any(ind in ch for ind in cygnet_indicators))
        if cygnet_matches >= 3:
            return 'cygnet'
        
        bioexplorer_indicators = ['fp1', 'fp2', 'f3', 'f4', 'c3', 'c4', 'cz']
        bioexplorer_matches = sum(1 for ch in ch_names_lower if ch in bioexplorer_indicators)
        if bioexplorer_matches >= 5:
            return 'bioexplorer'
        
        eeg_channels = [ch for ch in ch_names_lower if 'eeg' in ch or 'ch' in ch]
        if len(eeg_channels) >= 5:
            return 'generic'
        
        return 'unknown'
