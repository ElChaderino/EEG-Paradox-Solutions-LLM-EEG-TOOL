# Copyright (C) 2026  EEG Paradox Solutions LLM contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Paradox Solutions LLM. Licensed under GNU GPL v3 or later.
# See the LICENSE file in the repository root.

# Paradox Solutions LLM - one-shot Windows setup (venv, deps, data dirs, .env, web).
# Run from repository root:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

Write-Host "Root: $Root"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
} else {
    Write-Host ".env already exists - skipped"
}

New-Item -ItemType Directory -Force -Path "data\ingest_queue", "data\vault\reflections", "data\eeg_workspace\output" | Out-Null
if (-not (Test-Path "data\rules.yaml") -and (Test-Path "rules.example.yaml")) {
    Copy-Item "rules.example.yaml" "data\rules.yaml"
    Write-Host "Created data\rules.yaml from rules.example.yaml (optional symbolic hints)"
}
Write-Host "Data directories OK"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    Write-Host "Created .venv"
}

$ProgressPreference = "SilentlyContinue"
Write-Host "Upgrading pip (quiet)..." -ForegroundColor DarkGray
& .\.venv\Scripts\python.exe -m pip install --upgrade pip -q
Write-Host "Installing Python package pip install -e .[all] - this can take several minutes; output follows." -ForegroundColor Cyan
& .\.venv\Scripts\pip.exe install -e ".[all]"
Write-Host "Python package installed (editable + all extras: discord, eeg/MNE/plotly/connectivity)"

# Single-quoted -c so PowerShell does not parse () in get_registry().tool_specs()
$n = & .\.venv\Scripts\python.exe -c 'from hexnode.tools.registry import get_registry; print(len(get_registry().tool_specs()))'
Write-Host "Tool registry: $n tools"

Push-Location web
Write-Host "Running npm install in web/ - may take a few minutes..." -ForegroundColor Cyan
npm install
if (-not (Test-Path ".env.local")) {
    $webEnv = 'NEXT_PUBLIC_PARADOX_API=http://127.0.0.1:8765' + [Environment]::NewLine
    Set-Content -LiteralPath '.env.local' -Value $webEnv -Encoding utf8
    Write-Host 'Created web/.env.local'
}
Pop-Location

Write-Host ""
Write-Host 'Next steps:'
Write-Host '  1. Start Ollama and pull models (see README).'
Write-Host '  2. Launch API + UI:  powershell -ExecutionPolicy Bypass -File scripts\launch.ps1'
Write-Host '     Or double-click launch.bat (or Launch Paradox.bat) in the repo root'
