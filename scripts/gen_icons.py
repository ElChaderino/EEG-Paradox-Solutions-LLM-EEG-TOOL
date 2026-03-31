"""Generate Tauri application icons."""
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

import os
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow not installed, using fallback PNG generation")
    raise SystemExit(1)

ICON_DIR = Path(__file__).resolve().parent.parent / "src-tauri" / "icons"
ICON_DIR.mkdir(parents=True, exist_ok=True)

BG = "#1a1a2e"
FG = "#e94560"


def make_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = size // 8
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=size // 6,
        fill=BG,
    )
    try:
        font = ImageFont.truetype("arial", size * 2 // 5)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "P", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) // 2, (size - th) // 2 - bbox[1]),
        "P",
        fill=FG,
        font=font,
    )
    return img


for s in [32, 128]:
    make_icon(s).save(ICON_DIR / f"{s}x{s}.png")

make_icon(256).save(ICON_DIR / "128x128@2x.png")
make_icon(256).save(ICON_DIR / "icon.png")

sizes_ico = [16, 32, 48, 256]
imgs = [make_icon(s) for s in sizes_ico]
imgs[0].save(
    ICON_DIR / "icon.ico",
    format="ICO",
    sizes=[(s, s) for s in sizes_ico],
    append_images=imgs[1:],
)

for f in sorted(ICON_DIR.iterdir()):
    print(f"  {f.name} ({f.stat().st_size} bytes)")
print("Done.")
