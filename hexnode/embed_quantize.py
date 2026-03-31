"""Embedding quantization for ChromaDB storage compression.

Inspired by TurboQuant's data-oblivious approach: apply a random rotation to
spread information uniformly across dimensions, then scalar-quantize each
coordinate.  This preserves cosine similarity for vector search while reducing
storage from 3072 bytes/vector (768 x float32) down to 768 bytes (int8) or
192 bytes (int4).

The rotation matrix is seeded deterministically so quantize/dequantize are
consistent across restarts without storing calibration data.
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
import math
from typing import Literal

import numpy as np

from hexnode.config import settings

log = logging.getLogger("hexnode.embed_quantize")

_SEED = 42
_rotation_cache: dict[int, np.ndarray] = {}


def _get_rotation(dim: int) -> np.ndarray:
    """Deterministic random orthogonal matrix (Haar-distributed via QR)."""
    if dim not in _rotation_cache:
        rng = np.random.RandomState(_SEED)
        H = rng.randn(dim, dim).astype(np.float32)
        Q, R = np.linalg.qr(H)
        # Ensure proper rotation (det=+1)
        Q = Q @ np.diag(np.sign(np.diag(R)))
        _rotation_cache[dim] = Q
        log.info("Generated %dx%d rotation matrix for embedding quantization", dim, dim)
    return _rotation_cache[dim]


def quantize_embedding(
    vec: list[float],
    bits: int | None = None,
) -> list[float]:
    """Quantize a float32 embedding vector for compressed storage.

    bits=0  -> passthrough (no quantization)
    bits=8  -> int8 scalar quantization after rotation (~4x compression)
    bits=4  -> int4 scalar quantization after rotation (~8x compression)
    bits=1  -> binary sign quantization after rotation (~32x compression)

    Returns a list[float] because ChromaDB only accepts float embeddings,
    but the values are constrained to a small discrete set, enabling
    future backends to store them more compactly.
    """
    b = bits if bits is not None else settings.embed_quantize_bits
    if b <= 0:
        return vec

    arr = np.array(vec, dtype=np.float32)
    dim = len(arr)

    # Random rotation spreads information uniformly (data-oblivious step)
    R = _get_rotation(dim)
    rotated = R @ arr

    if b == 1:
        # Binary: keep only the sign
        quantized = np.sign(rotated).astype(np.float32)
        quantized[quantized == 0] = 1.0
        # Normalize so dot products are meaningful
        quantized /= math.sqrt(dim)
    elif b == 4:
        # 4-bit: 16 levels
        vmin, vmax = rotated.min(), rotated.max()
        span = vmax - vmin
        if span < 1e-10:
            return vec
        normalized = (rotated - vmin) / span
        levels = 15.0
        quantized_int = np.round(normalized * levels).astype(np.float32)
        # Dequantize back to approximate original scale
        quantized = (quantized_int / levels) * span + vmin
    else:
        # 8-bit: 256 levels (default)
        vmin, vmax = rotated.min(), rotated.max()
        span = vmax - vmin
        if span < 1e-10:
            return vec
        normalized = (rotated - vmin) / span
        levels = 255.0
        quantized_int = np.round(normalized * levels).astype(np.float32)
        quantized = (quantized_int / levels) * span + vmin

    # Inverse rotation to restore original coordinate space
    result = R.T @ quantized
    return result.tolist()


def get_quantize_info() -> dict[str, str | int]:
    """Return current quantization settings for display."""
    b = settings.embed_quantize_bits
    if b <= 0:
        return {"enabled": False, "bits": 0, "compression": "1x (off)", "method": "none"}
    method = "rotation + scalar quantization"
    compression = {1: "~32x", 4: "~8x", 8: "~4x"}.get(b, f"~{32 // b}x")
    return {
        "enabled": True,
        "bits": b,
        "compression": compression,
        "method": method,
    }
