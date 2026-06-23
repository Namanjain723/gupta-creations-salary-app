@echo off
cd /d "%~dp0"
title Backup Salary Data
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set STAMP=%%i
set DEST=Backups\backup_%STAMP%
echo Backing up your salary data to:  %DEST%
robocopy local_db "%DEST%\local_db" /E >nul
if exist secrets robocopy secrets "%DEST%\secrets" /E >nul
echo.
echo Done. All your salary data is copied to the "Backups" folder.
echo Tip: copy the "Backups" folder to a pen-drive / external disk for safety.
echo.
pause
