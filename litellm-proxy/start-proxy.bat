@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  LiteLLM Proxy (Vertex AI / Free Credit)
echo  Project: moveai-504907
echo  URL: http://localhost:4000/v1
echo ========================================
echo.
echo Cursor 설정:
echo   OpenAI API Key: sk-moveai-local
echo   Override OpenAI Base URL: http://localhost:4000/v1
echo   Models: gemini-2.5-flash / gemini-1.5-flash / gemini-2.0-flash
echo.
echo 이 창을 닫으면 Cursor 연동이 끊깁니다.
echo ========================================
echo.

set GOOGLE_CLOUD_PROJECT=moveai-504907
set VERTEXAI_PROJECT=moveai-504907
set VERTEXAI_LOCATION=us-central1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PATH=%APPDATA%\Python\Python312\Scripts;%PATH%

"%APPDATA%\Python\Python312\Scripts\litellm.exe" --config "%~dp0config.yaml" --port 4000 --host 127.0.0.1
if errorlevel 1 (
  echo.
  echo litellm 실행 실패. pip install "litellm[proxy]" 후 다시 시도하세요.
)
pause
