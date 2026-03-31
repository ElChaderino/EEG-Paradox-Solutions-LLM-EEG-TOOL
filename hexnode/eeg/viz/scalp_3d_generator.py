#!/usr/bin/env python3
"""
3D Scalp Topography (Level 3) Generator.

Produces physiologically constrained 3D scalp surface HTML: cranial cap only,
interpolation limited to electrode support, rim/feather/depth shading, orientation
cues, and camera presets. Uses MNE 10-20 or fallback, SciPy RBF, Plotly. Supports
power, z-score, and EO-EC difference modes.

Design follows MNE-Python and Plotly conventions:
- Orbit drag mode for rotate; scroll to zoom (scene.dragmode='orbit').
- Camera presets: Front, Back, Top, Left, Right (MNE set_3d_view style).
- Electrode markers + labels (sensors=True/names style); short colorbar title to avoid truncation.
- Interpolation: RBF on sphere with convex-hull masking (cf. topomap extrapolation).
- 3D relief: mesh is deformed radially by data values (elevation = band power / z-score) so the
  surface is contoured like a 3D topomap, not just a flat color on the model.

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

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Band name -> metric key (same as utils.extract_band_values)
_BAND_MAP = {
    "delta": "Delta",
    "theta": "Theta",
    "alpha": "Alpha",
    "beta": "Beta",
    "gamma": "Gamma",
    "smr": "SMR",
    "hibeta": "HiBeta",
}

_MIN_CHANNELS_DEFAULT = 4
# Lower smooth = more localized interpolation (less "globe of color"); 0.002 = stronger per-site variation
_RBF_SMOOTH = 0.002
_MESH_RES = 150
# Cranial cap only (upper convexity); physiologically correct
_PHI_MAX = 0.55 * np.pi  # ~99°: top and upper sides only
_HEAD_Z_SCALE = 0.85
_HEAD_XY_SCALE = 1.00
# 3D relief: scale mesh radially by data (1 + relief_scale * norm_val) for topo-map elevation
_RELIEF_SCALE = 0.42


def _get_band_metric_key(band: str) -> str:
    return _BAND_MAP.get(band.lower(), band.capitalize() if band else "Alpha")


def _get_coords_3d(
    channel_names: List[str],
) -> Tuple[Optional[np.ndarray], List[str]]:
    """
    Get 3D coordinates for channel names. Prefer MNE standard_1020; fallback
    to 2D CLINICAL_1020 projected onto sphere. Returns (coords_3d, valid_names);
    coords_3d is (N, 3), valid_names is subset of channel_names with valid positions.
    """
    from hexnode.eeg.viz.utils import clean_channel_name

    # Try MNE first
    try:
        import mne
        montage = mne.channels.make_standard_montage("standard_1020")
        ch_pos = montage.get_positions()["ch_pos"]
    except ImportError:
        logger.warning("MNE not available for 3D scalp; using 2D-to-sphere fallback")
        ch_pos = None
    except Exception as e:
        logger.warning("MNE montage failed: %s; using 2D-to-sphere fallback", e)
        ch_pos = None

    if ch_pos is not None:
        coords_list = []
        valid_names = []
        for ch in channel_names:
            clean = clean_channel_name(ch)
            if clean in ch_pos:
                pos = ch_pos[clean]
                # MNE returns positions in meters (x, y, z)
                coords_list.append([pos[0], pos[1], pos[2]])
                valid_names.append(ch)
        if len(coords_list) >= _MIN_CHANNELS_DEFAULT:
            coords = np.array(coords_list, dtype=float)
            # Normalize to unit sphere for consistent display
            norms = np.linalg.norm(coords, axis=1, keepdims=True)
            norms = np.where(norms > 0, norms, 1.0)
            coords = coords / norms
            return coords, valid_names
        logger.warning(
            "Only %d channels matched MNE montage (need >= %d); trying 2D fallback",
            len(coords_list), _MIN_CHANNELS_DEFAULT,
        )

    # Fallback: 2D CLINICAL_1020 -> sphere
    from hexnode.eeg.viz.theme_manager import CLINICAL_1020_POSITIONS

    coords_list = []
    valid_names = []
    for ch in channel_names:
        clean = clean_channel_name(ch)
        if clean not in CLINICAL_1020_POSITIONS:
            continue
        x, y = CLINICAL_1020_POSITIONS[clean]
        # Project unit-disk (x,y) onto upper hemisphere: z = sqrt(1 - x^2 - y^2)
        r2 = x * x + y * y
        if r2 >= 1.0:
            z = 0.0
        else:
            z = np.sqrt(1.0 - r2)
        coords_list.append([x, y, z])
        valid_names.append(ch)

    if len(coords_list) < _MIN_CHANNELS_DEFAULT:
        return None, []
    coords = np.array(coords_list, dtype=float)
    return coords, valid_names


def _get_values_for_mode(
    metrics_by_site: Dict[str, Any],
    norm_violations: Optional[Dict[str, Dict[str, List[Dict[str, Any]]]]],
    band: str,
    epoch: Optional[str],
    mode: str,
) -> Tuple[List[str], np.ndarray]:
    """
    Return (channel_names, values) for the given band/epoch and mode.
    mode: 'power' | 'zscore' | 'diff'. For 'diff', epoch is ignored; EO and EC are used.
    """
    from hexnode.eeg.viz.utils import extract_band_values

    metric_key = _get_band_metric_key(band)

    if mode == "diff":
        ch_eo, val_eo = extract_band_values(metrics_by_site, band, "EO")
        ch_ec, val_ec = extract_band_values(metrics_by_site, band, "EC")
        if not ch_eo or not ch_ec:
            return [], np.array([])
        # Align by channel (intersection)
        common = list(dict.fromkeys(c for c in ch_eo if c in ch_ec))
        if len(common) < _MIN_CHANNELS_DEFAULT:
            return [], np.array([])
        idx_eo = [ch_eo.index(c) for c in common]
        idx_ec = [ch_ec.index(c) for c in common]
        diff_vals = np.array(val_eo)[idx_eo] - np.array(val_ec)[idx_ec]
        return common, diff_vals.astype(float)

    channel_names, values = extract_band_values(metrics_by_site, band, epoch)
    if len(channel_names) < _MIN_CHANNELS_DEFAULT:
        return [], np.array([])
    values = np.asarray(values, dtype=float)

    if mode == "zscore":
            z_vals = np.zeros_like(values)
            norm_violations = norm_violations or {}
            for i, ch in enumerate(channel_names):
                site_viol = norm_violations.get(ch, {})
                viol_list = site_viol.get(metric_key, [])
                if viol_list and isinstance(viol_list[0], dict):
                    z = viol_list[0].get("z_score")
                    if z is not None:
                        z_vals[i] = float(z)
                        continue
                # Fallback: compute z from NormManager
                try:
                    from hexnode.eeg.norms.norm_manager import NormManager
                    nm = NormManager()
                    val = values[i]
                    for norm_set in ("cuban2ndwave", "cuban", "swingle"):
                        nd = nm.get_norm(norm_set, ch, metric_key)
                        if nd and nd.get("mean") is not None and nd.get("sd") and nd["sd"] > 0:
                            z_vals[i] = (val - nd["mean"]) / nd["sd"]
                            break
                except Exception:
                    pass
            return channel_names, z_vals

    return channel_names, values


def _interpolate_rbf(
    coords: np.ndarray,
    values: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    zs: np.ndarray,
    smooth: float = _RBF_SMOOTH,
) -> Optional[np.ndarray]:
    """Interpolate values onto sphere mesh using RBF. Returns surface_vals or None on failure."""
    try:
        from scipy.interpolate import Rbf
        rbf = Rbf(
            coords[:, 0],
            coords[:, 1],
            coords[:, 2],
            values,
            function="multiquadric",
            smooth=smooth,
        )
        surface_vals = rbf(xs, ys, zs)
        return np.asarray(surface_vals, dtype=float)
    except Exception as e:
        logger.warning("RBF interpolation failed: %s", e)
        return None


def _mask_and_feather_surface(
    coords: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    surface_vals: np.ndarray,
    feather_strength: float = 0.12,
) -> np.ndarray:
    """
    Mask outside electrode convex hull (2D Delaunay on projected XY) and
    softly feather values near boundary. Prevents RBF "globe" extrapolation.
    """
    try:
        from scipy.spatial import Delaunay
        from scipy.ndimage import distance_transform_edt
    except Exception:
        return surface_vals

    pts2 = coords[:, :2]
    if pts2.shape[0] < 3:
        return surface_vals

    tri = Delaunay(pts2)
    grid_pts = np.column_stack([xs.ravel(), ys.ravel()])
    inside = tri.find_simplex(grid_pts) >= 0
    inside = inside.reshape(xs.shape)

    masked = np.array(surface_vals, dtype=float, copy=True)
    masked[~inside] = np.nan

    dist = distance_transform_edt(inside.astype(np.uint8))
    if np.max(dist) > 0:
        fade = np.clip(dist / (feather_strength * np.max(dist)), 0.0, 1.0)
        masked = np.where(np.isfinite(masked), masked * fade, np.nan)

    return masked


def _apply_depth_shading(
    surface_vals: np.ndarray,
    zs: np.ndarray,
    strength: float = 0.18,
) -> np.ndarray:
    """Subtle z-based shading so lower dome appears slightly darker (cranial depth realism)."""
    sv = np.array(surface_vals, dtype=float, copy=True)
    z = np.array(zs, dtype=float)
    zmin = np.nanmin(z)
    zmax = np.nanmax(z)
    if not np.isfinite(zmin) or not np.isfinite(zmax) or zmax <= zmin:
        return sv
    zn = (z - zmin) / (zmax - zmin)
    mult = (1.0 - strength) + (2.0 * strength) * zn
    return np.where(np.isfinite(sv), sv * mult, np.nan)


def _deform_surface_by_values(
    xs: np.ndarray,
    ys: np.ndarray,
    zs: np.ndarray,
    surface_vals: np.ndarray,
    cmin: float,
    cmax: float,
    relief_scale: float = _RELIEF_SCALE,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Deform the scalp mesh radially by data values so high values bulge out (3D topo relief).
    Each vertex is scaled: (x,y,z) *= 1 + relief_scale * normalized_value.
    Normalized value is (surface_vals - cmin) / (cmax - cmin), clipped to [0, 1].
    """
    span = cmax - cmin
    if span <= 0:
        span = 1e-6
    norm = np.clip((np.asarray(surface_vals, dtype=float) - cmin) / span, 0.0, 1.0)
    # NaN-safe: where NaN, use 0 so no displacement
    norm = np.where(np.isfinite(norm), norm, 0.0)
    scale = 1.0 + relief_scale * norm
    return xs * scale, ys * scale, zs * scale


