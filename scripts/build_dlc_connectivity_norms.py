#!/usr/bin/env python3
"""
Build pairwise coherence norm tables (mean, sd) from EEG norms DLC Cuban 2nd wave
coherence exports, for use with hexnode pipeline ``connectivity_norm_csv``.

Source: addons/eeg-norms-dlc/payload/data/cuban_databases/.../*_coherence.csv
Channel indices 0–9 map to Fp1, Fp2, F3, F4, C3, C4, P3, P4, O1, O2 (verified
consistent across subjects in channels_bids.csv). Pairs outside this set are not
in the DLC coherence files.

Outputs under hexnode/eeg/norms/data/:
  connectivity_norm_cuban2ndwave_eyes_closed.csv
  connectivity_norm_cuban2ndwave_eyes_open.csv
  (optional: --all-conditions)

Each row: method,fmin,fmax,ch_a,ch_b,mean,sd  with method=coh

Includes native bands (delta … high_gamma) plus a composite row set fmin=4,fmax=30
(mean coherence across theta, alpha, beta per subject, then mean/sd across subjects)
to align with default pipeline connectivity band.
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

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_DLC = _REPO / "addons" / "eeg-norms-dlc" / "payload" / "data" / "cuban_databases" / "cuban_2nd_wave_database"
_OUT = _REPO / "hexnode" / "eeg" / "norms" / "data"

# Indices 0–9 only appear in DLC coherence CSVs; mapping from channels_bids (CBM00001).
IDX_TO_CH: dict[int, str] = {
    0: "Fp1",
    1: "Fp2",
    2: "F3",
    3: "F4",
    4: "C3",
    5: "C4",
    6: "P3",
    7: "P4",
    8: "O1",
    9: "O2",
}

BROAD_BANDS = ("theta", "alpha", "beta")


def _pair_key(i1: int, i2: int) -> tuple[str, str]:
    a = IDX_TO_CH[int(i1)]
    b = IDX_TO_CH[int(i2)]
    return tuple(sorted((a, b), key=lambda x: x.upper()))


def _stats(values: list[float]) -> tuple[float, float]:
    import math

    vals = [float(v) for v in values if v == v and math.isfinite(float(v))]
    n = len(vals)
    if n == 0:
        return float("nan"), float("nan")
    mean = sum(vals) / n
    if n < 2:
        return mean, 0.15
    m = mean
    var = sum((x - m) ** 2 for x in vals) / (n - 1)
    sd = var**0.5
    if sd <= 0:
        sd = 0.15
    return mean, sd


def aggregate_native(df) -> dict[tuple[float, float, str, str], list[float]]:
    """Group key (fmin, fmax, ch_a, ch_b) with sorted channel names -> coherence list."""
    buckets: dict[tuple[float, float, str, str], list[float]] = defaultdict(list)
    for _, row in df.iterrows():
        f0 = float(row["low_frequency"])
        f1 = float(row["high_frequency"])
        ca, cb = _pair_key(int(row["channel_1"]), int(row["channel_2"]))
        buckets[(f0, f1, ca, cb)].append(float(row["coherence"]))
    return buckets


def aggregate_broad_430(df) -> dict[tuple[str, str], list[float]]:
    """Per subject per pair: mean(theta, alpha, beta coherence); then lists per pair across subjects."""
    sub = df[df["frequency_band"].isin(BROAD_BANDS)].copy()
    if sub.empty:
        return {}
    g = sub.groupby(["pscid", "channel_1", "channel_2"], as_index=False)["coherence"].mean()
    pair_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for _, row in g.iterrows():
        ca, cb = _pair_key(int(row["channel_1"]), int(row["channel_2"]))
        pair_values[(ca, cb)].append(float(row["coherence"]))
    return pair_values


def write_norm_csv(
    out_path: Path,
    native: dict[tuple[float, float, str, str], list[float]],
    broad: dict[tuple[str, str], list[float]],
) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nrows = 0
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["method", "fmin", "fmax", "ch_a", "ch_b", "mean", "sd"])
        for (f0, f1, ca, cb) in sorted(native.keys(), key=lambda k: (k[0], k[1], k[2], k[3])):
            mean, sd = _stats(native[(f0, f1, ca, cb)])
            if mean != mean:
                continue
            w.writerow(["coh", f0, f1, ca, cb, f"{mean:.8f}", f"{sd:.8f}"])
            nrows += 1
        for (ca, cb) in sorted(broad.keys(), key=lambda k: (k[0].upper(), k[1].upper())):
            mean, sd = _stats(broad[(ca, cb)])
            if mean != mean:
                continue
            w.writerow(["coh", 4.0, 30.0, ca, cb, f"{mean:.8f}", f"{sd:.8f}"])
            nrows += 1
    return nrows


def process_condition(condition: str, dlc_root: Path) -> Path | None:
    import pandas as pd

    csv_path = (
        dlc_root
        / "condition_specific_analysis"
        / condition
        / f"{condition}_coherence.csv"
    )
    if not csv_path.is_file():
        print(f"SKIP missing: {csv_path}", file=sys.stderr)
        return None
    df = pd.read_csv(csv_path)
    tag = condition.lower().replace(" ", "_")
    out = _OUT / f"connectivity_norm_cuban2ndwave_{tag}.csv"
    native = aggregate_native(df)
    broad = aggregate_broad_430(df)
    n = write_norm_csv(out, native, broad)
    print(f"Wrote {n} rows -> {out}")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Build connectivity norm CSV from EEG norms DLC.")
    p.add_argument(
        "--dlc-root",
        type=Path,
        default=_DLC,
        help="Cuban 2nd wave database root (contains condition_specific_analysis/).",
    )
    p.add_argument(
        "--conditions",
        nargs="*",
        default=["eyes_closed", "eyes_open"],
        help="Condition folder names under condition_specific_analysis/",
    )
    args = p.parse_args()
    root: Path = args.dlc_root
    if not root.is_dir():
        print(f"ERROR: DLC root not found: {root}", file=sys.stderr)
        return 1
    for c in args.conditions:
        process_condition(c, root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
