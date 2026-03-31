#!/usr/bin/env python3
# Copyright (C) 2026  EEG Paradox Solutions LLM contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Add GNU GPL v3+ file headers to project sources (idempotent). Run from repo root."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_GPL_HEADER_LINE = re.compile(
    r"(?m)^(?:#|//|\s*\*\s*)SPDX-License-Identifier:\s*GPL-3\.0-or-later\s*$"
)

HEADER_PY = """# Copyright (C) 2026  EEG Paradox Solutions LLM contributors
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

"""

HEADER_TS = """/*
 * @license GPL-3.0-or-later
 * Copyright (C) 2026 EEG Paradox Solutions LLM contributors
 *
 * This file is part of Paradox Solutions LLM. See LICENSE in the repository root.
 */

"""

HEADER_PS1 = """# Copyright (C) 2026  EEG Paradox Solutions LLM contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Paradox Solutions LLM. Licensed under GNU GPL v3 or later.
# See the LICENSE file in the repository root.

"""

HEADER_RS = """// Copyright (C) 2026  EEG Paradox Solutions LLM contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// This file is part of Paradox Solutions LLM. See LICENSE in the repository root.

"""


def _skip_dir(p: Path) -> bool:
    parts = set(p.parts)
    return ".venv" in parts or "node_modules" in parts or "target" in parts


def _already_tagged(raw: str) -> bool:
    return bool(_GPL_HEADER_LINE.search(raw.replace("\r\n", "\n")))


def _dedupe_block(text: str, block: str) -> str:
    """Remove accidental duplicate consecutive GPL blocks (CRLF-safe)."""
    use_crlf = "\r\n" in text
    b = block.replace("\r\n", "\n")
    t = text.replace("\r\n", "\n")
    while b + b in t:
        t = t.replace(b + b, b, 1)
    if use_crlf:
        return t.replace("\n", "\r\n")
    return t


def collect_py() -> list[Path]:
    out: list[Path] = []
    for root in (REPO / "hexnode", REPO / "data" / "eeg_scripts"):
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if _skip_dir(p):
                continue
            out.append(p)
    for name in ("run_server.py", "eeg_subprocess_launcher.py", "runtime_hook.py"):
        p = REPO / name
        if p.is_file():
            out.append(p)
    for p in REPO.glob("*.spec"):
        out.append(p)
    scr = REPO / "scripts"
    if scr.is_dir():
        for p in scr.glob("*.py"):
            out.append(p)
    return sorted(set(out))


def dedupe_all() -> int:
    n = 0
    for p in collect_py():
        t = p.read_text(encoding="utf-8")
        d = _dedupe_block(t, HEADER_PY)
        if d != t:
            p.write_text(d, encoding="utf-8", newline="")
            n += 1
    web_src = REPO / "web" / "src"
    if web_src.is_dir():
        for p in web_src.rglob("*"):
            if p.suffix not in (".ts", ".tsx"):
                continue
            t = p.read_text(encoding="utf-8")
            d = _dedupe_block(t, HEADER_TS)
            if d != t:
                p.write_text(d, encoding="utf-8", newline="")
                n += 1
    for p in REPO.glob("web/*.ts"):
        t = p.read_text(encoding="utf-8")
        d = _dedupe_block(t, HEADER_TS)
        if d != t:
            p.write_text(d, encoding="utf-8", newline="")
            n += 1
    for name in ("postcss.config.mjs", "eslint.config.mjs"):
        p = REPO / "web" / name
        if not p.is_file():
            continue
        t = p.read_text(encoding="utf-8")
        d = _dedupe_block(t, HEADER_TS)
        if d != t:
            p.write_text(d, encoding="utf-8", newline="")
            n += 1
    scr = REPO / "scripts"
    if scr.is_dir():
        for p in scr.glob("*.ps1"):
            t = p.read_text(encoding="utf-8")
            d = _dedupe_block(t, HEADER_PS1)
            if d != t:
                p.write_text(d, encoding="utf-8", newline="\n")
                n += 1
    tauri_src = REPO / "src-tauri" / "src"
    if tauri_src.is_dir():
        for p in tauri_src.glob("*.rs"):
            t = p.read_text(encoding="utf-8")
            d = _dedupe_block(t, HEADER_RS)
            if d != t:
                p.write_text(d, encoding="utf-8", newline="\n")
                n += 1
    p = REPO / "src-tauri" / "build.rs"
    if p.is_file():
        t = p.read_text(encoding="utf-8")
        d = _dedupe_block(t, HEADER_RS)
        if d != t:
            p.write_text(d, encoding="utf-8", newline="\n")
            n += 1
    print(f"Deduped GPL header blocks in {n} files.")
    return 0


