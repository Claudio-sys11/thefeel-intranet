@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   더필코리아 인트라넷 - 빌드 (앱 + 설치파일)
echo ============================================
echo.

REM 0) 의존성 확인
pip show pyinstaller >nul 2>nul || (echo PyInstaller 설치 중... & pip install pyinstaller)
pip show pywebview  >nul 2>nul || (echo pywebview 설치 중... & pip install pywebview)
pip show pillow     >nul 2>nul || (echo Pillow 설치 중... & pip install pillow)

REM 1) 로고/아이콘 생성
echo [1/4] 로고/아이콘 생성...
python make_icon.py || goto :err

REM 2) 버전 정보 → version.iss 생성 (Inno Setup 용)
echo [2/4] 버전 정보 생성...
python -c "import version;open('version.iss','w',encoding='utf-8').write('#define MyAppVersion \"%s\"\n'%version.__version__)" || goto :err
for /f "tokens=2 delims== " %%v in ('python -c "import version;print(version.__version__)"') do set VER=%%v

REM 3) 데스크톱 앱 exe 빌드 (창 모드, 콘솔 없음)
echo [3/5] 앱 exe 빌드...
pyinstaller --noconfirm --onefile --windowed --name ThefeelIntranet --icon app.ico ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "schema.sql;." ^
  --collect-all webview ^
  desktop.py || goto :err

REM 4) 앱 exe 코드서명
echo [4/5] 앱 exe 코드서명...
powershell -ExecutionPolicy Bypass -File sign.ps1 "dist\ThefeelIntranet.exe" || goto :err

REM 5) 설치파일 빌드 후 코드서명
echo [5/5] 설치파일 빌드 + 서명...
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
%ISCC% installer.iss || goto :err
for %%f in ("installer_out\*.exe") do powershell -ExecutionPolicy Bypass -File sign.ps1 "%%f" || goto :err

echo.
echo [완료] installer_out\ 폴더의 서명된 설치파일을 배포하세요.
echo  사내 PC에는 dist_cert\사내PC_인증서신뢰등록.bat 를 1회 실행(관리자)하세요.
dir /b installer_out\*.exe
pause
exit /b 0

:err
echo.
echo [실패] 빌드 중 오류가 발생했습니다. 위 로그를 확인하세요.
pause
exit /b 1
