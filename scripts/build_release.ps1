# Copyright (C) 2026  EEG Paradox Solutions LLM contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Paradox Solutions LLM. Licensed under GNU GPL v3 or later.
# See the LICENSE file in the repository root.

# Paradox Solutions LLM - full release build pipeline.
# Produces MSI + NSIS installers in src-tauri/target/release/bundle/
#
# Prerequisites (dev machine):
#   - Python 3.11+, Node.js/npm
#   - Rust toolchain (rustup)
#   - Tauri CLI: cargo install "tauri-cli@^2"
#   - PyInstaller: pip install pyinstaller
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1 -SkipFrontend
#   powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1 -SkipBackend

param(
    [switch]$SkipFrontend,
    [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

function Write-Step($msg) {
    Write-Host "`n========================================" -ForegroundColor DarkCyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor DarkCyan
}

try {
    # ── Step 1: Build static frontend ────────────────────────────────────
    if (-not $SkipFrontend) {
        Write-Step "Step 1/4 - Building static frontend"
        Push-Location "web"
        if (-not (Test-Path "node_modules")) {
            Write-Host "  Installing npm dependencies..." -ForegroundColor Yellow
            npm install
        }
        npm run build
        if (-not (Test-Path "out\index.html")) {
            throw "Frontend build failed - web/out/index.html not found"
        }
        Write-Host "  Frontend ready: web/out/index.html" -ForegroundColor Green
        Pop-Location
    } else {
        Write-Step "Step 1/4 - Skipping frontend (-SkipFrontend)"
        if (-not (Test-Path "web\out\index.html")) {
            throw "web/out/index.html not found. Run without -SkipFrontend first."
        }
    }

    # ── Step 2: PyInstaller backend (API + bundled EEG worker) ───────────
    if (-not $SkipBackend) {
        Write-Step "Step 2/4 - Freezing Python backend (paradox-api + paradox-eeg-worker)"
        & powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\build_backend.ps1"
        if ($LASTEXITCODE -ne 0) {
            throw "build_backend.ps1 failed with exit code $LASTEXITCODE"
        }
    } else {
        Write-Step "Step 2/4 - Skipping backend (-SkipBackend)"
        if (-not (Test-Path "dist\paradox-api\paradox-api.exe")) {
            throw "dist/paradox-api/paradox-api.exe not found. Run without -SkipBackend first."
        }
    }

    # ── Step 3: Tauri build ──────────────────────────────────────────────
    Write-Step "Step 3/4 - Building Tauri desktop app + installers"

    if (-not (Test-Path "src-tauri\tauri.conf.json")) {
        throw "src-tauri\tauri.conf.json missing. This repo uses the same Tauri v2 layout as the unified Paradox desktop tree (see README Desktop section)."
    }

    $env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"

    if (-not (Get-Command "cargo-tauri" -ErrorAction SilentlyContinue)) {
        if (-not (Test-Path "$env:USERPROFILE\.cargo\bin\cargo-tauri.exe")) {
            throw "Tauri CLI not found. Run: cargo install 'tauri-cli@^2'"
        }
    }

    # Tauri beforeBuildCommand uses %PARADOX_REPO_ROOT% (see tauri.conf.json) because hook cwd is not reliable with spaces/paths.
    $env:PARADOX_REPO_ROOT = (Resolve-Path ".").Path
    Write-Host "  PARADOX_REPO_ROOT=$($env:PARADOX_REPO_ROOT)" -ForegroundColor DarkGray
    Push-Location "src-tauri"
    try {
        cargo tauri build --ci
        if ($LASTEXITCODE -ne 0) {
            throw "Tauri build failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }

    # ── Step 4: Report ───────────────────────────────────────────────────
    Write-Step "Step 4/4 - Build complete!"

    $msiPath = "src-tauri\target\release\bundle\msi"
    $nsisPath = "src-tauri\target\release\bundle\nsis"

    if (Test-Path $msiPath) {
        Get-ChildItem $msiPath -Filter "*.msi" | ForEach-Object {
            $mb = [math]::Round($_.Length / 1MB, 1)
            Write-Host "  MSI:  $($_.FullName) ($mb MB)" -ForegroundColor Green
        }
    }
    if (Test-Path $nsisPath) {
        Get-ChildItem $nsisPath -Filter "*.exe" | ForEach-Object {
            $mb = [math]::Round($_.Length / 1MB, 1)
            Write-Host "  NSIS: $($_.FullName) ($mb MB)" -ForegroundColor Green
        }
    }

    $stopwatch.Stop()
    $elapsed = $stopwatch.Elapsed
    Write-Host "`n  Total build time: $($elapsed.Minutes)m $($elapsed.Seconds)s" -ForegroundColor Cyan

} catch {
    Write-Host "`nBUILD FAILED: $_" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}
