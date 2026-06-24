# The Feel Intranet

Flask + SQLite 기반 사내 업무 포털. **로그인 / 공지사항 / 전자결재 / 사내메일 / 연차관리** 기능을 제공하며,
**Windows 데스크톱 앱**(네이티브 창, pywebview)으로 동작하고 **설치형 .exe**로 배포되며 GitHub 릴리스로 자동 업데이트됩니다.

## 설치 / 실행 (사용자)
> **직접 다운로드(.exe)**: https://github.com/Claudio-sys11/thefeel-intranet/releases/latest 에서 .exe 자산 클릭


1. [최신 릴리스](https://github.com/Claudio-sys11/thefeel-intranet/releases/latest)에서 **`The Feel Intranet-Setup-v{버전}.exe`** 다운로드
2. 설치파일 실행 → 자동 설치 후 **바탕화면 바로가기** 생성, 프로그램이 창으로 실행됨
   - 설치 위치: `%LOCALAPPDATA%\Programs\ThefeelIntranet`
3. 최초 로그인: **`THEFEELKOREA` / `231900`** → 로그인 후 비밀번호 변경 권장
4. `직원관리` 메뉴에서 직원 계정 추가

> **같은 사내망 다른 PC에서 접속**: 별도 설치 없이 브라우저로 서버 PC IP 접속 (예: `http://192.168.0.74:5000`).
> 서버 PC의 Windows 방화벽에서 **5000 포트 인바운드 허용** 필요.
> 데이터(`intranet.db`)는 설치 폴더와 분리된 `%LOCALAPPDATA%\ThefeelIntranet`에 저장되어 **업데이트·재설치에도 보존**됩니다.

## 코드서명 / SmartScreen 경고 줄이기

설치파일과 앱은 자체 코드서명 인증서(**THE FEEL KOREA**)로 서명되어 있습니다.
사내 PC에서 **"알 수 없는 게시자" 경고를 없애려면** 인증서를 1회 신뢰 등록하세요.

1. 릴리스의 **`TheFeelKorea-CertTrust.zip`** 다운로드 후 압축 해제
2. 안의 **`사내PC_인증서신뢰등록.bat`** 을 **관리자 권한으로 실행** (우클릭 → 관리자 권한으로 실행)
3. 이후 설치 시 게시자가 **THE FEEL KOREA**로 표시됩니다.

> 참고: 자체서명 인증서는 Microsoft 클라우드 평판이 없어, 인터넷에서 막 받은 파일은
> SmartScreen "Windows가 PC를 보호했습니다" 평판 경고가 한 번 뜰 수 있습니다.
> 이때는 **추가 정보 → 실행**을 누르거나, 받은 파일을 **우클릭 → 속성 → '차단 해제' 체크** 후 실행하세요.
> 완전 무경고는 유료 EV 코드서명 인증서가 필요합니다.

## 자동 업데이트

- 프로그램 시작 시 GitHub 릴리스를 확인해 새 버전이 있으면 상단에 알림 배너 표시.
- `업데이트` 화면에서 **관리자**가 「자동 업데이트 (설치 후 재시작)」 클릭 → 새 설치파일을 받아 **사일런트 설치**(이전 버전 자동 제거) 후 새 버전이 자동 실행됨.
- 수동 설치도 가능: 새 설치파일을 받아 실행하면 동일하게 업그레이드됩니다(데이터 유지).

## 기능

| 메뉴 | 설명 |
|------|------|
| **전자결재** | 일반품의·지출결의·구매요청·휴가신청, 다단계 결재선, 순차 승인·반려, 회수, 결재 이력 |
| **사내메일** | 다중 수신자, 받은/보낸함, 읽음 표시, 삭제 |
| **연차관리** | 연간 부여·사용·잔여 자동 계산, 휴가신청 결재 연동(최종 승인 시 자동 차감), 부서 휴가현황 |
| **직원관리**(관리자) | 직원 추가/수정, 부서·직급·입사일·연차 설정, 권한, 비밀번호 초기화 |

## 개발 / 빌드 (개발자)

```bash
pip install flask pywebview pyinstaller pillow   # Inno Setup 6 별도 설치 필요
python desktop.py      # 데스크톱 앱 개발 실행 (네이티브 창)
python app.py          # 브라우저 개발 실행 (http://127.0.0.1:5000)
build.bat              # 로고 생성 → 앱 exe → 설치파일까지 일괄 빌드
```

### 새 버전 배포 절차
1. `version.py`의 `__version__` 올리기 (예: 1.0.2 → 1.0.3)
2. `build.bat` 실행 → `installer_out\ThefeelIntranet-Setup-1.0.3.exe` 생성
3. 릴리스 업로드(파일명에 버전 포함):
   ```bash
   gh release create v1.0.3 installer_out/ThefeelIntranet-Setup-1.0.3.exe --title "v1.0.3" --notes "변경 내용"
   ```
   → 실행 중인 모든 클라이언트가 다음 시작 때 업데이트 알림을 받음.

## 파일 구조

```
Intranet/
├── desktop.py      # 데스크톱 앱 진입점 (pywebview 창 + Flask 서버)
├── app.py          # 웹 애플리케이션 (라우트·로직)
├── version.py      # 버전·저장소 정보 (릴리스마다 수정)
├── updater.py      # GitHub 릴리스 자동 업데이트(설치파일 사일런트 설치)
├── make_icon.py    # 로고/아이콘(SVG·PNG·ICO) 생성
├── schema.sql      # DB 스키마
├── installer.iss   # Inno Setup 설치 스크립트
├── templates/      # 화면(Jinja2)
├── static/         # CSS, 로고
├── build.bat       # 일괄 빌드(앱 exe + 설치파일)
└── run.bat         # 개발용 실행
```

> 운영 데이터는 `%LOCALAPPDATA%\ThefeelIntranet\intranet.db` 한 파일에 저장됩니다. 정기 백업하세요.
> `intranet.db`, `secret.key`는 저장소에 올리지 않습니다(.gitignore).
