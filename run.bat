@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   더필 사내 인트라넷 서버
echo ============================================
echo.
where python >nul 2>nul || (echo [오류] Python이 설치되어 있지 않습니다. & pause & exit /b)
pip show flask >nul 2>nul || (echo Flask 설치 중... & pip install flask)
echo 서버 시작: http://127.0.0.1:5000
echo (종료하려면 이 창에서 Ctrl+C)
echo.
start "" http://127.0.0.1:5000
python app.py
pause
