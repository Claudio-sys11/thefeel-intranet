@echo off
chcp 65001 >nul
title The Feel Intranet - 인증서 신뢰 등록
echo ============================================================
echo   The Feel Intranet  코드서명 인증서 신뢰 등록
echo   (회사 PC에서 1회만 관리자 권한으로 실행)
echo ============================================================
echo.
net session >nul 2>&1
if errorlevel 1 (
  echo [오류] 관리자 권한이 필요합니다.
  echo  이 파일을 마우스 오른쪽 클릭 → "관리자 권한으로 실행" 하세요.
  echo.
  pause
  exit /b 1
)
set CER=%~dp0TheFeelKorea-CodeSign.cer
if not exist "%CER%" (
  echo [오류] TheFeelKorea-CodeSign.cer 파일이 같은 폴더에 없습니다.
  pause & exit /b 1
)
echo 신뢰할 수 있는 루트 인증 기관에 등록 중...
certutil -addstore -f Root "%CER%" >nul
echo 신뢰할 수 있는 게시자에 등록 중...
certutil -addstore -f TrustedPublisher "%CER%" >nul
echo.
echo [완료] 인증서가 신뢰 등록되었습니다.
echo  이제 The Feel Intranet 설치 시 게시자가 'THE FEEL KOREA'로 표시되고
echo  "알 수 없는 게시자" 경고가 사라집니다.
echo.
pause
