@echo off
rem Double-click to start the SMA Trader web app. First run installs everything.
cd /d "%~dp0"
if not exist .venv (
    echo Setting up for the first time...
    python -m venv .venv || goto :error
    .venv\Scripts\python -m pip install -r requirements.txt || goto :error
)
.venv\Scripts\python -m streamlit run app.py
goto :eof
:error
echo Setup failed. Is Python 3.9+ installed and on PATH?
pause
