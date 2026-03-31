#!/usr/bin/env python3
"""
Channel Mapper
Channel mapping system for different EDF formats

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
from typing import Dict, List

logger = logging.getLogger(__name__)


class ChannelMapper:
    """Maps channels from different formats to standard 10-20 names"""
    
    def __init__(self):
        """Initialize channel mapper"""
        self.format_mappings = {
            'cygnet': {
                'Fp1-LE': 'Fp1', 'Fp2-LE': 'Fp2',
                'F3-LE': 'F3', 'F4-LE': 'F4',
                'C3-LE': 'C3', 'C4-LE': 'C4',
                'Cz-LE': 'Cz',
            },
            'bioexplorer': {},
            'generic': {
                'EEG Fp1': 'Fp1', 'EEG Fp2': 'Fp2',
            }
        }
    
    def map_channels(self, channel_names: List[str], format_type: str) -> Dict[str, str]:
        """
        Map channels to standard names
        
        Args:
            channel_names: List of channel names
            format_type: EDF format type
            
        Returns:
            Dictionary mapping original names to standard names
        """
        mapping = self.format_mappings.get(format_type, {})
        
        result = {}
        for ch_name in channel_names:
            if ch_name in mapping:
                result[ch_name] = mapping[ch_name]
            else:
                from hexnode.eeg.viz.channel_utils import clean_channel_name
                result[ch_name] = clean_channel_name(ch_name)
        
        return result
