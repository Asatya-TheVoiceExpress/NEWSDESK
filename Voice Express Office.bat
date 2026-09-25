@echo off
cd /d "%~dp0"
where pythonw >nul 2>&1 && (start "" pythonw "voice_express_office.py") || (start "" python "voice_express_office.py")
