@echo off
cd /d "%~dp0"
echo Building DarktideModManager.exe ...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name DarktideModManager --icon app.ico --version-file version_info.txt --add-data "static;static" --add-data "dmf_payload;dmf_payload" --collect-all webview app.py
echo.
echo Done. Output: dist\DarktideModManager.exe
pause
