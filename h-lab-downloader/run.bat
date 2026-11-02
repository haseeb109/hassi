@echo off
REM Run H Lab Downloader from source (needs Python 3.10+ installed)
cd /d "%~dp0"
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
pip install -q -U -r requirements.txt
start "" pythonw h_lab_downloader.py
