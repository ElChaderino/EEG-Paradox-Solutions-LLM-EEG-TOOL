@echo off
REM Copyright (C) 2026 EEG Paradox Solutions LLM contributors
REM SPDX-License-Identifier: GPL-3.0-or-later
REM Legacy alias — identical to launch.bat (points at scripts\launch.ps1)
title Paradox Solutions LLM
cd /d "%~dp0."
echo Starting Paradox launcher...
powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1" %*
