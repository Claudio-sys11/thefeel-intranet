# 더필 사내 인트라넷

Flask + SQLite 기반 사내 업무 포털. **로그인 / 전자결재 / 사내메일 / 연차관리** 기능을 제공하며,
Windows용 단일 실행 파일(.exe)로 배포되고 GitHub 릴리스로 자동 업데이트됩니다.

## 설치 / 실행 (사용자)

1. [최신 릴리스](https://github.com/Claudio-sys11/thefeel-intranet/releases/latest)에서 **`ThefeelIntranet.exe`** 다운로드
2. 서버로 쓸 PC의 원하는 폴더에 두고 더블클릭 → 콘솔 창이 뜨고 브라우저가 자동으로 열림
3. 최초 로그인: **`admin` / `admin1234`** → 로그인 후 비밀번호 변경 권장
4. `직원관리` 메뉴에서 직원 계정 추가

> **같은 사내망 다른 PC에서 접속**: 서버 PC IP로 접속 (예: `http://192.168.0.74:5000`).
> 서버 PC의 Windows 방화벽에서 **5000 포트 인바운드 허용** 필요.
> 종료는 콘솔 창에서 `Ctrl+C`. 데이터(`intranet.db`)는 exe와 같은 폴더에 저장됩니다.

## 자동 업데이트

- 프로그램 시작 시 GitHub 릴리스를 확인해 새 버전이 있으면 상단에 알림 배너 표시.
- `업데이트` 화면에서 **관리자**가 「자동 업데이트 적용 후 재시작」 클릭 → 새 exe를 받아 자기 자신을 교체하고 재시작.
- 수동 설치도 가능: 새 exe를 받아 기존 파일에 덮어쓰기 (데이터는 `intranet.db`에 유지됨).

## 기능

| 메뉴 | 설명 |
|------|------|
| **전자결재** | 일반품의·지출결의·구매요청·휴가신청, 다단계 결재선, 순차 승인·반려, 회수, 결재 이력 |
| **사내메일** | 다중 수신자, 받은/보낸함, 읽음 표시, 삭제 |
| **연차관리** | 연간 부여·사용·잔여 자동 계산, 휴가신청 결재 연동(최종 승인 시 자동 차감), 부서 휴가현황 |
| **직원관리**(관리자) | 직원 추가/수정, 부서·직급·입사일·연차 설정, 권한, 비밀번호 초기화 |

## 개발 / 빌드 (개발자)

```bash
pip install flask pyinstaller
python app.py          # 개발 실행 (http://127.0.0.1:5000)
build.bat              # exe 빌드 → dist\ThefeelIntranet.exe
```

### 새 버전 배포 절차
1. `version.py`의 `__version__` 올리기 (예: 1.0.0 → 1.0.1)
2. `build.bat` 실행
3. 릴리스 업로드:
   ```bash
   gh release create v1.0.1 dist/ThefeelIntranet.exe --title "v1.0.1" --notes "변경 내용"
   ```
   → 실행 중인 모든 클라이언트가 다음 시작 때 업데이트 알림을 받음.

## 파일 구조

```
Intranet/
├── app.py          # 메인 애플리케이션
├── version.py      # 버전·저장소 정보 (릴리스마다 수정)
├── updater.py      # GitHub 릴리스 자동 업데이트
├── schema.sql      # DB 스키마
├── templates/      # 화면(Jinja2)
├── static/         # CSS
├── build.bat       # exe 빌드
└── run.bat         # 개발용 실행
```

> 운영 데이터는 `intranet.db` 한 파일에 저장됩니다. 정기 백업하세요.
> `intranet.db`, `secret.key`는 저장소에 올리지 않습니다(.gitignore).
