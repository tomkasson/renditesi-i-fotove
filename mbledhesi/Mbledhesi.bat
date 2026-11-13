@echo off
title Mbledhesi i fotove
rem Hap mbledhesin (PowerShell 2.0 i Windows 7, pa instalim). Kopjo kete dosje ne USB dhe kliko dy here kete skedar.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mbledhesi.ps1"
echo.
pause
