@echo off
title TEXT-WEB UPDATE
cd /d "%~dp0"

echo.
echo ==============================
echo       TEXT-WEB UPDATE
echo ==============================
echo.

python update.py

if errorlevel 1 (
    echo.
    echo UPDATE GAGAL.
    pause
    exit /b 1
)

echo.
echo Update selesai.
echo.

REM Jika project sudah memakai Git, hapus "REM " pada tiga baris berikut:
REM git add .
REM git commit -m "Update texts"
REM git push

pause
