# Copyright (C) 2026  EEG Paradox Solutions LLM contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Paradox Solutions LLM. Licensed under GNU GPL v3 or later.
# See the LICENSE file in the repository root.

# Paradox Solutions LLM — start Ollama + FastAPI + Next.js UI (Windows).
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\launch.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\launch.ps1 -Reinstall   # pip -e .[all] + npm ci/install
#   powershell -ExecutionPolicy Bypass -File scripts\launch.ps1 -NoBrowser  # do not open browser
#   powershell -ExecutionPolicy Bypass -File scripts\launch.ps1 -SkipOllama # API + web only (no Ollama)
# Double-click: launch.bat  (passes args through, e.g. launch.bat -NoBrowser -SkipOllama)

param(
    [switch] $Reinstall,
    [switch] $NoBrowser,
    [switch] $SkipOllama
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = Split-Path $PSScriptRoot -Parent

Set-Location $Root
Write-Host "[Paradox] Launcher running from: $Root" -ForegroundColor Cyan

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "No .venv found. Run:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "[Paradox] venv OK" -ForegroundColor DarkGray

# EEG workspace + output (run_python_analysis, Script / code tab, viz_* scripts)
New-Item -ItemType Directory -Force -Path "data\eeg_workspace\output" | Out-Null

if ($Reinstall) {
    Write-Host "Reinstalling Python package (extras: all = discord + eeg/MNE/plotly)..."
    & .\.venv\Scripts\pip.exe install -e ".[all]"
    Write-Host "npm install (web)..."
    Push-Location (Join-Path $Root "web")
    npm install
    Pop-Location
}

# -- 0. Kill stale listeners on 8765 / 3000 ------------------------------------
# Get-NetTCPConnection can hang for a long time on some Windows setups; netstat is instant.
function Stop-ParadoxListenersOnPorts {
    param([int[]]$Ports)
    Write-Host "[Paradox] Checking ports $($Ports -join ', ') for stale listeners (netstat)..." -ForegroundColor DarkGray
    try {
        $lines = @(netstat.exe -ano 2>$null)
    } catch {
        Write-Host "  Port cleanup skipped (netstat failed)." -ForegroundColor DarkYellow
        return
    }
    foreach ($port in $Ports) {
        $token = ":$port "
        foreach ($line in $lines) {
            if ($line -notmatch "LISTENING") { continue }
            if (-not ($line -like "*$token*")) { continue }
            if ($line -match "LISTENING\s+(\d+)\s*$") {
                $procId = [int]$Matches[1]
                if ($procId -le 4) { continue }
                try {
                    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                    Write-Host "  Freed port $port (stopped PID $procId)" -ForegroundColor DarkGray
                } catch {}
            }
        }
    }
    Start-Sleep -Seconds 1
}

try {
    Stop-ParadoxListenersOnPorts -Ports @(8765, 3000)
} catch {
    Write-Host "  (Port cleanup skipped: $($_.Exception.Message))" -ForegroundColor DarkGray
}
Write-Host "[Paradox] Port check done" -ForegroundColor DarkGray

# -- Required models -----------------------------------------------------------
$RequiredModels = @("qwen3:8b", "nomic-embed-text")

# -- 1. Find Ollama -----------------------------------------------------------
function Find-Ollama {
    $exe = Get-Command ollama -ErrorAction SilentlyContinue
    if ($exe) { return $exe.Source }
    $localPrograms = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $localPrograms) { return $localPrograms }
    $pf = Join-Path $env:ProgramFiles "Ollama\ollama.exe"
    if (Test-Path $pf) { return $pf }
    return $null
}

$Ollama = $null
if (-not $SkipOllama) {
    $Ollama = Find-Ollama
    if (-not $Ollama) {
        Write-Host "Ollama not found. Install from https://ollama.com or use:  launch.bat -SkipOllama" -ForegroundColor Red
        exit 1
    }
    Write-Host "Ollama: $Ollama" -ForegroundColor DarkGray

    # -- 2. Start Ollama if not already running --------------------------------
    function Test-OllamaRunning {
        try {
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop
            return $true
        } catch { return $false }
    }

    if (-not (Test-OllamaRunning)) {
        Write-Host "Starting Ollama..." -ForegroundColor Yellow
        $env:OLLAMA_FLASH_ATTENTION = "1"
        $env:OLLAMA_KV_CACHE_TYPE   = "q8_0"
        Start-Process -FilePath $Ollama -ArgumentList "serve" -WindowStyle Hidden
        $deadline = (Get-Date).AddSeconds(30)
        while (-not (Test-OllamaRunning)) {
            if ((Get-Date) -gt $deadline) {
                Write-Host "Ollama did not start within 30s. Check Ollama logs." -ForegroundColor Red
                exit 1
            }
            Start-Sleep -Milliseconds 500
        }
        Write-Host "Ollama is running." -ForegroundColor Green
    } else {
        Write-Host "Ollama already running." -ForegroundColor Green
    }

    # -- 3. Pull missing models -----------------------------------------------
    $existingRaw = ""
    try {
        $listJob = Start-Job -ScriptBlock { param($exe) & $exe list 2>&1 | Out-String } -ArgumentList $Ollama
        $null = Wait-Job $listJob -Timeout 45
        if ($listJob.State -eq "Completed") {
            $existingRaw = Receive-Job $listJob
        } else {
            Write-Host "  ollama list timed out or failed ($($listJob.State)) - skip model detection; pull models manually if needed." -ForegroundColor Yellow
            Stop-Job $listJob -ErrorAction SilentlyContinue
        }
        Remove-Job $listJob -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Host "  Could not run ollama list; continuing." -ForegroundColor Yellow
    }
    foreach ($model in $RequiredModels) {
        $shortName = ($model -split ":")[0]
        if ($existingRaw -match [regex]::Escape($shortName)) {
            Write-Host "  Model $model - already pulled" -ForegroundColor DarkGray
        } else {
            Write-Host "  Pulling $model (first time may take a few minutes)..." -ForegroundColor Yellow
            & $Ollama pull $model
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  Failed to pull $model" -ForegroundColor Red
            } else {
                Write-Host "  $model ready" -ForegroundColor Green
            }
        }
    }
} else {
    Write-Host "Skipping Ollama (models must be available separately if you use chat)." -ForegroundColor Yellow
}

