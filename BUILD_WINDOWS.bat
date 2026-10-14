@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=py -3"
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher not found. Install Python 3.12 or 3.13 from python.org and retry.
  pause
  exit /b 1
)
if exist ".venv\Scripts\python.exe" goto venv_ok
%PYTHON% -m venv .venv
if errorlevel 1 goto fail
:venv_ok
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto fail
python -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo.
echo Running unit tests (no SMS sending)...
python -m unittest discover -s tests -p test_*.py -v
if errorlevel 1 goto fail
echo.
echo Running OFFSCREEN UI smoke test...
python tests\gui_smoke.py
if errorlevel 1 goto fail
echo.
echo Building Windows executable...
python -m PyInstaller --clean --noconfirm --onedir --windowed --name SMSGateDeskCommunity --icon "assets\SMSGateDesk.ico" --add-data "assets\SMSGateDesk.ico;assets" --add-data "assets\SMSGateDesk.png;assets" app.py
if errorlevel 1 goto fail
echo.
echo Verifying Windows Credential Manager FROM BUILT EXE...
start "" /wait "dist\SMSGateDeskCommunity\SMSGateDeskCommunity.exe" --credential-self-test
if errorlevel 1 goto fail
echo.
echo SUCCESS: %CD%\dist\SMSGateDeskCommunity\SMSGateDeskCommunity.exe
echo Password storage self-test passed, no SMS sent.
echo Distribute the ENTIRE dist\SMSGateDeskCommunity folder, not the EXE alone.
pause
exit /b 0
:fail
echo.
echo TEST OR BUILD FAILED. Do not replace your previous executable.
echo Check %%LOCALAPPDATA%%\SMSGateDeskCommunity\smsgate.log if credential self-test failed.
pause
exit /b 1
