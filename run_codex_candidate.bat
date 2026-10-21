@echo off
setlocal
cd /d "%~dp0"
set "AI_PROVIDER=codex_cli"
uv run app.py rebalance --dry-run=true --adaptive
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
