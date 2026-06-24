@echo off
chcp 65001 >nul
title The Feel Intranet - 서버 PC 방화벽 허용
echo ============================================================
echo   서버(관리자) PC 방화벽에서 5000 포트 인바운드 허용
echo   (직원 PC가 이 서버에 접속할 수 있게 함, 관리자 1회 실행)
echo ============================================================
echo.
net session >nul 2>&1
if errorlevel 1 (
  echo [오류] 관리자 권한이 필요합니다.
  echo  이 파일을 마우스 오른쪽 클릭 - "관리자 권한으로 실행" 하세요.
  echo.
  pause & exit /b 1
)
netsh advfirewall firewall delete rule name="The Feel Intranet 5000" >nul 2>&1
netsh advfirewall firewall add rule name="The Feel Intranet 5000" dir=in action=allow protocol=TCP localport=5000 >nul
if errorlevel 1 (echo [실패] 방화벽 규칙 추가 실패 & pause & exit /b 1)
echo [완료] 5000 포트 인바운드가 허용되었습니다.
echo  직원 PC에서 The Feel Intranet 실행 후 "서버에 접속"에 이 PC의 IP를 입력하세요.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo   이 PC IP 후보:%%a
echo.
pause
