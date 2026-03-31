/*
 * @license GPL-3.0-or-later
 * Copyright (C) 2026 EEG Paradox Solutions LLM contributors
 *
 * This file is part of Paradox Solutions LLM. See LICENSE in the repository root.
 */

import type { NextConfig } from "next";
import path from "path";
import { fileURLToPath } from "url";

/** App root (this folder). Keeps Turbopack resolving `tailwindcss` from `web/node_modules`, not the repo workspace root. */
const webRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  turbopack: {
    root: webRoot,
  },
};

export default nextConfig;
