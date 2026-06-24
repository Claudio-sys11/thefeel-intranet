@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   더필 인트라넷 - exe 빌드
echo ============================================
echo.
pip show pyinstaller >nul 2>nul || (echo PyInstaller 설치 중... & pip install pyinstaller)

echo 빌드 시작...
pyinstaller --noconfirm --onefile --console --name ThefeelIntranet ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "schema.sql;." ^
  app.py

if exist "dist\ThefeelIntranet.exe" (
  echo.
  echo [완료] dist\ThefeelIntranet.exe 생성됨
) else (
  echo [실패] 빌드에 실패했습니다. 위 로그를 확인하세요.
)
pause
