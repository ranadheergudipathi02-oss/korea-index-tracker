@echo off
REM Daily runner for the Static Korea Index Tracker (invoked by Task Scheduler).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo ===== %DATE% %TIME% ===== >> "data\_dailyrun.log"
python run_daily.py >> "data\_dailyrun.log" 2>&1
