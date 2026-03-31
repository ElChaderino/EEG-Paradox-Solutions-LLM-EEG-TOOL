# Copyright (C) 2026  EEG Paradox Solutions LLM contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Paradox Solutions LLM. Licensed under GNU GPL v3 or later.
# See the LICENSE file in the repository root.

# Freeze the Python backend into dist/paradox-api/ using PyInstaller.
# Prerequisites: pip install pyinstaller, and web/out/ must exist (run build_frontend.ps1 first).
#
# Build order: EEG worker first (dist/paradox-eeg-worker), then main API (dist/paradox-api),
# then copy worker into dist/paradox-api/eeg-worker. If the API step cannot remove
# dist/paradox-api (WinError 5), close any running paradox-api.exe, Explorer windows
# on that folder, and retry.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    if (-not (Test-Path "web\out\index.html")) {
        Write-Host "web/out/ not found - building frontend first..." -ForegroundColor Yellow
        powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\build_frontend.ps1"
    }

    if (-not (Test-Path ".venv\Scripts\pyinstaller.exe")) {
        Write-Error "PyInstaller not found. Run: pip install pyinstaller"
        exit 1
    }

    # Worker first: avoids touching dist/paradox-api until API build runs.
    Write-Host "Running PyInstaller (EEG worker: MNE, plotly, scipy)..." -ForegroundColor Cyan
    & .\.venv\Scripts\pyinstaller.exe --noconfirm paradox-eeg-worker.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed for paradox-eeg-worker.spec (exit $LASTEXITCODE)"
    }
    $workerSrc = "dist\paradox-eeg-worker"
    if (-not (Test-Path "$workerSrc\paradox-eeg-worker.exe")) {
        throw "EEG worker build incomplete - $workerSrc\paradox-eeg-worker.exe not found"
    }

    Write-Host "Running PyInstaller (main API)..." -ForegroundColor Cyan
    # PyInstaller tries to rmtree(dist/paradox-api); AV or a running API can lock DLLs.
    # Rename the old folder so COLLECT can use a fresh path (delete the backup later).
    $apiDist = Join-Path $repoRoot "dist\paradox-api"
    if (Test-Path $apiDist) {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backup = Join-Path $repoRoot "dist\paradox-api_prev_$stamp"
        Write-Host "  Moving aside existing dist\paradox-api -> $(Split-Path $backup -Leaf)..." -ForegroundColor DarkGray
        try {
            Rename-Item -LiteralPath $apiDist -NewName (Split-Path $backup -Leaf) -ErrorAction Stop
        } catch {
            Write-Host "  Could not rename dist\paradox-api (in use). Close paradox-api.exe / Explorer on that folder, then retry." -ForegroundColor Yellow
            throw $_
        }
    }

    & .\.venv\Scripts\pyinstaller.exe --noconfirm paradox-api.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed for paradox-api.spec (exit $LASTEXITCODE). Often WinError 5: unlock dist\paradox-api then retry."
    }

    $workerDest = "dist\paradox-api\eeg-worker"
    if (Test-Path $workerDest) {
        Remove-Item -Recurse -Force $workerDest
    }
    Copy-Item -Recurse -Force $workerSrc $workerDest
    Write-Host "Copied EEG worker to $workerDest" -ForegroundColor Green

    $exe = "dist\paradox-api\paradox-api.exe"
    if (-not (Test-Path $exe)) {
        throw "Build failed - $exe not found"
    }

    $sizeMB = [math]::Round((Get-ChildItem -Recurse "dist\paradox-api" | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
    Write-Host "Backend build complete: $exe ($sizeMB MB total)" -ForegroundColor Green

    # Post-build validation: catch missing EEG subprocess files early
    Write-Host "`nValidating bundle integrity..." -ForegroundColor Cyan
    $internal = "dist\paradox-api\_internal"
    $criticalFiles = @(
        "$internal\hexnode\__init__.py",
        "$internal\hexnode\eeg\__init__.py",
        "$internal\hexnode\eeg\viz\run_visualizations.py",
        "$internal\hexnode\eeg\viz\topomap_generator.py",
        "$internal\hexnode\eeg\viz\spectrum_generator.py",
        "$internal\hexnode\eeg\viz\scalp_3d_generator.py",
        "$internal\hexnode\eeg\viz\topo_sheet_generator.py",
        "$internal\hexnode\eeg\norms\enrichment.py",
        "$internal\hexnode\eeg\norms\norm_manager.py",
        "$internal\data\eeg_scripts\clinical_q_assessment.py",
        "$internal\data\eeg_scripts\band_power_analysis.py"
    )
    $missing = @()
    foreach ($f in $criticalFiles) {
        if (-not (Test-Path $f)) {
            Write-Host "  MISSING: $f" -ForegroundColor Red
            $missing += $f
        }
    }
    $workerExe = "dist\paradox-api\eeg-worker\paradox-eeg-worker.exe"
    if (-not (Test-Path $workerExe)) {
        Write-Host "  MISSING: $workerExe (MNE/plotly viz subprocess needs bundled worker)" -ForegroundColor Red
        $missing += $workerExe
    }

    if ($missing.Count -gt 0) {
        throw "Bundle validation failed ($($missing.Count) missing files). API COLLECT may have failed earlier; check paradox-api.spec and unlock dist\paradox-api."
    }
    Write-Host "  All critical EEG files + bundled worker present" -ForegroundColor Green
} finally {
    Pop-Location
}
