@echo off
title Cinstalimi i Renditesit te Fotove
rem Cinstalon Renditesin e Fotove (kliko dy here, ose nga "Aplikacionet e instaluara" te Windows-it).
rem Skripti kopjohet te TEMP, qe dosja e programit te mund te fshihet nderkohe qe punon.
copy /y "%~dp0cinstalo.ps1" "%TEMP%\renditesi_cinstalo.ps1" >nul
cd /d "%TEMP%" & powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\renditesi_cinstalo.ps1" %* & echo. & pause & exit /b
