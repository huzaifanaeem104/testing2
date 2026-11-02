@echo off
setlocal
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Right-click this file and choose Run as administrator.
    pause
    exit /b 1
)

set "QZDIR=C:\Program Files\QZ Tray"
if not exist "%QZDIR%" set "QZDIR=C:\Program Files (x86)\QZ Tray"
if not exist "%QZDIR%" (
    echo Install QZ Tray first: https://qz.io/download/
    start https://qz.io/download/
    pause
    exit /b 1
)

set "SRC=%~dp0override.crt"
if not exist "%SRC%" (
    echo override.crt is missing. Put it in the same folder as this script.
    pause
    exit /b 1
)

copy /Y "%SRC%" "%QZDIR%\override.crt" >nul
echo Trusted Odoo for silent print: %QZDIR%\override.crt
echo.
echo Close QZ Tray from the system tray, then start QZ Tray again.
echo After that, Print PDF in Odoo goes to this PC's default printer.
echo No Allow box. No printer picker.
pause
