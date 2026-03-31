@echo off
REM Copyright (C) 2026 EEG Paradox Solutions LLM contributors
REM SPDX-License-Identifier: GPL-3.0-or-later
REM Paradox Solutions LLM — Ollama + API (8765) + Next.js (3000)
REM Pass-through:  launch.bat -Reinstall   launch.bat -NoBrowser   launch.bat -SkipOllama
REM Manual API only:  .venv\Scripts\python.exe run_server.py   (from this folder)
REM Manual UI:         cd web ^&^& npm run dev
title Paradox Solutions LLM
REM Trailing "cd ...\" breaks quoted paths in cmd; use "%~dp0." so the final quote is not escaped.
cd /d "%~dp0."
echo.
echo Starting Paradox launcher (PowerShell)...
echo.
powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1" %*
