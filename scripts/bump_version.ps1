# Copyright (C) 2026  EEG Paradox Solutions LLM contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Paradox Solutions LLM. Licensed under GNU GPL v3 or later.
# See the LICENSE file in the repository root.

<#
.SYNOPSIS
  Bump the Paradox Solutions LLM version across every file that carries it.

.DESCRIPTION
  Reads the NEW version from the root VERSION file (single source of truth),
  then patches: tauri.conf.json, Cargo.toml, pyproject.toml, hexnode/__init__.py,
  hexnode/api/main.py, web/package.json, README.md, doc/README.md.

  Run from the repo root:
    powershell -ExecutionPolicy Bypass -File scripts\bump_version.ps1

  To set a new version, edit VERSION first, then run this script.
  Or pass it as an argument:
    scripts\bump_version.ps1 -NewVersion 0.4.0
#>

param(
    [string]$NewVersion
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Push-Location $root

try {
    if (-not $NewVersion) {
        if (-not (Test-Path "VERSION")) {
            throw "VERSION file not found at repo root. Create it or pass -NewVersion."
        }
        $NewVersion = (Get-Content "VERSION" -Raw).Trim()
    }

    if ($NewVersion -notmatch '^\d+\.\d+\.\d+(-[\w.]+)?$') {
        throw "Invalid semver: '$NewVersion'. Expected something like 1.2.3 or 1.2.3-beta.1"
    }

    Write-Host "=== Bumping to $NewVersion ===" -ForegroundColor Cyan

    # 1. VERSION file
    Set-Content "VERSION" "$NewVersion`n" -NoNewline:$false
    Write-Host "  [ok] VERSION"

    # 2. src-tauri/tauri.conf.json
    $tauriConf = "src-tauri\tauri.conf.json"
    if (Test-Path $tauriConf) {
        $json = Get-Content $tauriConf -Raw
        $json = $json -replace '"version"\s*:\s*"[^"]*"', "`"version`": `"$NewVersion`""
        Set-Content $tauriConf $json -NoNewline
        Write-Host "  [ok] $tauriConf"
    }

    # 3. src-tauri/Cargo.toml  (only the [package] version, first match)
    $cargoToml = "src-tauri\Cargo.toml"
    if (Test-Path $cargoToml) {
        $lines = Get-Content $cargoToml
        $patched = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if (-not $patched -and $lines[$i] -match '^version\s*=\s*"') {
                $lines[$i] = "version = `"$NewVersion`""
                $patched = $true
            }
        }
        Set-Content $cargoToml $lines
        Write-Host "  [ok] $cargoToml"
    }

    # 4. pyproject.toml
    $pyproject = "pyproject.toml"
    if (Test-Path $pyproject) {
        $lines = Get-Content $pyproject
        $patched = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if (-not $patched -and $lines[$i] -match '^version\s*=\s*"') {
                $lines[$i] = "version = `"$NewVersion`""
                $patched = $true
            }
        }
        Set-Content $pyproject $lines
        Write-Host "  [ok] $pyproject"
    }

    # 5. hexnode/__init__.py
    $hexInit = "hexnode\__init__.py"
    if (Test-Path $hexInit) {
        $content = Get-Content $hexInit -Raw
        $content = $content -replace '__version__\s*=\s*"[^"]*"', "__version__ = `"$NewVersion`""
        Set-Content $hexInit $content -NoNewline
        Write-Host "  [ok] $hexInit"
    }

    # 6. hexnode/api/main.py  (FastAPI version kwarg)
    $mainPy = "hexnode\api\main.py"
    if (Test-Path $mainPy) {
        $content = Get-Content $mainPy -Raw
        $content = $content -replace 'version\s*=\s*"[0-9][^"]*"', "version=`"$NewVersion`""
        Set-Content $mainPy $content -NoNewline
        Write-Host "  [ok] $mainPy"
    }

    # 7. web/package.json
    $webPkg = "web\package.json"
    if (Test-Path $webPkg) {
        $json = Get-Content $webPkg -Raw
        $json = $json -replace '"version"\s*:\s*"[^"]*"', "`"version`": `"$NewVersion`""
        Set-Content $webPkg $json -NoNewline
        Write-Host "  [ok] $webPkg"
    }

    # 8. README.md  (installer filename references)
    $readme = "README.md"
    if (Test-Path $readme) {
        $content = Get-Content $readme -Raw
        $content = $content -replace 'Paradox Solutions LLM_[\d.]+_', "Paradox Solutions LLM_${NewVersion}_"
        Set-Content $readme $content -NoNewline
        Write-Host "  [ok] $readme (installer filenames)"
    }

    # 9. doc/README.md  (What's New heading)
    $docReadme = "doc\README.md"
    if (Test-Path $docReadme) {
        $content = Get-Content $docReadme -Raw
        $content = $content -replace "What's New \(v[\d.]+\+?\)", "What's New (v$NewVersion)"
        Set-Content $docReadme $content -NoNewline
        Write-Host "  [ok] $docReadme (heading)"
    }

    Write-Host ""
    Write-Host "=== All files bumped to $NewVersion ===" -ForegroundColor Green
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Update CHANGELOG.md with release notes for $NewVersion"
    Write-Host "  2. Commit:  git add -A && git commit -m 'Bump version to $NewVersion'"
    Write-Host "  3. Tag:     git tag v$NewVersion"
    Write-Host "  4. Build:   .\scripts\build_release.ps1"
}
finally {
    Pop-Location
}
