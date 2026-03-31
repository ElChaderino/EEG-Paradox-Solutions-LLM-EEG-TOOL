# Copyright (C) 2026  EEG Paradox Solutions LLM contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Paradox Solutions LLM. Licensed under GNU GPL v3 or later.
# See the LICENSE file in the repository root.

# Build the Next.js frontend as a static export (web/out/).
# After this, FastAPI serves the UI directly - no Node.js runtime needed.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    if (-not (Test-Path "web\package.json")) {
        Write-Error "web\package.json not found - run from repo root"
        exit 1
    }

    Push-Location "web"

    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing npm dependencies..." -ForegroundColor Yellow
        npm install
    }

    Write-Host "Building static frontend..." -ForegroundColor Cyan
    npm run build

    if (-not (Test-Path "out\index.html")) {
        Write-Error "Build failed - out/index.html not found"
        exit 1
    }

    Write-Host "Static build complete: web/out/index.html ready" -ForegroundColor Green

    Pop-Location
} finally {
    Pop-Location
}
