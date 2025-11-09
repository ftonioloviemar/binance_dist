@echo off
cd /d %~dp0
uv run app.py rebalance --dry-run=false %*