# -- 4. Start API --------------------------------------------------------------
Write-Host ""
Write-Host "Starting Paradox API (port 8765)..." -ForegroundColor Cyan

$apiCmd = "Write-Host 'Paradox API  http://127.0.0.1:8765' -ForegroundColor Cyan; & .\.venv\Scripts\python.exe .\run_server.py"
Start-Process powershell.exe -WorkingDirectory $Root -ArgumentList "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $apiCmd

# Wait for API to respond before starting the web UI (first uvicorn+reload import can be slow)
Write-Host "Waiting for API to come online..." -NoNewline
$apiDeadline = (Get-Date).AddSeconds(120)
$apiUp = $false
while ((Get-Date) -lt $apiDeadline) {
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -TimeoutSec 3 -ErrorAction Stop
        $apiUp = $true
        break
    } catch {
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 1
    }
}
if ($apiUp) {
    Write-Host " OK" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "API did not respond within 120s - check the API PowerShell window for errors; starting web UI anyway." -ForegroundColor Yellow
}

# -- 5. Start Web UI -----------------------------------------------------------
Write-Host "Starting web UI (port 3000)..." -ForegroundColor Cyan
$webDir = Join-Path $Root "web"
$webUiStarted = $false

function Find-NpmCmd {
    $cmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    $cmd = Get-Command npm -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -match '\.(cmd|exe)$') { return $cmd.Source }
    foreach ($p in @(
            (Join-Path $env:ProgramFiles "nodejs\npm.cmd"),
            (Join-Path ${env:ProgramFiles(x86)} "nodejs\npm.cmd"),
            (Join-Path $env:LOCALAPPDATA "Programs\node\npm.cmd")
        )) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    return $null
}

if (-not (Test-Path -LiteralPath (Join-Path $webDir "package.json"))) {
    Write-Host "  Missing web/package.json - cannot start UI." -ForegroundColor Red
} elseif (-not (Test-Path -LiteralPath (Join-Path $webDir "node_modules"))) {
    Write-Host "  Missing web/node_modules. Run:  powershell -File scripts\setup.ps1   or   cd web; npm install" -ForegroundColor Red
} else {
    $npmPath = Find-NpmCmd
    if (-not $npmPath) {
        Write-Host "  npm not found in PATH. Install Node.js LTS (https://nodejs.org), reopen the terminal, then run setup.ps1." -ForegroundColor Red
    } else {
        Write-Host "  npm: $npmPath" -ForegroundColor DarkGray
        # New PowerShell -Command often fails to find npm; invoke npm.cmd directly with cwd = web/
        Start-Process -FilePath $npmPath -WorkingDirectory $webDir -ArgumentList @("run", "dev")
        $webUiStarted = $true
    }
}

# -- 6. Open browser -----------------------------------------------------------
if (-not $NoBrowser) {
    if ($webUiStarted) {
        Start-Sleep -Seconds 4
        Write-Host "Opening browser..."
        Start-Process "http://localhost:3000"
    } else {
        Write-Host "Skipping browser open (web UI was not started - fix errors above)." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "API:       http://127.0.0.1:8765/health  |  Swagger: /docs" -ForegroundColor Green
Write-Host "Web UI:    http://localhost:3000  (Session, EEG Data, Script / code)" -ForegroundColor Green
Write-Host "Ollama:    http://127.0.0.1:11434" -ForegroundColor Green
Write-Host "Optional:  copy .env.example -> .env ; set GOOGLE_CSE_* for Google+DDG search" -ForegroundColor DarkGray
Write-Host "Close the two PowerShell windows to stop API + web dev servers." -ForegroundColor DarkGray
Write-Host "This launcher window is idle (safe to close)." -ForegroundColor DarkGray
