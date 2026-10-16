#!/bin/sh
# Start the SMA Trader web app. First run installs everything.
cd "$(dirname "$0")" || exit 1
if [ ! -d .venv ]; then
    echo "Setting up for the first time..."
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt || exit 1
fi
exec .venv/bin/python -m streamlit run app.py
