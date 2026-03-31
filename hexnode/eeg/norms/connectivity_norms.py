"""
Normative connectivity z-scores from a user-supplied CSV.

Pairwise coherence / wPLI / etc. vary by method, frequency band, montage, and
population. This module loads per-pair mean/sd tables you build from a control
cohort (or literature, if available) and applies them to a dense connectivity matrix.

CSV columns (header row required):
  method — e.g. coh, plv, wpli (matched case-insensitively to the pipeline method)
  fmin, fmax — must match the pipeline connectivity band (floats)
  ch_a, ch_b — canonical 10-20 names (e.g. Fp1, Cz); order-independent
  mean, sd — normative distribution for that pair (sd > 0)

These CSVs ship under ``hexnode/eeg/norms/data/`` and are used automatically by
the EEG pipeline when ``connectivity_norm_csv`` is empty and
``connectivity_bundled_norms`` is True (no DLC install needed):

- ``connectivity_norm_cuban2ndwave_eyes_closed.csv`` — EC / default condition
- ``connectivity_norm_cuban2ndwave_eyes_open.csv`` — EO / eyes_open

(Regenerate from DLC with ``python scripts/build_dlc_connectivity_norms.py``.)

``connectivity_norm_example.csv`` is a minimal hand-edited template only.
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

import csv
import logging
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

logger = logging.getLogger(__name__)

NormKey = Tuple[str, float, float, str]  # method, fmin, fmax, "ChA--ChB"


def load_connectivity_norm_csv(path: str | Path) -> Dict[NormKey, Tuple[float, float]]:
    """Load mean/sd per pair from CSV. Returns empty dict if file missing or invalid."""
    p = Path(path)
    if not p.is_file():
        logger.debug("Connectivity norm CSV not found: %s", p)
        return {}
    norms: Dict[NormKey, Tuple[float, float]] = {}
    try:
        with p.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row:
                    continue
                m = str(row.get("method", "")).strip().lower()
                ca = str(row.get("ch_a", "")).strip()
                cb = str(row.get("ch_b", "")).strip()
                if not m or not ca or not cb:
                    continue
                f0 = float(row["fmin"])
                f1 = float(row["fmax"])
                mean = float(row["mean"])
                sd = float(row["sd"])
                if sd <= 0:
                    continue
                a, b = sorted([ca, cb], key=lambda x: x.upper())
                pk = f"{a}--{b}"
                norms[(m, f0, f1, pk)] = (mean, sd)
    except Exception as e:
        logger.warning("Failed to load connectivity norm CSV %s: %s", p, e)
        return {}
    logger.info("Loaded %d connectivity norm pairs from %s", len(norms), p.name)
    return norms


def connectivity_z_matrix(
    con_data: np.ndarray,
    ch_names: list[str],
    method: str,
    fmin: float,
    fmax: float,
    norms: Dict[NormKey, Tuple[float, float]],
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Build symmetric z-matrix (NaN where no norm). Upper triangle counts in meta.
    """
    n = int(con_data.shape[0])
    zmat = np.full((n, n), np.nan, dtype=float)
    meth = method.strip().lower()
    f0p, f1p = float(fmin), float(fmax)
    got = 0
    tot = 0
    for i in range(n):
        for j in range(i + 1, n):
            tot += 1
            a, b = sorted([ch_names[i], ch_names[j]], key=lambda x: str(x).upper())
            pk = (meth, f0p, f1p, f"{a}--{b}")
            st = norms.get(pk)
            if st is None:
                continue
            mean, sd = st
            if sd <= 0:
                continue
            z = (float(con_data[i, j]) - mean) / sd
            zmat[i, j] = zmat[j, i] = z
            got += 1
    meta = {
        "n_matched": got,
        "n_upper_pairs": tot,
        "coverage": float(got) / float(tot) if tot else 0.0,
    }
    return zmat, meta


def connectivity_z_json_ready(zmat: np.ndarray) -> list[list[float | None]]:
    """2D list with None for NaN (JSON-safe)."""
    n = zmat.shape[0]
    out: list[list[float | None]] = []
    for i in range(n):
        row: list[float | None] = []
        for j in range(n):
            v = zmat[i, j]
            row.append(None if (v != v or np.isnan(v)) else round(float(v), 4))
        out.append(row)
    return out
