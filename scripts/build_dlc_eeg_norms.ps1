# Copyright (C) 2026  EEG Paradox Solutions LLM contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Paradox Solutions LLM. Licensed under GNU GPL v3 or later.
# See the LICENSE file in the repository root.

# Build standalone EEG norms add-on installer (NSIS).
# Requires: NSIS (makensis.exe on PATH)
# Output: dist/Paradox_EEG_Norms_Addon_Setup.exe

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$addonRoot = Join-Path $repoRoot "addons\eeg-norms-dlc"
$payload = Join-Path $addonRoot "payload"
$staging = Join-Path $addonRoot "build\staging"
$distDir = Join-Path $repoRoot "dist"

if (-not (Test-Path (Join-Path $payload "data\cuban_databases"))) {
    Write-Host "ERROR: payload\data\cuban_databases not found. Populate addons\eeg-norms-dlc\payload from EEG_Paradox_Decoder\data." -ForegroundColor Red
    exit 1
}

$makensisExe = $null
$cmd = Get-Command makensis -ErrorAction SilentlyContinue
if ($cmd) {
    $makensisExe = $cmd.Source
}
if (-not $makensisExe) {
    foreach ($candidate in @(
        "${env:ProgramFiles(x86)}\NSIS\Bin\makensis.exe",
        "${env:ProgramFiles(x86)}\NSIS\makensis.exe",
        "$env:ProgramFiles\NSIS\Bin\makensis.exe",
        "$env:ProgramFiles\NSIS\makensis.exe",
        "$env:LOCALAPPDATA\tauri\NSIS\Bin\makensis.exe",
        "$env:LOCALAPPDATA\tauri\NSIS\makensis.exe"
    )) {
        if ($candidate -and (Test-Path $candidate)) {
            $makensisExe = $candidate
            break
        }
    }
}
if (-not $makensisExe) {
    Write-Host "ERROR: makensis not found. Install NSIS (winget install NSIS.NSIS) or add NSIS to PATH." -ForegroundColor Red
    exit 1
}
Write-Host "Using: $makensisExe"

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
if (Test-Path $staging) {
    Remove-Item -Recurse -Force $staging
}
New-Item -ItemType Directory -Force -Path $staging | Out-Null
Copy-Item -Path (Join-Path $payload "*") -Destination $staging -Recurse -Force

Push-Location $addonRoot
try {
    & $makensisExe "installer.nsi"
    if ($LASTEXITCODE -ne 0) {
        throw "makensis failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

$out = Join-Path $distDir "Paradox_EEG_Norms_Addon_Setup.exe"
Write-Host "Optional: regenerate connectivity z-score CSVs from DLC coherence tables:" -ForegroundColor DarkGray
Write-Host "  python `"$repoRoot\scripts\build_dlc_connectivity_norms.py`"" -ForegroundColor DarkGray

if (Test-Path $out) {
    Write-Host "OK: $out" -ForegroundColor Green
} else {
    Write-Host "ERROR: expected output not found: $out" -ForegroundColor Red
    exit 1
}
