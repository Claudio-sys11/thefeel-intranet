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
echo [3/4] 앱 exe 빌드...
pyinstaller --noconfirm --onefile --windowed --name ThefeelIntranet --icon app.ico ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "schema.sql;." ^
  --collect-all webview ^
  desktop.py || goto :err

REM 4) 설치파일 빌드 (Inno Setup)
echo [4/4] 설치파일 빌드...
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
%ISCC% installer.iss || goto :err

echo.
echo [완료] installer_out\ 폴더의 ThefeelIntranet-Setup-*.exe 를 배포하세요.
dir /b installer_out\*.exe
pause
exit /b 0

:err
echo.
echo [실패] 빌드 중 오류가 발생했습니다. 위 로그를 확인하세요.
pause
exit /b 1