# Paradox dark theme for 3D scalp (so saved HTML is never white)
_SCALP_DARK_BG = "#0a0f17"
_SCALP_DARK_FG = "#d6f6ff"


def _is_light_hex(hex_str: str) -> bool:
    """True if hex color is light (e.g. white/light gray). Ensures 3D scalp HTML never gets white bg."""
    if not hex_str or not isinstance(hex_str, str):
        return False
    s = hex_str.strip().lstrip("#")
    if len(s) == 6:
        try:
            r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            return luminance > 0.6
        except ValueError:
            pass
    return False


def _get_theme_colors() -> Tuple[str, str]:
    """Get background and foreground colors from theme manager (match other viz)."""
    try:
        from hexnode.eeg.viz.theme_manager import get_theme_manager
        theme = get_theme_manager()
        bg = theme.get_background_color()
        fg = theme.get_foreground_color()
        # Force dark for 3D scalp so saved HTML is never white and z-scores are readable
        if _is_light_hex(bg):
            return _SCALP_DARK_BG, _SCALP_DARK_FG
        return bg, fg
    except Exception:
        return _SCALP_DARK_BG, _SCALP_DARK_FG


def _build_plotly_figure(
    xs: np.ndarray,
    ys: np.ndarray,
    zs: np.ndarray,
    surface_vals: np.ndarray,
    coords: np.ndarray,
    channel_names: List[str],
    title: str,
    cmin: float,
    cmax: float,
    colorscale: str,
    is_diverging: bool,
    electrode_values: Optional[np.ndarray] = None,
    bg_color: Optional[str] = None,
    fg_color: Optional[str] = None,
) -> Any:
    """Build Plotly Figure: surface (with 3D relief) + rim + electrodes + nose + ears + camera presets."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        logger.warning("Plotly not available for 3D scalp visualization")
        return None

    if bg_color is None or fg_color is None:
        _bg, _fg = _get_theme_colors()
        bg_color = bg_color or _bg
        fg_color = fg_color or _fg

    if is_diverging:
        # Clinical RdBu: blue (negative) -> white (zero) -> red (positive), matching 2D topomaps
        colorscale = [
            [0.0, '#2166ac'], [0.125, '#4393c3'], [0.25, '#92c5de'],
            [0.375, '#d1e5f0'], [0.5, '#f7f7f7'],
            [0.625, '#fddbc7'], [0.75, '#f4a582'], [0.875, '#d6604d'],
            [1.0, '#b2182b'],
        ]
        if cmax <= cmin:
            cmin, cmax = -3.0, 3.0
    else:
        if colorscale == "RdBu":
            colorscale = "Viridis"
        if cmax <= cmin:
            cmax = cmin + 1e-6

    shaded_vals = _apply_depth_shading(surface_vals, zs, strength=0.16)

    lighting = dict(
        ambient=0.60,
        diffuse=0.55,
        specular=0.15,
        roughness=0.80,
        fresnel=0.08,
    )
    lightpos = dict(x=0.4, y=1.2, z=1.6)

    cbar_title = "Z-Score" if is_diverging else "Band power"
    contour_kw = {}
    if not is_diverging:
        z_min, z_max = np.nanmin(zs), np.nanmax(zs)
        z_range = float(z_max - z_min) if np.any(np.isfinite(zs)) else 1.0
        contour_step = max(z_range / 10, 0.02) if z_range >= 1e-6 else None
        if contour_step is not None and z_range >= 1e-6:
            contour_kw["contours"] = dict(
                z=dict(
                    show=True,
                    usecolormap=False,
                    color=fg_color,
                    start=float(z_min),
                    end=float(z_max),
                    size=contour_step,
                ),
            )
    surface = go.Surface(
        x=xs,
        y=ys,
        z=zs,
        surfacecolor=shaded_vals,
        colorscale=colorscale,
        cmin=cmin,
        cmax=cmax,
        opacity=1.0,
        showscale=True,
        lighting=lighting,
        lightposition=lightpos,
        **contour_kw,
        colorbar=dict(
            title=dict(text=cbar_title, font=dict(color=fg_color)),
            len=0.7,
            thickness=18,
            x=1.02,
            tickfont=dict(color=fg_color),
        ),
        name="Scalp",
        hoverinfo="skip",
    )

    # Scale electrode positions to ellipsoid; if relief is used, push each electrode out by its value
    coords_display = coords * np.array([_HEAD_XY_SCALE, _HEAD_XY_SCALE, _HEAD_Z_SCALE])
    if electrode_values is not None and len(electrode_values) == len(channel_names):
        span = cmax - cmin
        if span <= 0:
            span = 1e-6
        for i in range(len(channel_names)):
            norm_val = np.clip((float(electrode_values[i]) - cmin) / span, 0.0, 1.0)
            scale = 1.0 + _RELIEF_SCALE * norm_val
            coords_display[i] *= scale
    # Electrode markers: white fill with cyan outline so they pop on both dark bg and colored surface
    electrodes = go.Scatter3d(
        x=coords_display[:, 0],
        y=coords_display[:, 1],
        z=coords_display[:, 2],
        mode="markers+text",
        marker=dict(size=5, color="rgba(255,255,255,0.92)", symbol="circle",
                    line=dict(width=1.2, color="rgba(82,232,252,0.8)")),
        text=channel_names,
        textposition="top center",
        textfont=dict(size=11, color=fg_color, family="sans-serif"),
        name="Electrodes",
        hoverinfo="text",
        hovertext=[f"{ch}" for ch in channel_names],
    )

    # Nose indicator: cyan so it's visible on dark background
    nose = go.Scatter3d(
        x=[0.0, 0.0],
        y=[1.02 * _HEAD_XY_SCALE, 1.16 * _HEAD_XY_SCALE],
        z=[0.06 * _HEAD_Z_SCALE, 0.02 * _HEAD_Z_SCALE],
        mode="lines",
        line=dict(width=7, color="rgba(82,232,252,0.65)"),
        showlegend=False,
        hoverinfo="skip",
        name="",
    )

    t = np.linspace(0, 2 * np.pi, 100)
    ear_y = 0.05 + 0.18 * np.cos(t)
    ear_z = 0.20 + 0.22 * np.sin(t)
    ear_x_left = (-0.98 * _HEAD_XY_SCALE) * np.ones_like(t)
    ear_x_right = (0.98 * _HEAD_XY_SCALE) * np.ones_like(t)
    ear_z_scaled = ear_z * _HEAD_Z_SCALE

    ear_left = go.Scatter3d(
        x=ear_x_left,
        y=ear_y * _HEAD_XY_SCALE,
        z=ear_z_scaled,
        mode="lines",
        line=dict(width=5, color="rgba(82,232,252,0.45)"),
        showlegend=False,
        hoverinfo="skip",
        name="",
    )
    ear_right = go.Scatter3d(
        x=ear_x_right,
        y=ear_y * _HEAD_XY_SCALE,
        z=ear_z_scaled,
        mode="lines",
        line=dict(width=5, color="rgba(82,232,252,0.45)"),
        showlegend=False,
        hoverinfo="skip",
        name="",
    )

    rim_x = xs[-1, :]
    rim_y = ys[-1, :]
    rim_z = zs[-1, :]
    rim = go.Scatter3d(
        x=rim_x,
        y=rim_y,
        z=rim_z,
        mode="lines",
        line=dict(width=5, color="rgba(82,232,252,0.35)"),
        showlegend=False,
        hoverinfo="skip",
        name="",
    )

    fig = go.Figure(data=[surface, rim, electrodes, nose, ear_left, ear_right])

    # Camera presets (MNE/Plotly convention: eye = camera position, center = look-at, up = view up)
    cam_front = dict(eye=dict(x=0.0, y=2.2, z=0.4), center=dict(x=0, y=0, z=0), up=dict(x=0, y=0, z=1))
    cam_back = dict(eye=dict(x=0.0, y=-2.2, z=0.4), center=dict(x=0, y=0, z=0), up=dict(x=0, y=0, z=1))
    cam_top = dict(eye=dict(x=0.0, y=0.0, z=2.2), center=dict(x=0, y=0, z=0), up=dict(x=0, y=1, z=0))
    cam_left = dict(eye=dict(x=-2.2, y=0.0, z=0.4), center=dict(x=0, y=0, z=0), up=dict(x=0, y=0, z=1))
    cam_right = dict(eye=dict(x=2.2, y=0.0, z=0.4), center=dict(x=0, y=0, z=0), up=dict(x=0, y=0, z=1))

    fig.update_layout(
        paper_bgcolor=bg_color,
        plot_bgcolor=bg_color,
        title=dict(
            text=title,
            font=dict(size=16, color=fg_color),
            x=0.5,
            xanchor="center",
        ),
        annotations=[
            dict(
                text="Drag to rotate · Scroll to zoom · Buttons for preset views",
                xref="paper",
                yref="paper",
                x=0.5,
                y=1.02,
                xanchor="center",
                yanchor="bottom",
                showarrow=False,
                font=dict(size=11, color=fg_color),
            ),
            *([
                dict(
                    text="Blue: below normative mean · Red: above normative mean",
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.96,
                    xanchor="center",
                    yanchor="top",
                    showarrow=False,
                    font=dict(size=12, color=fg_color),
                )
            ] if is_diverging else []),
        ],
        scene=dict(
            xaxis=dict(visible=False, showbackground=False, backgroundcolor=bg_color),
            yaxis=dict(visible=False, showbackground=False, backgroundcolor=bg_color),
            zaxis=dict(visible=False, showbackground=False, backgroundcolor=bg_color),
            bgcolor=bg_color,
            aspectmode="data",
            camera=cam_front,
            dragmode="orbit",
        ),
        margin=dict(l=0, r=90, t=100, b=40),
        font=dict(color=fg_color),
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                x=0.02,
                y=0.98,
                xanchor="left",
                yanchor="top",
                pad=dict(r=10, t=10),
                showactive=True,
                buttons=[
                    dict(label="Front", method="relayout", args=[{"scene.camera": cam_front}]),
                    dict(label="Back", method="relayout", args=[{"scene.camera": cam_back}]),
                    dict(label="Top", method="relayout", args=[{"scene.camera": cam_top}]),
                    dict(label="Left", method="relayout", args=[{"scene.camera": cam_left}]),
                    dict(label="Right", method="relayout", args=[{"scene.camera": cam_right}]),
                ],
            )
        ],
    )
    return fig


def build_microstate_scalp_surfaces(
    maps_arr: np.ndarray,
    ch_names: List[str],
    n_states: int,
    mesh_res: int = 100,
    rbf_smooth: float = _RBF_SMOOTH,
    feather_strength: float = 0.12,
) -> Optional[List[Dict[str, Any]]]:
    """
    Build LORETA-style 3D scalp surface data for each microstate (RBF interpolation,
    mask/feather, depth shading). For use in microstate interactive HTML "3D model" view.

    Returns list of dicts, one per state: {x, y, z, surfacecolor, cmin, cmax} (all
    arrays as lists for JSON). Returns None if coords or RBF fails.
    """
    from hexnode.eeg.viz.utils import clean_channel_name

    coords, valid_names = _get_coords_3d(ch_names)
    if coords is None or len(valid_names) < _MIN_CHANNELS_DEFAULT:
        return None

    # Align maps to valid_names: maps_arr[state_idx, ch_idx] -> values for valid_names
    ch_to_idx = {c: i for i, c in enumerate(ch_names)}
    valid_idx = []
    for vn in valid_names:
        for k in (vn, clean_channel_name(vn), vn.upper()):
            if k in ch_to_idx:
                valid_idx.append(ch_to_idx[k])
                break
        else:
            valid_idx.append(-1)
    if any(i < 0 for i in valid_idx) or len(valid_idx) != len(valid_names):
        return None

    phi, theta = np.mgrid[
        0 : _PHI_MAX : mesh_res * 1j,
        0 : 2 * np.pi : mesh_res * 1j,
    ]
    xs_unit = np.sin(phi) * np.cos(theta)
    ys_unit = np.sin(phi) * np.sin(theta)
    zs_unit = np.cos(phi)
    xs = _HEAD_XY_SCALE * xs_unit
    ys = _HEAD_XY_SCALE * ys_unit
    zs = _HEAD_Z_SCALE * zs_unit

    out: List[Dict[str, Any]] = []
    all_vals: List[float] = []
    for si in range(min(n_states, maps_arr.shape[0])):
        values = np.array([float(maps_arr[si, valid_idx[i]]) for i in range(len(valid_names))])
        surface_vals = _interpolate_rbf(coords, values, xs_unit, ys_unit, zs_unit, smooth=rbf_smooth)
        if surface_vals is None:
            return None
        surface_vals = _mask_and_feather_surface(coords, xs_unit, ys_unit, surface_vals, feather_strength=feather_strength)
        shaded = _apply_depth_shading(surface_vals, zs, strength=0.16)
        vmin, vmax = np.nanmin(shaded), np.nanmax(shaded)
        if np.isfinite(vmin):
            all_vals.append(vmin)
        if np.isfinite(vmax):
            all_vals.append(vmax)
        # Symmetric cmin/cmax for topography (diverging)
        span = max(abs(vmin), abs(vmax), 1e-6) if np.isfinite(vmin) and np.isfinite(vmax) else 1.0
        cmin, cmax = -span, span
        np.nan_to_num(shaded, copy=False, nan=0.0)
        out.append({
            "x": xs.tolist(),
            "y": ys.tolist(),
            "z": zs.tolist(),
            "surfacecolor": shaded.tolist(),
            "cmin": float(cmin),
            "cmax": float(cmax),
        })
    if not out:
        return None
    # Optional: normalize cmin/cmax across states for comparable colors
    if all_vals:
        gmin, gmax = min(all_vals), max(all_vals)
        span = max(abs(gmin), abs(gmax), 1e-6)
        for d in out:
            d["cmin"], d["cmax"] = -span, span
    return out


def _build_one_scalp_figure(
    metrics_by_site: Dict[str, Any],
    norm_violations: Optional[Dict[str, Dict[str, List[Dict[str, Any]]]]],
    subject_id: str,
    session_id: str,
    band: str,
    epoch: Optional[str],
    mode: str,
    config: Any,
) -> Optional[Any]:
    """Build one 3D scalp Plotly figure (no file write). Returns go.Figure or None."""
    if not metrics_by_site:
        return None
    opts = config.get("3d_scalp_topo", {}) or {} if hasattr(config, "get") else {}
    min_channels = int(opts.get("min_channels", _MIN_CHANNELS_DEFAULT))

    channel_names, values = _get_values_for_mode(
        metrics_by_site, norm_violations, band, epoch, mode
    )
    if len(channel_names) < min_channels:
        return None
    coords, valid_names = _get_coords_3d(channel_names)
    if coords is None or len(valid_names) < min_channels:
        return None
    name_to_idx = {c: i for i, c in enumerate(channel_names)}
    values_aligned = np.array([
        values[name_to_idx[c]] for c in valid_names if c in name_to_idx
    ])
    if len(values_aligned) != len(valid_names):
        return None
    channel_names = valid_names
    values = values_aligned

    mesh_res = int(opts.get("mesh_resolution", _MESH_RES))
    rbf_smooth = float(opts.get("rbf_smooth", _RBF_SMOOTH))
    feather_strength = float(opts.get("feather_strength", 0.12))

    phi, theta = np.mgrid[
        0 : _PHI_MAX : mesh_res * 1j,
        0 : 2 * np.pi : mesh_res * 1j,
    ]
    xs_unit = np.sin(phi) * np.cos(theta)
    ys_unit = np.sin(phi) * np.sin(theta)
    zs_unit = np.cos(phi)
    surface_vals = _interpolate_rbf(coords, values, xs_unit, ys_unit, zs_unit, smooth=rbf_smooth)
    if surface_vals is None:
        return None
    surface_vals = _mask_and_feather_surface(coords, xs_unit, ys_unit, surface_vals, feather_strength=feather_strength)

    xs = _HEAD_XY_SCALE * xs_unit
    ys = _HEAD_XY_SCALE * ys_unit
    zs = _HEAD_Z_SCALE * zs_unit

    is_diverging = mode in ("zscore", "diff")

    if is_diverging:
        # Z-scores: symmetric around zero so white = normative mean
        dmin, dmax = np.nanmin(surface_vals), np.nanmax(surface_vals)
        if np.isfinite(dmin) and np.isfinite(dmax):
            half_span = max(abs(dmin), abs(dmax), 1.0)
        else:
            half_span = 3.0
        cmin, cmax = -half_span, half_span
        relief_cmin, relief_cmax = cmin, cmax
    else:
        vmin, vmax = np.nanmin(values), np.nanmax(values)
        if vmax <= vmin:
            vmax = vmin + 1e-6
        cmin, cmax = float(vmin), float(vmax)
        relief_cmin, relief_cmax = cmin, cmax

    title = f"3D Scalp – {_get_band_metric_key(band)}"
    if mode == "diff":
        title += " (EO − EC)"
    elif epoch:
        title += f" – {epoch}"
    title += f" – {subject_id}"

    relief_scale = float(opts.get("relief_scale", 0.15 if is_diverging else _RELIEF_SCALE))
    xs, ys, zs = _deform_surface_by_values(xs, ys, zs, surface_vals, relief_cmin, relief_cmax, relief_scale=relief_scale)
    bg_color, fg_color = _get_theme_colors()

    return _build_plotly_figure(
        xs, ys, zs, surface_vals, coords, channel_names,
        title=title, cmin=cmin, cmax=cmax, colorscale="RdBu", is_diverging=is_diverging,
        electrode_values=values_aligned,
        bg_color=bg_color,
        fg_color=fg_color,
    )


def generate_3d_scalp_html(
    metrics_by_site: Dict[str, Any],
    norm_violations: Optional[Dict[str, Dict[str, List[Dict[str, Any]]]]],
    output_dir: Path,
    subject_id: str,
    session_id: str,
    band: str,
    epoch: Optional[str],
    mode: str = "power",
    config: Optional[Any] = None,
) -> Optional[Path]:
    """
    Generate one 3D scalp topography HTML file.

    Args:
        metrics_by_site: Per-site metrics (nested by epoch or flat).
        norm_violations: Optional; used for z-score mode.
        output_dir: Directory to write HTML (e.g. report visualizations dir).
        subject_id: Subject identifier (for filename/title).
        session_id: Session identifier (for filename/title).
        band: Band name (e.g. 'alpha', 'Alpha').
        epoch: Epoch name ('EO', 'EC') or None for power average; ignored for mode='diff'.
        mode: 'power' | 'zscore' | 'diff'.
        config: Optional visualization config (for zscore_vmin_vmax, etc.).

    Returns:
        Path to written HTML file, or None if generation failed or was skipped.
    """
    if not metrics_by_site:
        return None
    cfg = config or {}
    if hasattr(cfg, "get"):
        opts = cfg.get("3d_scalp_topo", {}) or {}
    else:
        opts = {}
    min_channels = int(opts.get("min_channels", _MIN_CHANNELS_DEFAULT))

    channel_names, values = _get_values_for_mode(
        metrics_by_site, norm_violations, band, epoch, mode
    )
    if len(channel_names) < min_channels:
        logger.debug(
            "3D scalp: skipping %s %s %s (only %d channels)",
            band, epoch or "all", mode, len(channel_names),
        )
        return None

    coords, valid_names = _get_coords_3d(channel_names)
    if coords is None or len(valid_names) < min_channels:
        logger.warning(
            "3D scalp: insufficient channels with positions (%d valid)",
            len(valid_names),
        )
        return None

    name_to_idx = {c: i for i, c in enumerate(channel_names)}
    values_aligned = np.array([
        values[name_to_idx[c]] for c in valid_names if c in name_to_idx
    ])
    if len(values_aligned) != len(valid_names):
        return None
    channel_names = valid_names
    values = values_aligned

    mesh_res = int(opts.get("mesh_resolution", _MESH_RES))
    rbf_smooth = float(opts.get("rbf_smooth", _RBF_SMOOTH))
    feather_strength = float(opts.get("feather_strength", 0.12))

    phi, theta = np.mgrid[
        0 : _PHI_MAX : mesh_res * 1j,
        0 : 2 * np.pi : mesh_res * 1j,
    ]
    xs_unit = np.sin(phi) * np.cos(theta)
    ys_unit = np.sin(phi) * np.sin(theta)
    zs_unit = np.cos(phi)
    surface_vals = _interpolate_rbf(coords, values, xs_unit, ys_unit, zs_unit, smooth=rbf_smooth)
    if surface_vals is None:
        return None
    surface_vals = _mask_and_feather_surface(coords, xs_unit, ys_unit, surface_vals, feather_strength=feather_strength)

    xs = _HEAD_XY_SCALE * xs_unit
    ys = _HEAD_XY_SCALE * ys_unit
    zs = _HEAD_Z_SCALE * zs_unit

    is_diverging = mode in ("zscore", "diff")

    if is_diverging:
        # Z-scores: symmetric around zero so white = normative mean
        dmin, dmax = np.nanmin(surface_vals), np.nanmax(surface_vals)
        if np.isfinite(dmin) and np.isfinite(dmax):
            half_span = max(abs(dmin), abs(dmax), 1.0)
        else:
            half_span = 3.0
        cmin, cmax = -half_span, half_span
        relief_cmin, relief_cmax = cmin, cmax
    else:
        vmin, vmax = np.nanmin(values), np.nanmax(values)
        if vmax <= vmin:
            vmax = vmin + 1e-6
        cmin, cmax = float(vmin), float(vmax)
        relief_cmin, relief_cmax = cmin, cmax

    title = f"3D Scalp – {_get_band_metric_key(band)}"
    if mode == "diff":
        title += " (EO − EC)"
    elif epoch:
        title += f" – {epoch}"
    title += f" – {subject_id}"

    relief_scale = float(opts.get("relief_scale", 0.15 if is_diverging else _RELIEF_SCALE))
    xs, ys, zs = _deform_surface_by_values(xs, ys, zs, surface_vals, relief_cmin, relief_cmax, relief_scale=relief_scale)
    bg_color, fg_color = _get_theme_colors()

    fig = _build_plotly_figure(
        xs, ys, zs, surface_vals, coords, channel_names,
        title=title, cmin=cmin, cmax=cmax, colorscale="RdBu", is_diverging=is_diverging,
        electrode_values=values_aligned,
        bg_color=bg_color,
        fg_color=fg_color,
    )
    if fig is None:
        return None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_band = band.lower().replace(" ", "_")
    safe_epoch = (epoch or "all").lower()
    safe_mode = mode.lower()
    filename = f"3d_scalp_{safe_band}_{safe_epoch}_{safe_mode}.html"
    out_path = output_dir / filename

    try:
        fig.write_html(str(out_path), include_plotlyjs=True)
        logger.info("3D scalp saved: %s", out_path)
        return out_path
    except Exception as e:
        logger.warning("Could not write 3D scalp HTML: %s", e)
        return None


def generate_3d_scalp_combined_html(
    metrics_by_site: Dict[str, Any],
    norm_violations: Optional[Dict[str, Dict[str, List[Dict[str, Any]]]]],
    output_dir: Path,
    subject_id: str,
    session_id: str,
    config: Optional[Any] = None,
) -> Optional[Path]:
    """
    Generate a single HTML file with all 3D scalp views (bands × epochs × modes) and a dropdown selector.
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        logger.warning("Plotly not available for 3D scalp combined HTML")
        return None

    if not metrics_by_site:
        return None
    cfg = config or {}
    opts = cfg.get("3d_scalp_topo", {}) or {} if hasattr(cfg, "get") else {}
    bands = opts.get("bands")
    if bands is None and hasattr(cfg, "get"):
        bands = (cfg.get("topomaps") or {}).get("bands")
    if bands is None:
        bands = ["delta", "theta", "alpha", "beta", "gamma", "smr", "hibeta"]

    from hexnode.eeg.viz.utils import get_all_available_epochs
    epochs = get_all_available_epochs(metrics_by_site)
    if not epochs:
        epochs = [None]
    generate_diff = opts.get("generate_diff", True)

    options = []  # list of (label, data_list, layout_patch with title + annotations)
    first_fig = None
    for band in bands:
        for epoch in epochs:
            for mode in ("power", "zscore"):
                fig = _build_one_scalp_figure(
                    metrics_by_site, norm_violations, subject_id, session_id,
                    band=band, epoch=epoch, mode=mode, config=cfg,
                )
                if fig is not None:
                    label = f"{_get_band_metric_key(band)}"
                    if epoch:
                        label += f" {epoch}"
                    else:
                        label += " all"
                    label += f" {mode}"
                    data_list = [t.to_dict() for t in fig.data]
                    title_obj = fig.layout.title
                    title_dict = title_obj.to_plotly_json() if hasattr(title_obj, "to_plotly_json") else {"text": getattr(title_obj, "text", str(title_obj))}
                    ann_list = [a.to_plotly_json() if hasattr(a, "to_plotly_json") else a for a in (fig.layout.annotations or [])]
                    if first_fig is None:
                        first_fig = fig
                    options.append((label, data_list, {"title": title_dict, "annotations": ann_list}))

        if generate_diff and len(epochs) >= 2 and "EO" in epochs and "EC" in epochs:
            fig = _build_one_scalp_figure(
                metrics_by_site, norm_violations, subject_id, session_id,
                band=band, epoch=None, mode="diff", config=cfg,
            )
            if fig is not None:
                label = f"{_get_band_metric_key(band)} EO−EC diff"
                data_list = [t.to_dict() for t in fig.data]
                title_obj = fig.layout.title
                title_dict = title_obj.to_plotly_json() if hasattr(title_obj, "to_plotly_json") else {"text": getattr(title_obj, "text", str(title_obj))}
                ann_list = [a.to_plotly_json() if hasattr(a, "to_plotly_json") else a for a in (fig.layout.annotations or [])]
                if first_fig is None:
                    first_fig = fig
                options.append((label, data_list, {"title": title_dict, "annotations": ann_list}))

    if not options or first_fig is None:
        logger.warning("3D scalp combined: no views generated")
        return None

    dropdown_buttons = [
        dict(
            label=label,
            method="update",
            args=[{"data": data_list, "layout": {"title": layout_patch["title"], "annotations": layout_patch["annotations"]}}],
        )
        for label, data_list, layout_patch in options
    ]
    base_fig = go.Figure(data=first_fig.data, layout=first_fig.layout)
    view_buttons = list(first_fig.layout.updatemenus) if first_fig.layout.updatemenus else []
    base_fig.update_layout(
        updatemenus=[
            dict(
                type="dropdown",
                direction="down",
                x=0.02,
                y=0.98,
                xanchor="left",
                yanchor="top",
                bgcolor=_SCALP_DARK_BG,
                bordercolor=_SCALP_DARK_FG,
                font=dict(color=_SCALP_DARK_FG, size=12),
                buttons=dropdown_buttons,
            ),
            *view_buttons,
        ],
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "3d_scalp_combined.html"
    try:
        base_fig.write_html(str(out_path), include_plotlyjs=True)
        logger.info("3D scalp combined saved: %s (%d views)", out_path, len(options))
        return out_path
    except Exception as e:
        logger.warning("Could not write 3D scalp combined HTML: %s", e)
        return None
