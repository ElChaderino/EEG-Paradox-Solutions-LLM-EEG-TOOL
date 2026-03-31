"""Attach normative z-scores to flat per-channel metrics (for viz + JSON exports)."""
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
from typing import Any, Iterable

logger = logging.getLogger(__name__)

_BANDS = ("Delta", "Theta", "Alpha", "Beta", "Gamma", "SMR", "HiBeta")
_NORM_ORDER: tuple[str, ...] = ("cuban2ndwave", "cuban", "swingle")


def enrich_metrics_with_normative_z(
    metrics_by_site: dict[str, Any],
    norm_sets: Iterable[str] | None = None,
) -> int:
    """
    For each channel dict, add ``<Band>_z_normative`` when mean/sd exist in NormManager.
    Mutates ``metrics_by_site`` in place. Returns count of z-values written.
    """
    if not metrics_by_site:
        return 0
    order = tuple(norm_sets) if norm_sets is not None else _NORM_ORDER
    try:
        from hexnode.eeg.norms.norm_manager import NormManager

        nm = NormManager()
    except Exception as e:
        logger.debug("NormManager unavailable for enrichment: %s", e)
        return 0

    from hexnode.eeg.viz.utils import clean_channel_name

    written = 0
    for ch, site in metrics_by_site.items():
        if not isinstance(site, dict):
            continue
        ch_for_norm = clean_channel_name(str(ch))
        for band in _BANDS:
            val = site.get(band)
            if val is None or not isinstance(val, (int, float)):
                continue
            z_key = f"{band}_z_normative"
            if z_key in site and site[z_key] is not None:
                continue
            z_val = None
            for ns in order:
                nd = nm.get_norm(ns, ch_for_norm, band)
                if not nd:
                    continue
                mean = nd.get("mean")
                sd = nd.get("sd")
                if mean is None or sd is None or sd <= 0:
                    continue
                try:
                    z_val = (float(val) - float(mean)) / float(sd)
                    break
                except (TypeError, ValueError):
                    continue
            if z_val is not None:
                site[z_key] = round(z_val, 4)
                written += 1
    if written:
        logger.info("Normative z enrichment: wrote %d site-band z-scores", written)
    return written
