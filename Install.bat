@echo off
rem Double-click this file to install/update Python (per-user, only if
rem Python 3.10+ is missing), the project dependencies, and create a
rem desktop shortcut, via a small window (install.ps1).
where powershell.exe >nul 2>&1
if errorlevel 1 (
    echo Windows PowerShell ^(powershell.exe^) was not found on this computer.
    echo It is required to run the setup window ^(install.ps1^).
    pause
    exit /b 1
)
if not exist "%~dp0install.ps1" (
    echo install.ps1 was not found next to Install.bat:
    echo %~dp0install.ps1
    pause
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
    echo.
    echo The setup window ended with an error ^(exit code %errorlevel%^).
    pause
    exit /b %errorlevel%
)