def insert_python(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8")
    if _already_tagged(raw):
        return False
    try:
        tree = ast.parse(raw)
    except SyntaxError:
        print(f"  skip (syntax): {path.relative_to(REPO)}")
        return False

    lines = raw.splitlines(keepends=True)
    i = 0
    if i < len(lines) and lines[i].startswith("#!"):
        i += 1
    if i < len(lines) and lines[i].startswith("#") and "coding" in lines[i]:
        i += 1
    while i < len(lines) and lines[i].strip() == "":
        i += 1

    insert_idx = i
    if tree.body and isinstance(tree.body[0], ast.Expr):
        v = tree.body[0].value
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            insert_idx = tree.body[0].end_lineno

    header_lines = HEADER_PY.splitlines(keepends=True)
    new_lines = lines[:insert_idx] + header_lines + lines[insert_idx:]
    out = "".join(new_lines)
    out = re.sub(
        r"\nCopyright \(C\) 2025[^\n]*EEG Paradox Clinical System Contributors\n",
        "\n",
        out,
        count=1,
    )
    path.write_text(out, encoding="utf-8", newline="")
    return True


def insert_ts(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8")
    if _already_tagged(raw) or "@license GPL-3.0-or-later" in raw:
        return False
    lines = raw.splitlines(keepends=True)
    if not lines:
        return False
    insert_at = 0
    if lines[0].strip() in ('"use client";', "'use client';", '"use server";', "'use server';"):
        insert_at = 1
        if insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
    header_lines = HEADER_TS.splitlines(keepends=True)
    new_lines = lines[:insert_at] + header_lines + lines[insert_at:]
    path.write_text("".join(new_lines), encoding="utf-8", newline="")
    return True


def insert_ps1(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8")
    if _already_tagged(raw):
        return False
    path.write_text(HEADER_PS1 + raw, encoding="utf-8", newline="\n")
    return True


def insert_rs(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8")
    if _already_tagged(raw):
        return False
    path.write_text(HEADER_RS + raw, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    if "--dedupe" in sys.argv:
        return dedupe_all()
    added = 0
    for p in collect_py():
        if insert_python(p):
            print(f"  + {p.relative_to(REPO)}")
            added += 1

    web_src = REPO / "web" / "src"
    if web_src.is_dir():
        for p in web_src.rglob("*"):
            if p.suffix not in (".ts", ".tsx"):
                continue
            if insert_ts(p):
                print(f"  + {p.relative_to(REPO)}")
                added += 1

    for p in REPO.glob("web/*.ts"):
        if insert_ts(p):
            print(f"  + {p.relative_to(REPO)}")
            added += 1
    for name in ("postcss.config.mjs", "eslint.config.mjs"):
        p = REPO / "web" / name
        if p.is_file() and insert_ts(p):
            print(f"  + {p.relative_to(REPO)}")
            added += 1

    scripts = REPO / "scripts"
    if scripts.is_dir():
        for p in scripts.glob("*.ps1"):
            if insert_ps1(p):
                print(f"  + {p.relative_to(REPO)}")
                added += 1

    tauri_src = REPO / "src-tauri" / "src"
    if tauri_src.is_dir():
        for p in tauri_src.glob("*.rs"):
            if insert_rs(p):
                print(f"  + {p.relative_to(REPO)}")
                added += 1
    p = REPO / "src-tauri" / "build.rs"
    if p.is_file() and insert_rs(p):
        print(f"  + {p.relative_to(REPO)}")
        added += 1

    print(f"Done. GPL headers added or already present. Files updated this run: {added}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
