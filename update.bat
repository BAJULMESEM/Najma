@echo off
cd /d "%~dp0"

echo.
echo ========================================
echo          NAJMA TEXT UPDATE
echo ========================================
echo.

echo [1/4] Memperbarui files.json...
python update.py

if errorlevel 1 (
    echo.
    echo ERROR: update.py gagal dijalankan.
    pause
    exit /b 1
)

echo.
echo [2/4] Menambahkan perubahan ke Git...
git add .

echo.
echo [3/4] Membuat commit...
git commit -m "Update texts"

echo.
echo [4/4] Mengirim ke GitHub...
git push

if errorlevel 1 (
    echo.
    echo ERROR: Gagal melakukan push ke GitHub.
    pause
    exit /b 1
)

echo.
echo ========================================
echo       UPDATE BERHASIL!
echo ========================================
echo.
echo GitHub sudah diperbarui.
echo GitHub Actions akan memperbarui files.json.
echo.
pause