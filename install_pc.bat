@echo off
setlocal
title Qwen PC Demo Installer
cd /d "%~dp0"

echo Qwen PC Demo installer
echo.

where python >nul 2>nul
if errorlevel 1 goto INSTALL_PYTHON

python --version
echo Installing Python packages...
python -m pip install --upgrade pip --disable-pip-version-check
if errorlevel 1 echo Warning: pip upgrade failed, continuing with the existing pip.

rem Try the official PyPI first, then a mirror if the network is unavailable.
python -m pip install -r requirements.txt --disable-pip-version-check --default-timeout=30 --index-url https://pypi.org/simple
if not errorlevel 1 goto INSTALL_OK
echo Official PyPI failed. Trying the Aliyun mirror...
python -m pip install -r requirements.txt --disable-pip-version-check --default-timeout=30 --index-url https://mirrors.aliyun.com/pypi/simple/
if errorlevel 1 goto INSTALL_FAILED

:INSTALL_OK

>"run_pc_demo.bat" echo @echo off
>>"run_pc_demo.bat" echo cd /d "%%~dp0"
>>"run_pc_demo.bat" echo python qwen_chat_gui_final.py
>>"run_pc_demo.bat" echo pause

echo Installation complete.
echo Double-click run_pc_demo.bat to start.
pause
exit /b 0

:INSTALL_PYTHON
echo Python was not found. Trying to install Python 3.10 with winget...
where winget >nul 2>nul
if errorlevel 1 goto NO_PYTHON
winget install --id Python.Python.3.10 --exact --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto NO_PYTHON
echo Python installation finished.
echo Please close this window and run install_pc.bat again.
pause
exit /b 0

:NO_PYTHON
echo Automatic Python installation was unavailable.
echo Install Python 3.10 or newer and enable Add Python to PATH.
pause
exit /b 1

:INSTALL_FAILED
echo.
echo Package installation failed.
echo Please check the Internet connection, then run this file again.
echo If it still fails, copy the error lines above.
pause
exit /b 1

