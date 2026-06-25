@echo off
chcp 949 >nul
title The Feel Intranet - 서버 PC 방화벽 허용
net session >nul 2>&1
if errorlevel 1 (
  echo 관리자 권한이 필요합니다. 잠시 후 뜨는 창에서 "예"를 눌러주세요...
  powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo ============================================================
echo    서버(관리자) PC 방화벽에서 5000 포트 인바운드 허용
echo    직원 PC가 이 서버에 접속할 수 있게 합니다.
echo ============================================================
echo.
netsh advfirewall firewall delete rule name="The Feel Intranet 5000" >nul 2>&1
netsh advfirewall firewall add rule name="The Feel Intranet 5000" dir=in action=allow protocol=TCP localport=5000 profile=any >nul
if errorlevel 1 (
  echo [실패] 방화벽 규칙 추가에 실패했습니다.
  pause
  exit /b 1
)
echo [완료] 5000 포트 인바운드가 허용되었습니다.
echo.
echo  이 서버 PC의 IP 주소(직원에게 알려줄 주소):
ipconfig | findstr /c:"IPv4"
echo.
echo  * The Feel Intranet 앱이 이 PC에서 실행(서버 모드) 중이어야
echo    직원 PC가 접속할 수 있습니다.
echo.
pause
