@echo off
cd /d "%~dp0"
title Gupta Creations - Salary App
echo ============================================================
echo    GUPTA CREATIONS - SALARY APP
echo ------------------------------------------------------------
echo    Starting... a browser tab will open in a few seconds.
echo    Login:  admin  /  gupta123   (change before sharing)
echo.
echo    To use on your phone / another counter (same WiFi):
echo    open  http://YOUR-PC-IP:8501  on that device.
echo.
echo    To STOP the app: just close this black window.
echo ============================================================
echo.
.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless false
pause
