@echo off
REM Copyright (C) 2026 EEG Paradox Solutions LLM contributors
REM SPDX-License-Identifier: GPL-3.0-or-later
REM FastAPI only on port 8765 (no Next.js, no Ollama check). Use for debugging or Tauri sidecar tests.
title Paradox API
cd /d "%~dp0."
if not exist ".venv\Scripts\python.exe" (
    echo No .venv found. Run:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
    pause
    exit /b 1
)
echo.
echo Paradox API  http://127.0.0.1:8765  ^|  /docs  ^|  /health
echo Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" run_server.py
if errorlevel 1 pause
