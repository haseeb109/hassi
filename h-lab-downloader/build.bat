@echo off
REM Builds dist\HLabDownloader\HLabDownloader.exe (with ffmpeg + deno bundled)
cd /d "%~dp0"
if not exist .venv ( py -m venv .venv )
call .venv\Scripts\activate
pip install -q -U -r requirements.txt pyinstaller

pyinstaller --noconfirm --clean --windowed --name HLabDownloader ^
  --collect-all customtkinter --collect-all yt_dlp --collect-all yt_dlp_ejs ^
  --icon assets/icon.ico --add-data "assets;assets" h_lab_downloader.py

REM Bundle ffmpeg.exe and deno.exe if they are in this folder
if exist ffmpeg.exe copy /y ffmpeg.exe dist\HLabDownloader\
if exist deno.exe copy /y deno.exe dist\HLabDownloader\
echo.
echo Done: dist\HLabDownloader\HLabDownloader.exe
pause
