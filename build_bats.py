# -*- coding: utf-8 -*-
"""도구용 .bat 파일을 CP949(한글 Windows ANSI)로 기록 — cmd 한글 깨짐 방지."""
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist_cert")

FIREWALL = """@echo off
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
echo [완료] 5000 포트(TCP) 인바운드가 허용되었습니다.
REM 서버 자동 검색용 UDP 50505 (직원 PC가 서버를 자동으로 찾게 함)
netsh advfirewall firewall delete rule name="The Feel Intranet Discovery 50505" >nul 2>&1
netsh advfirewall firewall add rule name="The Feel Intranet Discovery 50505" dir=in action=allow protocol=UDP localport=50505 profile=any >nul
echo [완료] 50505 포트(UDP, 자동 검색) 인바운드가 허용되었습니다.
echo.
echo  이 서버 PC의 IP 주소(직원에게 알려줄 주소):
ipconfig | findstr /c:"IPv4"
echo.
echo  * The Feel Intranet 앱이 이 PC에서 실행(서버 모드) 중이어야
echo    직원 PC가 접속할 수 있습니다.
echo.
pause
"""

CERT = """@echo off
chcp 949 >nul
title The Feel Intranet - 인증서 신뢰 등록
net session >nul 2>&1
if errorlevel 1 (
  echo 관리자 권한이 필요합니다. 잠시 후 뜨는 창에서 "예"를 눌러주세요...
  powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo ============================================================
echo    The Feel Intranet  코드서명 인증서 신뢰 등록
echo    (회사 PC에서 1회만 실행)
echo ============================================================
echo.
set CER=%~dp0TheFeelKorea-CodeSign.cer
if not exist "%CER%" (
  echo [오류] TheFeelKorea-CodeSign.cer 파일이 같은 폴더에 없습니다.
  pause
  exit /b 1
)
echo 신뢰할 수 있는 루트 인증 기관에 등록 중...
certutil -addstore -f Root "%CER%" >nul
echo 신뢰할 수 있는 게시자에 등록 중...
certutil -addstore -f TrustedPublisher "%CER%" >nul
echo.
echo [완료] 인증서가 신뢰 등록되었습니다.
echo  이제 The Feel Intranet 설치 시 "알 수 없는 게시자" 경고가 사라집니다.
echo.
pause
"""

def w(name, text):
    p = os.path.join(HERE, name)
    # CRLF + CP949 로 기록 (배치파일 표준)
    data = text.replace("\n", "\r\n").encode("cp949")
    with open(p, "wb") as f:
        f.write(data)
    print("wrote", name, len(data), "bytes (cp949)")

w("서버PC_방화벽허용.bat", FIREWALL)
w("사내PC_인증서신뢰등록.bat", CERT)
print("done")
