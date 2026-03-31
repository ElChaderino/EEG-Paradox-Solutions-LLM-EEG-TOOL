#!/usr/bin/env python3
"""
Microstate visualizer: static topomaps, directionality summary, and interactive
clinical-panel explorer.

Generates:
  (1) 2x2 grid of microstate topographies (A-D)  [PNG]
  (2) Directionality summary (net sources/sinks, dominant flows)  [HTML]
  (3) Interactive explorer with five clinical panels  [HTML]
      - Topomaps: 2x2 contour topographies per state
      - Segmentation: GFP timeline with color-coded state segments
      - Statistics: bar charts (coverage, duration, occurrences/s, mean GFP)
      - Transitions: transition probability heatmap + directionality
      - Source 3D: LORETA source-localized brain surface (optional)

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

import json as _json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Static visualizations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def generate_microstate_visualizations(
    microstate_dict: Dict[str, Any],
    viz_dir: Path,
    subject_id: str = "unknown",
    session_id: str = "session",
) -> Dict[str, Path]:
    """Generate microstate topomap grid (PNG) and directionality summary (HTML)."""
    out: Dict[str, Path] = {}
    maps_raw = microstate_dict.get("maps")
    ch_names = microstate_dict.get("ch_names") or []
    state_labels = microstate_dict.get("state_labels") or ["A", "B", "C", "D"]
    n_states = min(len(maps_raw) if maps_raw else 0, len(state_labels))

    if not maps_raw or n_states < 1 or len(ch_names) < 4:
        return out

    try:
        from hexnode.eeg.viz.topomap_generator import TopomapGenerator
        from hexnode.eeg.viz.visualization_config import get_visualization_config
    except ImportError as e:
        logger.debug("Microstate viz skipped (import): %s", e)
        return out

    config = get_visualization_config()
    topo_gen = TopomapGenerator(config)
    maps_arr = np.array(maps_raw, dtype=float)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n_cols = 2
    n_rows = (n_states + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5, 4.5),
                             subplot_kw=dict(projection=None))
    if n_states == 1:
        axes = np.array([[axes]])
    elif n_rows == 1:
        axes = axes.reshape(1, -1)
    for si in range(n_states):
        row, col = si // n_cols, si % n_cols
        ax = axes[row, col]
        values = maps_arr[si].flatten()
        if len(values) != len(ch_names):
            values = np.resize(values, len(ch_names))
        title = f"State {state_labels[si] if si < len(state_labels) else si}"
        ok = topo_gen.plot_topomap_into_axes(
            ax, values, ch_names, title, is_zscore=False, allow_constant=True)
        if not ok:
            ax.axis("off")
            ax.set_title(title)
    for si in range(n_states, n_rows * n_cols):
        row, col = si // n_cols, si % n_cols
        axes[row, col].axis("off")
    fig.suptitle("EEG Microstates (resting-state topographies)", fontsize=11, y=1.02)
    fig.tight_layout()
    png_path = viz_dir / f"microstate_topomaps_{subject_id}_{session_id}.png"
    try:
        fig.savefig(png_path, dpi=150, bbox_inches="tight")
        out["microstate_topomaps"] = png_path
    except Exception as e:
        logger.warning("Could not save microstate topomaps: %s", e)
    finally:
        plt.close(fig)

    dirs = microstate_dict.get("directionality")
    if dirs:
        html_path = viz_dir / f"microstate_directionality_{subject_id}_{session_id}.html"
        html_lines = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Microstate directionality</title>",
            "<style>body{font-family:sans-serif;background:#0e1219;color:#d6f6ff;padding:1rem;}",
            "h2{color:#52e8fc;} table{border-collapse:collapse;} "
            "th,td{padding:4px 8px;border:1px solid #2a3a4a;}</style></head><body>",
            "<h2>Microstate directionality</h2>",
            "<p>Directed transitions between segments (resting-state network).</p>",
        ]
        if dirs.get("net_sources"):
            html_lines.append(
                f"<p><strong>Net sources</strong>: {', '.join(dirs['net_sources'])}</p>")
        if dirs.get("net_sinks"):
            html_lines.append(
                f"<p><strong>Net sinks</strong>: {', '.join(dirs['net_sinks'])}</p>")
        flows = dirs.get("dominant_flows") or []
        if flows:
            html_lines.append(
                "<h3>Dominant flows</h3><table>"
                "<tr><th>From</th><th>To</th><th>Probability</th></tr>")
            for f in flows[:12]:
                html_lines.append(
                    f"<tr><td>{f.get('from','?')}</td>"
                    f"<td>{f.get('to','?')}</td>"
                    f"<td>{f.get('probability',0):.3f}</td></tr>")
            html_lines.append("</table>")
        html_lines.append(
            f"<p><em>Total transitions: {dirs.get('total_transitions', 0)}</em></p>")
        html_lines.append("</body></html>")
        try:
            html_path.write_text("\n".join(html_lines), encoding="utf-8")
            out["microstate_directionality"] = html_path
        except Exception as e:
            logger.warning("Could not save microstate directionality HTML: %s", e)

    return out


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_NETWORK_KEYS = ["All", "frontal", "central", "parietal", "occipital", "temporal"]

_CHANNEL_TO_NETWORK_FALLBACK: Dict[str, str] = {}
for _site, _net in [
    ("Fp1", "frontal"), ("Fp2", "frontal"), ("F3", "frontal"), ("F4", "frontal"),
    ("F7", "frontal"), ("F8", "frontal"), ("Fz", "frontal"),
    ("C3", "central"), ("C4", "central"), ("Cz", "central"),
    ("P3", "parietal"), ("P4", "parietal"), ("Pz", "parietal"), ("P7", "parietal"), ("P8", "parietal"),
    ("O1", "occipital"), ("O2", "occipital"), ("Oz", "occipital"),
    ("T7", "temporal"), ("T8", "temporal"),
]:
    _CHANNEL_TO_NETWORK_FALLBACK[_site.upper()] = _net
    _CHANNEL_TO_NETWORK_FALLBACK[_site] = _net


def _channel_to_network() -> Dict[str, str]:
    """Channel name (any case) -> network name (frontal, central, etc.)."""
    try:
        from hexnode.eeg.reporting.systems_analyzer import SystemsAnalyzer
        sa = SystemsAnalyzer()
        out: Dict[str, str] = {}
        for net_name, info in sa.networks.items():
            for site in info.get("sites", []):
                out[site.upper()] = net_name
                out[site] = net_name
        if out:
            return out
    except Exception:
        pass
    return dict(_CHANNEL_TO_NETWORK_FALLBACK)


def _microstate_region_summary(
    maps_arr: np.ndarray,
    ch_names: List[str],
    state_labels: List[str],
    n_states: int,
    top_n: int = 8,
) -> List[Dict[str, Any]]:
    """Per-state summary: which networks/sites dominate (by |map|)."""
    from hexnode.eeg.viz.utils import clean_channel_name
    ch_to_net = _channel_to_network()
    out: List[Dict[str, Any]] = []
    for si in range(min(n_states, maps_arr.shape[0])):
        vals = np.abs(maps_arr[si, :])
        order = np.argsort(-vals)
        seen_ch: set = set()
        sites_by_net: Dict[str, List[str]] = {}
        for idx in order[: top_n * 2]:
            if idx >= len(ch_names):
                continue
            ch = ch_names[idx]
            ch_upper = ch.upper()
            clean = clean_channel_name(ch)
            if ch_upper in seen_ch or clean in seen_ch:
                continue
            seen_ch.add(ch_upper)
            net = ch_to_net.get(ch_upper) or ch_to_net.get(clean) or ch_to_net.get(ch)
            if not net:
                continue
            sites_by_net.setdefault(net, []).append(ch)
            if sum(len(v) for v in sites_by_net.values()) >= top_n:
                break
        dominant = list(sites_by_net.keys())
        summary_parts = [f"{net} ({', '.join(sites_by_net[net])})" for net in dominant]
        summary_str = "State {}: {}".format(
            state_labels[si] if si < len(state_labels) else si,
            "; ".join(summary_parts) if summary_parts else "no region match",
        )
        out.append({
            "state": state_labels[si] if si < len(state_labels) else str(si),
            "dominant_networks": dominant,
            "sites_by_network": sites_by_net,
            "summary": summary_str,
        })
    return out


def _build_interpolation_grids(
    maps_arr: np.ndarray, ch_names: List[str],
    topo_gen: Any, resolution: int = 40,
) -> List[Dict[str, Dict[str, Any]]]:
    """Per-state 2D interpolation grids for topomaps (All-network only for speed)."""
    from hexnode.eeg.viz.utils import clean_channel_name

    positions, valid_channels = topo_gen._get_channel_positions(ch_names)
    if len(positions) < 4:
        return []

    valid_idx = []
    for vc in valid_channels:
        for i, cn in enumerate(ch_names):
            if clean_channel_name(cn) == vc or cn == vc or cn.upper() == vc.upper():
                valid_idx.append(i)
                break
        else:
            valid_idx.append(-1)

    grids: List[Dict[str, Dict[str, Any]]] = []
    for si in range(maps_arr.shape[0]):
        values = np.zeros(len(valid_channels), dtype=float)
        for j, vch in enumerate(valid_channels):
            idx = valid_idx[j] if j < len(valid_idx) else -1
            if idx >= 0:
                values[j] = float(maps_arr[si, idx])
        try:
            Xi, Yi, Zi = topo_gen._clinical_interpolation(values, positions, resolution)
        except Exception:
            grids.append({})
            continue
        grids.append({"x": Xi[0, :].tolist(), "y": Yi[:, 0].tolist(),
                      "z": Zi.tolist()})
    return grids


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Interactive HTML (five clinical panels)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def generate_interactive_microstate_html(
    microstate_dict: Dict[str, Any],
    viz_dir: Path,
    subject_id: str = "unknown",
    session_id: str = "session",
    output_path: Optional[Path] = None,
    source_3d_data: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """
    Interactive HTML with five clinically focused panels:

      1. Topomaps     - 2x2 contour topographies per state
      2. Segmentation - GFP timeline + color-coded state strip (standard microstate fig)
      3. Statistics    - Bar charts: coverage, duration, occurrences/s, mean GFP
      4. Transitions   - Transition probability heatmap + directionality summary
      5. Source 3D     - LORETA source-localized brain surface (optional)

    Same control-bar aesthetic as the traceroute explorer.
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        logger.warning("Plotly not available for interactive microstate")
        return None

    maps_raw = microstate_dict.get("maps")
    ch_names = microstate_dict.get("ch_names") or []
    state_labels = microstate_dict.get("state_labels") or ["A", "B", "C", "D"]
    labels_ds = microstate_dict.get("labels_downsampled")
    labels_hz = microstate_dict.get("labels_downsample_hz") or 50.0
    gfp_ds = microstate_dict.get("gfp_downsampled") or []
    directionality = microstate_dict.get("directionality") or {}
    transition_matrix = microstate_dict.get("transition_matrix") or []
    stats = microstate_dict.get("stats") or {}

    n_states = min(len(maps_raw) if maps_raw else 0, len(state_labels))
    if not maps_raw or n_states < 1 or len(ch_names) < 4:
        return None
    if not labels_ds:
        logger.debug("No labels_downsampled; skipping interactive microstate")
        return None

    try:
        from hexnode.eeg.viz.topomap_generator import TopomapGenerator
        from hexnode.eeg.viz.visualization_config import get_visualization_config
    except ImportError as e:
        logger.debug("Microstate interactive skipped (import): %s", e)
        return None

    config = get_visualization_config()
    topo_gen = TopomapGenerator(config)
    maps_arr = np.array(maps_raw, dtype=float)

    grids = _build_interpolation_grids(maps_arr, ch_names, topo_gen, 40)
    if not grids:
        return None
    region_summary = _microstate_region_summary(
        maps_arr, ch_names, state_labels, n_states)
    has_source = bool(source_3d_data)
    total_dur = round(len(labels_ds) / labels_hz, 2) if labels_hz > 0 else 0

    # ─── Initial Plotly figure: 2x2 contour topomaps ──────────────

    def _topo_title(i: int) -> str:
        if i < len(region_summary) and region_summary[i].get("dominant_networks"):
            nets = ", ".join(region_summary[i]["dominant_networks"])
            return f"State {state_labels[i]} \u2014 {nets}"
        return f"State {state_labels[i]}"

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[_topo_title(i) for i in range(n_states)],
        vertical_spacing=0.12, horizontal_spacing=0.08,
    )
    for i in range(n_states):
        g = grids[i] if isinstance(grids[i], dict) and "x" in grids[i] else None
        if not g:
            continue
        fig.add_trace(go.Contour(
            x=g["x"], y=g["y"], z=g["z"],
            colorscale="Viridis", showscale=(i == 0),
            line_smoothing=1, contours_showlines=True,
        ), row=i // 2 + 1, col=i % 2 + 1)
    fig.update_layout(
        title=dict(text="<b>EEG Microstates \u2014 Topographies</b>",
                   font=dict(size=16, color="#e9eff7"), x=0.5, xanchor="center"),
        paper_bgcolor="#1a2432", plot_bgcolor="#1a2432",
        font=dict(family="Arial", size=11, color="#e9eff7"),
        margin=dict(l=50, r=50, t=60, b=40), showlegend=False,
    )
    for ax_name in ("xaxis", "yaxis", "xaxis2", "yaxis2",
                    "xaxis3", "yaxis3", "xaxis4", "yaxis4"):
        ax_obj = getattr(fig.layout, ax_name, None)
        if ax_obj is not None:
            ax_obj.update(visible=False)
    fig.update_annotations(font_color="#e9eff7")

    # ─── Control bar HTML ─────────────────────────────────────────
    ic = "#52e8fc"
    _s = ("background:#2e3d52;color:#E8EFF6;"
          "border:1px solid rgba(100,120,140,0.5);border-radius:6px;"
          "padding:4px 8px;font-family:inherit;font-size:11px;"
          "cursor:pointer;outline:none;")
    _l = "font-weight:700;letter-spacing:0.5px;font-size:10px;"
    view_opts = (
        '<option value="topomaps" selected>Topomaps</option>'
        '<option value="segmentation">Segmentation</option>'
        '<option value="statistics">Statistics</option>'
        '<option value="transitions">Transitions</option>'
        '<option value="network">3D Network</option>'
        + ('<option value="source">Source 3D</option>' if has_source else ''))
    def _state_opt_label(i: int) -> str:
        if i < len(region_summary) and region_summary[i].get("dominant_networks"):
            nets = ", ".join(region_summary[i]["dominant_networks"][:3])
            return f"State {state_labels[i]} ({nets})"
        return f"State {state_labels[i]}"
    state_opts = "".join(
        f'<option value="{i}">{_state_opt_label(i)}</option>'
        for i in range(n_states))

    controls_html = f'''
<div id="ms-ctrl" style="
  position:fixed;top:8px;right:14px;z-index:99998;
  display:flex;gap:8px;align-items:center;flex-wrap:wrap;
  background:#212d3e;padding:8px 14px;
  border-radius:10px;border:1px solid rgba(80,100,120,0.45);
  font-family:'Cascadia Code','Fira Mono',monospace;font-size:11px;
  box-shadow:0 2px 10px rgba(0,0,0,0.15);
  ">
  <span style="color:{ic};{_l}">VIEW</span>
  <select id="ms-view" style="{_s}">{view_opts}</select>
  <span id="ms-network-sep" style="color:#8A9CAE;font-size:10px;display:none;">|</span>
  <span id="ms-network-lbl" style="color:{ic};{_l}display:none;">NETWORK</span>
  <select id="ms-network" style="{_s}display:none;"><option value="all">ALL</option></select>
  <span id="ms-state-sep" style="color:#8A9CAE;font-size:10px;display:none;">|</span>
  <span id="ms-state-lbl" style="color:{ic};{_l}display:none;">STATE</span>
  <select id="ms-state" style="{_s}display:none;">{state_opts}</select>
</div>
<div id="ms-dir-panel" style="
  display:none;position:fixed !important;bottom:14px !important;right:14px !important;width:390px !important;
  background:#212d3e !important;border:1px solid rgba(80,100,120,0.50) !important;
  border-radius:12px !important;padding:0 !important;
  font-family:'Cascadia Code','Fira Mono','SF Mono',monospace !important;font-size:11px !important;
  color:#E4ECF2 !important;z-index:99999 !important;max-height:52vh !important;overflow-y:auto !important;
  box-shadow:0 4px 16px rgba(0,0,0,0.2), 0 0 1px rgba(100,140,180,0.15) !important;
  ">
  <div id="ms-dir-content"></div>
</div>
<div id="ms-network-info" style="
  display:none;position:fixed !important;bottom:14px !important;left:14px !important;width:320px !important;
  background:#212d3e !important;border:1px solid rgba(80,100,120,0.50) !important;
  border-radius:12px !important;padding:0 !important;
  font-family:'Cascadia Code','Fira Mono','SF Mono',monospace !important;font-size:11px !important;
  color:#E4ECF2 !important;z-index:99998 !important;max-height:52vh !important;overflow-y:auto !important;
  box-shadow:0 4px 16px rgba(0,0,0,0.2), 0 0 1px rgba(100,140,180,0.15) !important;
  ">
  <div id="ms-network-info-content"></div>
</div>'''

    # ─── Build embedded data + JavaScript ─────────────────────────
    js_data = (
        '"use strict";\n'
        'var G=' + _json.dumps(grids) + ';\n'
        'var SL=' + _json.dumps(state_labels[:n_states]) + ';\n'
        'var REGION_SUMMARY=' + _json.dumps(region_summary) + ';\n'
        'var LB=' + _json.dumps(labels_ds) + ';\n'
        'var GFP_DS=' + _json.dumps(gfp_ds) + ';\n'
        'var LHZ=' + str(labels_hz) + ';\n'
        'var DIR=' + _json.dumps(directionality) + ';\n'
        'var TRANS=' + _json.dumps(transition_matrix) + ';\n'
        'var STATS=' + _json.dumps(stats) + ';\n'
        'var NS=' + str(n_states) + ';\n'
        'var TDUR=' + str(total_dur) + ';\n'
        'var SRC=' + (_json.dumps(source_3d_data) if has_source else 'null') + ';\n'
    )

    js_logic = r'''
var SC=['#FF5566','#52e8fc','#5CDB7F','#FFA040','#8C6BFF','#E8D44D','#C84DBA','#45AAE8'];
var BG='#1a2432',FG='#e9eff7',GC='rgba(100,120,140,0.25)',AC='#52e8fc';

function $(id){return document.getElementById(id);}
var gd,vSel,sSel,sLbl,sSep,nNetSel,nNetLbl,nNetSep,nInfoPan,nInfoCon,dPan,dCon;

function stateLabel(i){
  var r=REGION_SUMMARY&&REGION_SUMMARY[i];
  if(r&&r.dominant_networks&&r.dominant_networks.length)
    return 'State '+SL[i]+' ('+r.dominant_networks.join(', ')+')';
  return 'State '+SL[i];
}
function stateLabelShort(i){
  var r=REGION_SUMMARY&&REGION_SUMMARY[i];
  if(r&&r.dominant_networks&&r.dominant_networks.length)
    return SL[i]+' ('+r.dominant_networks[0]+')';
  return 'State '+SL[i];
}

/* ================================================================
   PANEL 2: Segmentation Timeline (GFP + state color strip)
   ================================================================ */
function buildSeg(){
  var n=GFP_DS.length;
  if(!n){gd.innerHTML='<p style="color:#FF5566;padding:2rem;">No GFP data. Re-run analysis to generate segmentation.</p>';return;}
  var t=new Array(n);
  for(var i=0;i<n;i++) t[i]=+(i/LHZ).toFixed(4);

  var traces=[];
  for(var s=0;s<NS;s++){
    var y=new Array(n);
    for(var i=0;i<n;i++) y[i]=(LB[i]===s)?GFP_DS[i]:null;
    traces.push({type:'scatter',mode:'lines',x:t,y:y,
      line:{color:SC[s%SC.length],width:1.5},connectgaps:false,
      name:stateLabel(s),legendgroup:SL[s]});
  }

  var shapes=[];
  var si=0;
  while(si<n){
    var st=LB[si],start=si;
    while(si<n&&LB[si]===st) si++;
    shapes.push({type:'rect',xref:'x',yref:'paper',
      x0:start/LHZ,x1:si/LHZ,y0:0,y1:0.08,
      fillcolor:SC[st%SC.length],line:{width:0},opacity:0.85});
  }

  var layout={
    title:{text:'<b>Microstate Segmentation</b><br>'
      +'<span style="color:#A0B2C4;font-size:12px;">GFP colored by active state '
      +'\u2014 strip below shows state timeline</span>',
      font:{size:15,color:FG},x:0.5,xanchor:'center'},
    paper_bgcolor:BG,plot_bgcolor:BG,
    font:{color:FG,family:'Arial',size:11},
    xaxis:{title:'Time (s)',color:'#A0B2C4',gridcolor:GC,zerolinecolor:GC},
    yaxis:{title:'GFP (\u00B5V)',color:'#A0B2C4',gridcolor:GC,
      zerolinecolor:GC,domain:[0.14,1]},
    shapes:shapes,showlegend:true,
    legend:{font:{color:FG},bgcolor:'#1e2a3a',
      bordercolor:'rgba(100,120,140,0.3)',x:1,xanchor:'right',y:1},
    margin:{l:60,r:30,t:80,b:50}
  };
  Plotly.newPlot(gd,traces,layout,{responsive:true});
}

/* ================================================================
   PANEL 3: Statistics Dashboard (4 bar charts)
   ================================================================ */
function buildStats(){
  var ps=STATS.per_state||{};
  var lbs=[],cov=[],dur=[],occ=[],mgfp=[],cols=[];
  var durS=TDUR>0?TDUR:1;
  for(var i=0;i<NS;i++){
    var s=ps[SL[i]]||{};
    lbs.push(stateLabelShort(i));
    cov.push(s.coverage_pct||0);
    dur.push(s.mean_duration_ms||0);
    occ.push((s.n_occurrences||0)/durS);
    mgfp.push(s.mean_gfp||0);
    cols.push(SC[i%SC.length]);
  }
  var axS={color:'#A0B2C4',gridcolor:GC,zerolinecolor:GC};
  var traces=[
    {type:'bar',x:lbs,y:cov,marker:{color:cols},showlegend:false,
     xaxis:'x',yaxis:'y'},
    {type:'bar',x:lbs,y:dur,marker:{color:cols},showlegend:false,
     xaxis:'x2',yaxis:'y2'},
    {type:'bar',x:lbs,y:occ,marker:{color:cols},showlegend:false,
     xaxis:'x3',yaxis:'y3'},
    {type:'bar',x:lbs,y:mgfp,marker:{color:cols},showlegend:false,
     xaxis:'x4',yaxis:'y4'}
  ];
  var gev=((STATS.global_explained_variance||0)*100).toFixed(1);
  var layout={
    title:{text:'<b>Microstate Statistics</b><br>'
      +'<span style="color:#A0B2C4;font-size:12px;">Global Explained Variance: '
      +gev+'%</span>',
      font:{size:15,color:FG},x:0.5,xanchor:'center'},
    paper_bgcolor:BG,plot_bgcolor:BG,
    font:{color:FG,family:'Arial',size:11},
    xaxis: {domain:[0,0.45],anchor:'y', color:'#A0B2C4',tickangle:-30},
    yaxis: {domain:[0.58,1],anchor:'x', title:'Coverage (%)',
      color:axS.color,gridcolor:axS.gridcolor,zerolinecolor:axS.zerolinecolor},
    xaxis2:{domain:[0.55,1],anchor:'y2',color:'#A0B2C4',tickangle:-30},
    yaxis2:{domain:[0.58,1],anchor:'x2',title:'Duration (ms)',
      color:axS.color,gridcolor:axS.gridcolor,zerolinecolor:axS.zerolinecolor},
    xaxis3:{domain:[0,0.45],anchor:'y3',color:'#A0B2C4',tickangle:-30},
    yaxis3:{domain:[0,0.42],anchor:'x3',title:'Occurrences / s',
      color:axS.color,gridcolor:axS.gridcolor,zerolinecolor:axS.zerolinecolor},
    xaxis4:{domain:[0.55,1],anchor:'y4',color:'#A0B2C4',tickangle:-30},
    yaxis4:{domain:[0,0.42],anchor:'x4',title:'Mean GFP',
      color:axS.color,gridcolor:axS.gridcolor,zerolinecolor:axS.zerolinecolor},
    showlegend:false,
    margin:{l:60,r:30,t:80,b:70},
    annotations:[
      {text:'<b>Coverage</b>',xref:'paper',yref:'paper',x:0.225,y:1.04,
       showarrow:false,font:{color:AC,size:12}},
      {text:'<b>Duration</b>',xref:'paper',yref:'paper',x:0.775,y:1.04,
       showarrow:false,font:{color:AC,size:12}},
      {text:'<b>Occurrences / s</b>',xref:'paper',yref:'paper',x:0.225,y:0.48,
       showarrow:false,font:{color:AC,size:12}},
      {text:'<b>Mean GFP</b>',xref:'paper',yref:'paper',x:0.775,y:0.48,
       showarrow:false,font:{color:AC,size:12}}
    ]
  };
  Plotly.newPlot(gd,traces,layout,{responsive:true});
}

/* ================================================================
   PANEL 4: Transition Heatmap + Directionality (traceroute-style)
   ================================================================ */
function buildTrans(){
  if(!TRANS||!TRANS.length) return;
  var xLabs=[],yLabs=[];
  for(var i=0;i<NS;i++){ xLabs.push(stateLabelShort(i)); yLabs.push(stateLabelShort(i)); }
  var zNum=[]; for(var i=0;i<NS;i++){ var row=[]; for(var j=0;j<NS;j++){ var v=TRANS[i][j]; row.push(typeof v==='number'?v:parseFloat(v)); } zNum.push(row); }
  var annots=[];
  for(var i=0;i<NS;i++){
    for(var j=0;j<NS;j++){
      var v=zNum[i][j];
      annots.push({x:xLabs[j],y:yLabs[i],text:(isNaN(v)?0:v).toFixed(3),showarrow:false,
        font:{color:v>0.35?'#FFFFFF':'#E4ECF2',size:13}});
    }
  }
  var traces=[{type:'heatmap',x:xLabs,y:yLabs,z:zNum,
    colorscale:[[0,'#1a2432'],[0.15,'#142536'],[0.35,'#1e4976'],[0.6,'#2980b9'],[0.85,'#5dade2'],[1,'#aed6f1']],
    showscale:true,colorbar:{title:'P',titlefont:{color:'#A0B2C4',size:11},tickfont:{color:'#A0B2C4',size:10},outlinewidth:0,len:0.75},
    hovertemplate:'%{y} \u2192 %{x}: %{z:.3f}<extra></extra>'}];
  var interp='';
  if(REGION_SUMMARY&&REGION_SUMMARY.length){
    interp='<span style="color:#A0B0C0;font-size:10px;"> ';
    for(var i=0;i<NS;i++){
      var r=REGION_SUMMARY[i];
      if(r&&r.dominant_networks&&r.dominant_networks.length)
        interp+=SL[i]+' = '+r.dominant_networks[0]+(i<NS-1?' &nbsp;|&nbsp; ':'');
      else interp+=SL[i]+(i<NS-1?' &nbsp;|&nbsp; ':'');
    }
    interp+='</span>';
  }
  var layout={
    title:{text:'<span style="color:#52e8fc;font-weight:700;letter-spacing:0.5px;">TRANSITION PROBABILITIES</span><br>'
      +'<span style="color:#A0B0C0;font-size:11px;">Row = from state, Column = to state</span>'
      +(interp?'<br>'+interp:''),
      font:{size:14,color:'#E4ECF2'},x:0.5,xanchor:'center'},
    paper_bgcolor:BG,plot_bgcolor:BG,
    font:{color:'#E4ECF2',family:'Cascadia Code, Fira Mono, monospace',size:11},
    xaxis:{title:{text:'To',font:{color:'#8898AA',size:10}},side:'bottom',color:'#8898AA',tickfont:{size:11,color:'#C0CCD8'},gridcolor:'rgba(80,100,120,0.25)'},
    yaxis:{title:{text:'From',font:{color:'#8898AA',size:10}},autorange:'reversed',color:'#8898AA',tickfont:{size:11,color:'#C0CCD8'},gridcolor:'rgba(80,100,120,0.25)'},
    annotations:annots,
    margin:{l:72,r:88,t:88,b:64}
  };
  Plotly.newPlot(gd,traces,layout,{responsive:true});
  fillDir();
}

function fillDir(){
  if(!dCon) return;
  var total=DIR.total_transitions||0;
  var srcTxt=DIR.net_sources&&DIR.net_sources.length?DIR.net_sources.join(', '):'\u2014';
  var snkTxt=DIR.net_sinks&&DIR.net_sinks.length?DIR.net_sinks.join(', '):'\u2014';
  var h='<div style="padding:14px 18px 10px !important;background:linear-gradient(135deg, #2e3d52, #283548) !important;border-bottom:1px solid rgba(80,100,120,0.40) !important;border-radius:12px 12px 0 0 !important;">';
  h+='<div style="display:flex !important;align-items:center !important;gap:8px !important;margin-bottom:8px !important;">';
  h+='<div style="width:8px !important;height:8px !important;border-radius:50% !important;background:#52e8fc !important;box-shadow:0 0 6px #52e8fc !important;"></div>';
  h+='<span style="color:#52e8fc !important;font-weight:700 !important;font-size:13px !important;letter-spacing:0.8px !important;">DIRECTIONALITY</span></div>';
  h+='<div style="color:#A0B0C0 !important;font-size:10px !important;line-height:1.6 !important;">';
  h+='Net sources: <span style="color:#00FF88 !important;font-weight:600 !important;">'+srcTxt+'</span> &nbsp;|&nbsp; ';
  h+='Net sinks: <span style="color:#FF5566 !important;font-weight:600 !important;">'+snkTxt+'</span> &nbsp;|&nbsp; ';
  h+='Total: <span style="color:#D4DEE8 !important;">'+total+'</span></div></div>';
  h+='<div style="padding:10px 18px !important;">';
  if(DIR.dominant_flows&&DIR.dominant_flows.length){
    h+='<div style="color:#8898AA !important;font-weight:500 !important;font-size:9px !important;text-transform:uppercase !important;letter-spacing:0.5px !important;margin-bottom:6px !important;">From \u2192 To (prob)</div>';
    h+='<table style="border-collapse:collapse !important;width:100% !important;">';
    h+='<tr><th style="color:#8898AA !important;font-weight:500 !important;font-size:9px !important;padding:0 6px 5px !important;text-align:left !important;text-transform:uppercase !important;">From</th><th style="color:#8898AA !important;font-weight:500 !important;font-size:9px !important;padding:0 6px 5px !important;text-align:left !important;text-transform:uppercase !important;">To</th><th style="color:#8898AA !important;font-weight:500 !important;font-size:9px !important;padding:0 6px 5px !important;text-align:right !important;text-transform:uppercase !important;">Prob</th></tr>';
    DIR.dominant_flows.slice(0,12).forEach(function(f){
      h+='<tr><td style="padding:4px 8px !important;border-top:1px solid rgba(80,100,120,0.35) !important;color:#E4ECF2 !important;">'+(f.from||'?')+'</td><td style="padding:4px 8px !important;border-top:1px solid rgba(80,100,120,0.35) !important;color:#E4ECF2 !important;">'+(f.to||'?')+'</td><td style="padding:4px 8px !important;border-top:1px solid rgba(80,100,120,0.35) !important;color:#C0CCD8 !important;text-align:right !important;">'+(typeof f.probability==="number"?f.probability:parseFloat(f.probability)||0).toFixed(3)+'</td></tr>';
    });
    h+='</table>';
  }
  if(REGION_SUMMARY&&REGION_SUMMARY.length){
    h+='<div style="margin-top:12px !important;padding-top:10px !important;border-top:1px solid rgba(80,100,120,0.30) !important;color:#A0B2C4 !important;font-size:10px !important;">';
    h+='<span style="color:#52e8fc !important;font-weight:600 !important;">State (site):</span> ';
    for(var i=0;i<NS;i++){
      var r=REGION_SUMMARY[i];
      if(r&&r.dominant_networks&&r.dominant_networks.length)
        h+=SL[i]+' = '+r.dominant_networks.join(', ')+(i<NS-1?'; ':'');
      else h+=SL[i]+(i<NS-1?'; ':'');
    }
    h+='</div>';
  }
  if(DIR.per_state_flow){
    h+='<div style="margin-top:10px !important;color:#8898AA !important;font-size:9px !important;text-transform:uppercase !important;letter-spacing:0.5px !important;margin-bottom:4px !important;">Out / In / Net</div>';
    h+='<table style="border-collapse:collapse !important;width:100% !important;">';
    h+='<tr><th style="color:#8898AA !important;font-weight:500 !important;font-size:9px !important;padding:0 6px 5px !important;text-align:left !important;text-transform:uppercase !important;">State</th><th style="color:#8898AA !important;font-weight:500 !important;font-size:9px !important;padding:0 6px 5px !important;text-align:right !important;text-transform:uppercase !important;">Out</th><th style="color:#8898AA !important;font-weight:500 !important;font-size:9px !important;padding:0 6px 5px !important;text-align:right !important;text-transform:uppercase !important;">In</th><th style="color:#8898AA !important;font-weight:500 !important;font-size:9px !important;padding:0 6px 5px !important;text-align:right !important;text-transform:uppercase !important;">Net</th></tr>';
    for(var i=0;i<NS;i++){
      var pf=DIR.per_state_flow[SL[i]];
      if(!pf) continue;
      var net=pf.net_flow;
      var nc=net>0?'#00FF88':net<0?'#FF5566':'#D4DEE8';
      var stLabel=stateLabelShort(i);
      h+='<tr><td style="padding:4px 8px !important;border-top:1px solid rgba(80,100,120,0.35) !important;color:'+SC[i%SC.length]+' !important;font-weight:600 !important;">'+stLabel+'</td><td style="padding:4px 8px !important;border-top:1px solid rgba(80,100,120,0.35) !important;color:#C0CCD8 !important;text-align:right !important;">'+pf.outflow_count+'</td><td style="padding:4px 8px !important;border-top:1px solid rgba(80,100,120,0.35) !important;color:#C0CCD8 !important;text-align:right !important;">'+pf.inflow_count+'</td><td style="padding:4px 8px !important;border-top:1px solid rgba(80,100,120,0.35) !important;color:'+nc+' !important;font-weight:600 !important;text-align:right !important;">'+(net>0?'+':'')+net+'</td></tr>';
    }
    h+='</table>';
  }
  h+='</div>';
  h+='<div style="padding:10px 18px 14px !important;border-top:1px solid rgba(80,100,120,0.40) !important;background:#243040 !important;border-radius:0 0 12px 12px !important;">';
  h+='<span style="color:#8A9CAE !important;font-size:9px !important;text-transform:uppercase !important;">Total transitions</span> <span style="color:#D4DEE8 !important;font-weight:600 !important;">'+total+'</span></div>';
  dCon.innerHTML=h;
}

/* ================================================================
   PANEL: Microstate Transition Network (Gunkelman-style)
   Directed arrows, line thickness = probability, arc labels, state legend.
   ================================================================ */
function buildNetwork(){
  var n=NS; if(!n||!TRANS||!TRANS.length){gd.innerHTML='<p style="color:#FF5566;padding:2rem;">No transition data.</p>';return;}
  var radius=1.2;
  var nodeXY=[]; for(var i=0;i<n;i++){ var a=Math.PI/2-i*2*Math.PI/n; nodeXY.push([radius*Math.cos(a),radius*Math.sin(a)]); }
  var traces=[];
  var thresh=0.02;
  var arrowScale=0.14;
  var arcEnd=0.88;
  var labelX=[],labelY=[],labelZ=[],labelT=[];
  var coneX=[],coneY=[],coneZ=[],coneU=[],coneV=[],coneW=[],coneC=[];
  for(var i=0;i<n;i++){
    for(var j=0;j<n;j++){
      if(i===j) continue;
      var p=Array.isArray(TRANS[i])?TRANS[i][j]:0;
      p=typeof p==='number'?p:parseFloat(p);
      if(isNaN(p)||p<thresh) continue;
      var x0=nodeXY[i][0],y0=nodeXY[i][1],x1=nodeXY[j][0],y1=nodeXY[j][1];
      var mx=(x0+x1)/2,my=(y0+y1)/2;
      var len=Math.sqrt(mx*mx+my*my)||1;
      var ctrlScale=1.18;
      var cx=mx/len*radius*ctrlScale, cy=my/len*radius*ctrlScale, cz=0.12;
      var pts=21;
      var x=[],y=[],z=[];
      var lastIdx=Math.floor(pts*arcEnd);
      for(var k=0;k<=lastIdx;k++){
        var t=k/pts;
        var u=1-t;
        var bx=u*u*x0+2*u*t*cx+t*t*x1;
        var by=u*u*y0+2*u*t*cy+t*t*y1;
        var bz=2*u*t*cz;
        x.push(bx);y.push(by);z.push(bz);
      }
      var xTip=x[x.length-1],yTip=y[y.length-1],zTip=z[z.length-1];
      var dx=x1-xTip,dy=y1-yTip,dz=(0-zTip)||0.01;
      var dLen=Math.sqrt(dx*dx+dy*dy+dz*dz)||0.01;
      coneX.push(x1);coneY.push(y1);coneZ.push(0);
      coneU.push(-dx/dLen*arrowScale);coneV.push(-dy/dLen*arrowScale);coneW.push(-dz/dLen*arrowScale);
      coneC.push(SC[i%SC.length]);
      var tMid=0.5;
      var uMid=1-tMid;
      labelX.push(uMid*uMid*x0+2*uMid*tMid*cx+tMid*tMid*x1);
      labelY.push(uMid*uMid*y0+2*uMid*tMid*cy+tMid*tMid*y1);
      labelZ.push(2*uMid*tMid*cz+0.02);
      labelT.push((p*100).toFixed(0)+'%');
      var lineW=Math.max(3,5+p*8);
      traces.push({type:'scatter3d',mode:'lines',x:x,y:y,z:z,
        line:{color:SC[i%SC.length],width:lineW},showlegend:false});
    }
  }
  for(var ci=0;ci<coneX.length;ci++){
    traces.push({type:'cone',x:[coneX[ci]],y:[coneY[ci]],z:[coneZ[ci]],
      u:[coneU[ci]],v:[coneV[ci]],w:[coneW[ci]],
      colorscale:[[0,coneC[ci]],[1,coneC[ci]]],showscale:false,
      anchor:'tip',sizemode:'absolute',sizeref:0.08,showlegend:false});
  }
  if(labelX.length){
    traces.push({type:'scatter3d',mode:'text',x:labelX,y:labelY,z:labelZ,text:labelT,
      textfont:{size:11,color:FG},textposition:'middle center',showlegend:false});
  }
  var headR=1.52;
  var headN=64;
  var headX=[],headY=[],headZ=[];
  for(var hi=0;hi<=headN;hi++){
    var th=(hi/headN)*2*Math.PI;
    headX.push(headR*Math.cos(th));headY.push(headR*Math.sin(th));headZ.push(0);
  }
  traces.unshift({type:'scatter3d',mode:'lines',x:headX,y:headY,z:headZ,
    line:{color:'rgba(100,125,150,0.6)',width:2.5},
    name:'Scalp outline',showlegend:false});
  var noseX=[0,0],noseY=[headR,headR*1.14],noseZ=[0,0];
  traces.unshift({type:'scatter3d',mode:'lines',x:noseX,y:noseY,z:noseZ,
    line:{color:'rgba(90,110,130,0.6)',width:2},showlegend:false});
  var innerR=0.95;
  var innerX=[],innerY=[],innerZ=[];
  for(var hi=0;hi<=headN;hi++){
    var th=(hi/headN)*2*Math.PI;
    innerX.push(innerR*Math.cos(th));innerY.push(innerR*Math.sin(th));innerZ.push(0);
  }
  traces.unshift({type:'scatter3d',mode:'lines',x:innerX,y:innerY,z:innerZ,
    line:{color:'rgba(70,90,110,0.35)',width:1.5},showlegend:false});
  var headLabelX=[0,-headR-0.18,headR+0.18,0],headLabelY=[headR+0.2,0,0,-headR-0.18],headLabelZ=[0,0,0,0];
  var headLabelT=['Nose','L','R','Back'];
  traces.unshift({type:'scatter3d',mode:'text',x:headLabelX,y:headLabelY,z:headLabelZ,text:headLabelT,
    textfont:{size:10,color:'#A0B2C4'},textposition:'middle center',showlegend:false});
  var nx=[],ny=[],nz=[],nc=[];
  for(var i=0;i<n;i++){
    nx.push(nodeXY[i][0]);ny.push(nodeXY[i][1]);nz.push(0);
    nc.push(SC[i%SC.length]);
  }
  for(var si=0;si<n;si++){
    var nodeText=stateLabelShort(si);
    traces.push({type:'scatter3d',mode:'markers+text',x:[nx[si]],y:[ny[si]],z:[nz[si]],
      marker:{size:16,color:SC[si%SC.length],line:{color:'#fff',width:2},symbol:'circle'},
      text:[nodeText],textposition:'top center',textfont:{size:12,color:FG,family:'Arial'},
      name:stateLabelShort(si),showlegend:true});
  }
  var layout={
    title:{text:'<b>Microstate Transition Network</b> <span style="color:#A0B2C4;font-size:11px;">(scalp view)</span><br>'
      +'<span style="color:#A0B2C4;font-size:11px;">States = dominant topography. Arrows: direction. Thickness &amp; %: transition probability.</span>',
      font:{size:15,color:FG},x:0.5,xanchor:'center'},
    paper_bgcolor:BG,
    scene:{bgcolor:BG,
      xaxis:{visible:false},yaxis:{visible:false},zaxis:{visible:false},
      aspectmode:'data',
      camera:{eye:{x:0,y:2.2,z:0.8},up:{x:0,y:0,z:1}}},
    font:{color:FG},margin:{l:0,r:0,t:80,b:0},showlegend:true,
    legend:{font:{size:10,color:FG},bgcolor:'rgba(26,36,50,0.9)',bordercolor:'rgba(100,120,140,0.4)',
      x:1.02,xanchor:'left',y:0.5,yanchor:'middle',
      title:{text:'State (site)',font:{size:11,color:AC}}},
    updatemenus:[
      {type:'buttons',direction:'left',x:0.02,y:0.98,xanchor:'left',yanchor:'top',pad:{r:6,t:6},showactive:true,
        bgcolor:'#283548',bordercolor:'rgba(90,110,130,0.45)',font:{size:10,color:'#D8E2EC'},
        buttons:[
          {label:'Front',method:'relayout',args:[{'scene.camera':{eye:{x:0,y:2.2,z:0.8},up:{x:0,y:0,z:1}}}]},
          {label:'Top',method:'relayout',args:[{'scene.camera':{eye:{x:0,y:0,z:2.8},up:{x:0,y:1,z:0}}}]},
          {label:'Left',method:'relayout',args:[{'scene.camera':{eye:{x:-2.2,y:0,z:0.8},up:{x:0,y:0,z:1}}}]},
          {label:'Right',method:'relayout',args:[{'scene.camera':{eye:{x:2.2,y:0,z:0.8},up:{x:0,y:0,z:1}}}]}
        ]},
      {type:'buttons',direction:'left',x:0.98,y:0.98,xanchor:'right',yanchor:'top',pad:{r:6,t:6},showactive:true,
        bgcolor:'#283548',bordercolor:'rgba(90,110,130,0.45)',font:{size:10,color:'#D8E2EC'},
        buttons:[{label:'Play',method:'restyle',args:[{}]}]}
    ]
  };
  Plotly.newPlot(gd,traces,layout,{responsive:true});
  fillNetworkInfo();
}

function fillNetworkInfo(){
  if(!nInfoCon) return;
  var h='<div style="padding:14px 18px 10px !important;background:linear-gradient(135deg, #2e3d52, #283548) !important;border-bottom:1px solid rgba(80,100,120,0.40) !important;border-radius:12px 12px 0 0 !important;">';
  h+='<div style="display:flex !important;align-items:center !important;gap:8px !important;margin-bottom:6px !important;">';
  h+='<div style="width:8px !important;height:8px !important;border-radius:50% !important;background:#52e8fc !important;box-shadow:0 0 6px #52e8fc !important;"></div>';
  h+='<span style="color:#52e8fc !important;font-weight:700 !important;font-size:12px !important;letter-spacing:0.8px !important;">NETWORK INFO</span></div>';
  h+='<div style="color:#A0B0C0 !important;font-size:10px !important;">Scalp view: nodes = microstates (dominant site). Use Front/Top/Left/Right to rotate.</div></div>';
  h+='<div style="padding:10px 18px !important;">';
  h+='<div style="color:#8898AA !important;font-weight:600 !important;font-size:9px !important;text-transform:uppercase !important;letter-spacing:0.5px !important;margin-bottom:6px !important;">How to read</div>';
  h+='<ul style="margin:0 0 12px 14px !important;padding:0 !important;color:#C0CCD8 !important;font-size:10px !important;line-height:1.6 !important;">';
  h+='<li>Each circle is a microstate (A\u2013D) at a scalp position.</li>';
  h+='<li>Arrows show transition direction (source \u2192 target).</li>';
  h+='<li>Thicker arrow = higher transition probability.</li>';
  h+='<li>% label on each arc = P(transition) from that pair.</li>';
  h+='</ul>';
  h+='<div style="color:#8898AA !important;font-weight:600 !important;font-size:9px !important;text-transform:uppercase !important;letter-spacing:0.5px !important;margin-bottom:6px !important;">Keys</div>';
  h+='<table style="border-collapse:collapse !important;width:100% !important;font-size:10px !important;">';
  h+='<tr><td style="padding:2px 6px 2px 0 !important;color:#52e8fc !important;">Arrow color</td><td style="padding:2px 0 !important;color:#C0CCD8 !important;">= source state (from)</td></tr>';
  h+='<tr><td style="padding:2px 6px 2px 0 !important;color:#52e8fc !important;">Thickness</td><td style="padding:2px 0 !important;color:#C0CCD8 !important;">= transition probability</td></tr>';
  h+='<tr><td style="padding:2px 6px 2px 0 !important;color:#52e8fc !important;">% on arc</td><td style="padding:2px 0 !important;color:#C0CCD8 !important;">= P(to|from) in percent</td></tr>';
  h+='<tr><td style="padding:2px 6px 2px 0 !important;color:#52e8fc !important;">Nose / L / R / Back</td><td style="padding:2px 0 !important;color:#C0CCD8 !important;">= scalp orientation</td></tr>';
  h+='</table>';
  h+='<div style="margin-top:12px !important;padding-top:10px !important;border-top:1px solid rgba(80,100,120,0.30) !important;color:#8898AA !important;font-weight:600 !important;font-size:9px !important;text-transform:uppercase !important;letter-spacing:0.5px !important;margin-bottom:6px !important;">State (site) legend</div>';
  h+='<div style="color:#C0CCD8 !important;font-size:10px !important;line-height:1.8 !important;">';
  for(var si=0;si<NS;si++){
    h+='<span style="display:inline-block !important;width:8px !important;height:8px !important;border-radius:50% !important;background:'+SC[si%SC.length]+' !important;margin-right:6px !important;vertical-align:middle !important;"></span> ';
    h+=stateLabelShort(si)+'<br>';
  }
  h+='</div><p style="margin:8px 0 0 !important;color:#8A9CAE !important;font-size:9px !important;">See <b>Topomaps</b> view for full topography per state.</p>';
  h+='</div>';
  h+='<div style="padding:10px 18px 14px !important;border-top:1px solid rgba(80,100,120,0.40) !important;background:#243040 !important;border-radius:0 0 12px 12px !important;">';
  h+='<span style="color:#8A9CAE !important;font-size:9px !important;">View</span> <span style="color:#D4DEE8 !important;">Front / Top / Left / Right</span> for 3D orientation.</div>';
  nInfoCon.innerHTML=h;
}

/* ================================================================
   PANEL 5: Source 3D (LORETA brain, optional)
   ================================================================ */
function buildSrc(si){
  if(!SRC||!SRC.per_state||!SRC.per_state[si]){
    gd.innerHTML='<p style="color:#A0B2C4;padding:2rem;text-align:center;">'
      +'Source localization data not available.<br>Requires LORETA pipeline.</p>';
    return;
  }
  var S=SRC.per_state[si];
  if(!S||!(S.lh_x||S.rh_x)){
    gd.innerHTML='<p style="color:#A0B2C4;padding:2rem;text-align:center;">'
      +'Source localization data not available for this state.<br>Requires LORETA pipeline (run with EDF + LORETA enabled).</p>';
    return;
  }
  var traces=[];
  if(S.lh_x) traces.push({type:'mesh3d',x:S.lh_x,y:S.lh_y,z:S.lh_z,
    i:S.lh_i,j:S.lh_j,k:S.lh_k,intensity:S.lh_colors,
    colorscale:'Hot',cmin:S.cmin||0,cmax:S.cmax||1,
    showscale:true,opacity:0.92,
    lighting:{ambient:0.45,diffuse:0.55,specular:0.2,roughness:0.85},
    lightposition:{x:100,y:200,z:300},
    colorbar:{title:'Activity',titlefont:{color:FG},tickfont:{color:'#A0B2C4'}},
    name:'Left'});
  if(S.rh_x) traces.push({type:'mesh3d',x:S.rh_x,y:S.rh_y,z:S.rh_z,
    i:S.rh_i,j:S.rh_j,k:S.rh_k,intensity:S.rh_colors,
    colorscale:'Hot',cmin:S.cmin||0,cmax:S.cmax||1,
    showscale:false,opacity:0.92,
    lighting:{ambient:0.45,diffuse:0.55,specular:0.2,roughness:0.85},
    lightposition:{x:100,y:200,z:300},
    name:'Right'});
  var layout={
    title:{text:'<b>'+stateLabel(si)+' \u2014 Source Localization ('
      +(SRC.method||'sLORETA')+')</b>',
      font:{size:15,color:FG},x:0.5,xanchor:'center'},
    paper_bgcolor:BG,
    scene:{bgcolor:BG,
      xaxis:{visible:false},yaxis:{visible:false},zaxis:{visible:false},
      aspectmode:'data',
      camera:{eye:{x:0,y:2.2,z:0.8},up:{x:0,y:0,z:1}}},
    font:{color:FG},margin:{l:0,r:0,t:60,b:0},showlegend:false,
    updatemenus:[{type:'buttons',direction:'left',x:0.02,y:0.98,
      xanchor:'left',yanchor:'top',pad:{r:6,t:6},showactive:true,
      bgcolor:'#283548',bordercolor:'rgba(90,110,130,0.45)',
      font:{size:10,color:'#D8E2EC'},
      buttons:[
        {label:'Front',method:'relayout',
         args:[{'scene.camera':{eye:{x:0,y:2.2,z:0.8},up:{x:0,y:0,z:1}}}]},
        {label:'Top',method:'relayout',
         args:[{'scene.camera':{eye:{x:0,y:0,z:2.8},up:{x:0,y:1,z:0}}}]},
        {label:'Left',method:'relayout',
         args:[{'scene.camera':{eye:{x:-2.2,y:0,z:0.8},up:{x:0,y:0,z:1}}}]},
        {label:'Right',method:'relayout',
         args:[{'scene.camera':{eye:{x:2.2,y:0,z:0.8},up:{x:0,y:0,z:1}}}]}
      ]}]
  };
  Plotly.newPlot(gd,traces,layout,{responsive:true});
}

/* ================================================================
   View switcher
   ================================================================ */
function switchTo(v){
  if(!gd||!window.Plotly) return;
  var showState=(v==='source');
  var showNetwork=(v==='network');
  if(sLbl) sLbl.style.display=showState?'inline':'none';
  if(sSel) sSel.style.display=showState?'inline':'none';
  if(sSep) sSep.style.display=showState?'inline':'none';
  if(nNetLbl) nNetLbl.style.display=showNetwork?'inline':'none';
  if(nNetSel) nNetSel.style.display=showNetwork?'inline':'none';
  if(nNetSep) nNetSep.style.display=showNetwork?'inline':'none';
  if(dPan) dPan.style.display=(v==='transitions')?'block':'none';

  if(v==='topomaps'&&window.MS_TD){
    Plotly.react(gd,window.MS_TD,window.MS_TL);
  }
  else if(v==='segmentation') buildSeg();
  else if(v==='statistics')   buildStats();
  else if(v==='transitions')  buildTrans();
  else if(v==='network')      buildNetwork();
  else if(v==='source')       buildSrc(sSel?parseInt(sSel.value,10):0);
}

/* ================================================================
   Init (wait for Plotly CDN + graph render)
   ================================================================ */
function init(){
  gd=document.querySelector('.plotly-graph-div');
  vSel=$('ms-view');sSel=$('ms-state');sLbl=$('ms-state-lbl');
  sSep=$('ms-state-sep');
  nNetSel=$('ms-network');nNetLbl=$('ms-network-lbl');nNetSep=$('ms-network-sep');
  nInfoPan=$('ms-network-info');nInfoCon=$('ms-network-info-content');
  dPan=$('ms-dir-panel');dCon=$('ms-dir-content');

  if(!gd||!window.Plotly){setTimeout(init,60);return;}
  if(!gd.data||!gd.data.length){setTimeout(init,60);return;}

  window.MS_TD=gd.data.map(function(t){
    return {type:t.type,x:t.x,y:t.y,z:t.z,
      colorscale:t.colorscale||'Viridis',showscale:t.showscale,
      line_smoothing:t.line_smoothing,contours:t.contours};
  });
  window.MS_TL=JSON.parse(JSON.stringify(gd.layout));

  if(vSel) vSel.addEventListener('change',function(){switchTo(vSel.value);});
  if(sSel) sSel.addEventListener('change',function(){
    if(vSel&&vSel.value==='source') buildSrc(parseInt(sSel.value,10));
  });
}
setTimeout(init,80);
'''

    script = ('<script>\n(function(){\n' + js_data + js_logic
              + '\n})();\n</script>')

    # ─── Assemble HTML ────────────────────────────────────────────
    html = fig.to_html(include_plotlyjs=True)
    if "<body>" in html:
        html = html.replace(
            "<body>",
            '<body>\n' + controls_html + '\n<div id="ms-plot-wrap">\n',
            1)
    html = html.replace("</body>", "\n</div>\n" + script + "\n</body>", 1)

    if output_path is None:
        output_path = viz_dir / f"microstate_interactive_{subject_id}_{session_id}.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info("Saved interactive microstate: %s", output_path)
    return output_path
