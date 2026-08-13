@echo off
chcp 65001 >nul
echo ========================================
echo  GCP ADC re-login (required once)
echo  Project: moveai-504907
echo ========================================
echo.
echo 1) Install Google Cloud SDK if missing:
echo    https://cloud.google.com/sdk/docs/install
echo 2) This script opens browser login.
echo.

where gcloud >nul 2>&1
if errorlevel 1 (
  echo [ERROR] gcloud not found in PATH.
  echo Install Cloud SDK, open a NEW terminal, then run this again.
  pause
  exit /b 1
)

gcloud auth application-default login
gcloud auth application-default set-quota-project moveai-504907
gcloud config set project moveai-504907

echo.
echo Done. Now run start-proxy.bat and connect Cursor.
pause
