@echo off
chcp 65001 >nul
title 每日看板
cd /d %~dp0
set PYTHONUNBUFFERED=1
python server.py
pause
