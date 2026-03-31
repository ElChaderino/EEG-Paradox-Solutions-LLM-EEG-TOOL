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

# PyInstaller spec for Paradox Solutions LLM backend
# Build: pyinstaller paradox-api.spec

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
import os

block_cipher = None

# ── Heavy ML packages to exclude (not needed - we use Ollama for inference) ──
_EXCLUDES = [
    "torch", "torchvision", "torchaudio", "torchtext",
    "transformers", "datasets", "huggingface_hub", "tokenizers", "safetensors",
    "tensorflow", "keras", "jax", "jaxlib", "flax",
    "faiss", "faiss_cpu", "faiss_gpu",
    "bitsandbytes", "accelerate", "diffusers",
    "wandb", "mlflow", "tensorboard",
    "IPython", "ipykernel", "ipywidgets", "jupyter", "notebook", "nbformat",
    "matplotlib", "plotly", "seaborn", "bokeh",
    "scipy", "mne", "pandas", "pyarrow",
    "sklearn", "scikit-learn", "xgboost", "lightgbm",
    "cv2", "opencv-python", "PIL", "Pillow",
    "tkinter", "_tkinter",
    "sympy", "numba", "llvmlite",
    "dask", "ray", "pyspark",
    "spacy", "nltk", "gensim",
    "onnx", "onnxruntime",
    "triton", "flash_attn",
    "pyedflib",
    "chromadb.server",
]

# ── Collect heavy packages that have hidden imports / data ──────────────
chromadb_datas, chromadb_binaries, chromadb_hiddens = collect_all("chromadb")

# Filter out excluded modules from chromadb's transitive deps
chromadb_hiddens = [h for h in chromadb_hiddens
                    if not any(h == ex or h.startswith(ex + ".") for ex in _EXCLUDES)]
chromadb_binaries = [(src, dst) for src, dst in chromadb_binaries
                     if not any(ex in src for ex in ["torch", "faiss", "cuda", "triton"])]

trafilatura_datas = collect_data_files("trafilatura")
pydantic_datas = collect_data_files("pydantic")
certifi_datas = collect_data_files("certifi")

# ── Our own submodules (PyInstaller can miss dynamic imports) ───────────
hexnode_hiddens = collect_submodules("hexnode")
hexnode_eeg_viz_hiddens = collect_submodules("hexnode.eeg.viz")
hexnode_hiddens = list(set(hexnode_hiddens + hexnode_eeg_viz_hiddens))

# ── Data files to bundle alongside the exe ──────────────────────────────
added_datas = [
    ("web/out", "web/out"),
    ("data/eeg_reference", "data/eeg_reference"),
    ("data/eeg_scripts", "data/eeg_scripts"),
    ("hexnode/symbolic/default_rules.yaml", "hexnode/symbolic"),
    # Connectivity norm CSVs for pipeline z-scores (hexnode.eeg.pipeline bundled path)
    ("hexnode/eeg/norms/data", "hexnode/eeg/norms/data"),
    # ── EEG subprocess source files ──────────────────────────────────────
    # The viz / clinical-q scripts run in a *system* Python subprocess
    # (not the frozen exe) because MNE/SciPy/Matplotlib are excluded from the
    # bundle.  That subprocess cannot import from the PYZ bytecode archive, so
    # we ship the raw .py source tree it needs alongside the compiled modules.
    ("hexnode/__init__.py", "hexnode"),
    ("hexnode/eeg", "hexnode/eeg"),
    (".env.example", "."),
    ("rules.example.yaml", "."),
]

a = Analysis(
    ["run_server.py"],
    pathex=["."],
    binaries=chromadb_binaries,
    datas=added_datas + chromadb_datas + trafilatura_datas + pydantic_datas + certifi_datas,
    hiddenimports=[
        *chromadb_hiddens,
        *hexnode_hiddens,
        "hnswlib",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "httpx",
        "httpx._transports",
        "httpx._transports.default",
        "httpcore",
        "h11",
        "anyio",
        "anyio._backends",
        "anyio._backends._asyncio",
        "sniffio",
        "pydantic",
        "pydantic_settings",
        "pydantic_core",
        "trafilatura",
        # beautifulsoup4 is the pip *package* name; the importable module is bs4 only.
        "bs4",
        "ddgs",
        "psutil",
        "pypdf",
        "yaml",
        "multipart",
        "python_multipart",
        "starlette",
        "starlette.staticfiles",
        "starlette.middleware",
        "starlette.middleware.cors",
        "fastapi",
        "fastapi.staticfiles",
        "fastapi.middleware",
        "fastapi.middleware.cors",
        "cryptography",
        "cryptography.hazmat",
        "cryptography.hazmat.primitives",
        "cryptography.hazmat.primitives.asymmetric",
        "cryptography.hazmat.primitives.asymmetric.rsa",
        "cffi",
        "sqlite3",
        "encodings",
        "encodings.idna",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["runtime_hook.py"],
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
    name="paradox-api",
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="paradox-api",
)
