#!/usr/bin/env python3
"""
Apply the same 10-20 channel standardization as the main EEG Paradox decoder:
format hint → channel_mapper → clean_channel_name; drop aux (ECG/EKG/EMG/EOG/…);
rename T3→T7, etc.; dedupe by canonical name.
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

import logging
from typing import Any, Dict, List, TYPE_CHECKING

from hexnode.eeg.viz.channel_utils import clean_channel_name, get_standard_1020_channels

if TYPE_CHECKING:
    import mne

logger = logging.getLogger(__name__)


def standardize_raw_to_1020(raw: "mne.io.BaseRaw") -> Dict[str, Any]:
    """
    Mutate ``raw`` in place: keep only standard 10-20 EEG channels, canonical names.

    Returns metadata: original_channels, channel_mapping, format_type.
    """
    from hexnode.eeg.viz.channel_mapper import ChannelMapper
    from hexnode.eeg.viz.edf_format_detector import EDFFormatDetector

    original_channels: List[str] = list(raw.ch_names)
    detector = EDFFormatDetector()
    mapper = ChannelMapper()
    format_type = detector.detect(original_channels)
    channel_mapping = mapper.map_channels(original_channels, format_type)
    standard_1020 = get_standard_1020_channels()

    standardized_channels: List[tuple] = []
    channels_to_remove: List[str] = []
    used_standard_names = set()

    for orig_name in original_channels:
        if orig_name in channel_mapping:
            std_name = channel_mapping[orig_name]
        else:
            std_name = clean_channel_name(orig_name)

        if std_name in standard_1020:
            if std_name not in used_standard_names:
                standardized_channels.append((orig_name, std_name))
                used_standard_names.add(std_name)
            else:
                channels_to_remove.append(orig_name)
        else:
            channels_to_remove.append(orig_name)

    if channels_to_remove:
        to_drop = [ch for ch in channels_to_remove if ch in raw.ch_names]
        if to_drop:
            raw.drop_channels(to_drop)

    rename_mapping = {orig: std for orig, std in standardized_channels if orig in raw.ch_names}
    if rename_mapping:
        raw.rename_channels(rename_mapping)

    return {
        "original_channels": original_channels,
        "channel_mapping": channel_mapping,
        "format_type": format_type,
    }
