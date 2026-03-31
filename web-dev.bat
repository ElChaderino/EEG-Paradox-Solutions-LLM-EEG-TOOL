@echo off
REM Copyright (C) 2026 EEG Paradox Solutions LLM contributors
REM SPDX-License-Identifier: GPL-3.0-or-later
REM Next.js UI only (port 3000). API must be running separately (launch.bat or run_server.py).
REM Uses repo root package.json so paths with spaces are handled via npm --prefix.
title Paradox WEB
cd /d "%~dp0."
call npm run dev
