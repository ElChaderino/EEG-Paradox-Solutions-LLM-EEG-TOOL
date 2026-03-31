# -*- mode: python ; coding: utf-8 -*-
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

# PyInstaller: dedicated EEG / NetOps worker (MNE, plotly, scipy, …)
# Build: pyinstaller --noconfirm paradox-eeg-worker.spec
# Output: dist/paradox-eeg-worker/  → copy into dist/paradox-api/eeg-worker/ (see build_backend.ps1)

from PyInstaller.utils.hooks import collect_all, collect_submodules
import os

block_cipher = None

# Keep the worker lean: no API server stack, no LLM / vector DB
_EXCLUDES = [
    "torch", "torchvision", "torchaudio", "torchtext",
    "transformers", "datasets", "huggingface_hub", "tokenizers", "safetensors",
    "tensorflow", "keras", "jax", "jaxlib", "flax",
    "faiss", "faiss_cpu", "faiss_gpu",
    "chromadb", "chromadb.server",
    "fastapi", "uvicorn", "starlette",
    "IPython", "ipykernel", "ipywidgets", "jupyter", "notebook", "nbformat",
    "tkinter", "_tkinter",
    "trafilatura", "ddgs",
]

def _collect(name: str):
    try:
        return collect_all(name)
    except Exception:
        return [], [], []


mne_d, mne_bin, mne_h = _collect("mne")
plotly_d, plotly_bin, plotly_h = _collect("plotly")
scipy_d, scipy_bin, scipy_h = _collect("scipy")
mpl_d, mpl_bin, mpl_h = _collect("matplotlib")
sk_d, sk_bin, sk_h = _collect("sklearn")
nx_d, nx_bin, nx_h = _collect("networkx")
sm_d, sm_bin, sm_h = _collect("statsmodels")
pd_d, pd_bin, pd_h = _collect("pandas")
pil_d, pil_bin, pil_h = _collect("Pillow")
orjson_d, orjson_bin, orjson_h = _collect("orjson")
nibabel_d, nibabel_bin, nibabel_h = _collect("nibabel")
nilearn_d, nilearn_bin, nilearn_h = _collect("nilearn")

# mne-connectivity / optional pipeline deps
try:
    mne_conn_h = collect_submodules("mne_connectivity")
except Exception:
    mne_conn_h = []
try:
    mne_ica_h = collect_submodules("mne_icalabel")
except Exception:
    mne_ica_h = []

all_binaries = mne_bin + plotly_bin + scipy_bin + mpl_bin + sk_bin + nx_bin + sm_bin + pd_bin + pil_bin + orjson_bin + nibabel_bin + nilearn_bin
all_datas = mne_d + plotly_d + scipy_d + mpl_d + sk_d + nx_d + sm_d + pd_d + pil_d + orjson_d + nibabel_d + nilearn_d

# Drop chromadb/torch paths if pulled transitively
def _bin_ok(src: str) -> bool:
    s = src.lower()
    return not any(x in s for x in ["torch", "faiss", "cuda", "triton", "chromadb"])

all_binaries = [(s, d) for s, d in all_binaries if _bin_ok(s)]

hidden = list(
    set(
        mne_h + plotly_h + scipy_h + mpl_h + sk_h + nx_h + sm_h + pd_h + pil_h
        + orjson_h + nibabel_h + nilearn_h + mne_conn_h + mne_ica_h
        + [
            "numpy",
            "PIL",
            "PIL.Image",
            "certifi",
            "importlib.resources",
            "orjson",
            "nibabel",
            "nibabel.freesurfer",
            "nibabel.spatialimages",
            "nibabel.processing",
            "nilearn",
            "nilearn.image",
            "nilearn.plotting",
            "nilearn.datasets",
        ]
    )
)
hidden = [h for h in hidden if not any(h == ex or h.startswith(ex + ".") for ex in _EXCLUDES)]

a = Analysis(
    ["eeg_subprocess_launcher.py"],
    pathex=["."],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUDES,
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="paradox-eeg-worker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="paradox-eeg-worker",
)
