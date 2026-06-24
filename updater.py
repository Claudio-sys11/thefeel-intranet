# -*- coding: utf-8 -*-
"""GitHub 릴리스 기반 자동 업데이트 확인/적용"""
import json
import os
import sys
import urllib.request

from version import __version__, GITHUB_OWNER, GITHUB_REPO, ASSET_NAME

API_LATEST = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# 백그라운드 확인 결과 캐시 (None = 최신 / dict = 새 버전 있음)
UPDATE_INFO = None
UPDATE_CHECKED = False                       # 최신버전 확인 완료 여부
# 업데이트 진행 상태 (상태바 % 표시용)
PROGRESS = {"state": "idle", "percent": 0, "message": ""}


def _vt(s):
    """'1.2.3' -> (1,2,3) 비교용"""
    parts = []
    for x in (s or "").lstrip("vV").split("."):
        try:
            parts.append(int(x))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def check_update(timeout=5):
    """새 버전이 있으면 dict 반환, 없거나 실패하면 None"""
    try:
        req = urllib.request.Request(
            API_LATEST,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "thefeel-intranet"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except Exception:
        return None
    latest = (data.get("tag_name") or "").lstrip("vV")
    if not latest or _vt(latest) <= _vt(__version__):
        return None
    # 설치파일(Setup) 자산 우선, 없으면 임의의 .exe
    assets = data.get("assets", [])
    download = None
    for a in assets:
        if a.get("name", "").lower().endswith(".exe") and "setup" in a.get("name", "").lower():
            download = a.get("browser_download_url")
            break
    if not download:
        for a in assets:
            if a.get("name", "").endswith(".exe"):
                download = a.get("browser_download_url")
                break
    return {
        "latest": latest,
        "current": __version__,
        "page": data.get("html_url"),
        "download": download or data.get("html_url"),
        "notes": (data.get("body") or "").strip(),
    }


def check_async():
    """백그라운드 스레드에서 확인하여 UPDATE_INFO 갱신"""
    import threading

    def _run():
        global UPDATE_INFO, UPDATE_CHECKED
        UPDATE_INFO = check_update()
        UPDATE_CHECKED = True

    threading.Thread(target=_run, daemon=True).start()


def start_apply(download_url):
    """업데이트 적용을 백그라운드로 시작 (즉시 반환). PROGRESS 로 진행률 추적."""
    import threading
    threading.Thread(target=_do_apply, args=(download_url,), daemon=True).start()


def _do_apply(download_url):
    """설치파일을 진행률과 함께 내려받아 사일런트 설치 → 이전 버전 제거·업그레이드 후 재실행."""
    global PROGRESS
    if not getattr(sys, "frozen", False):
        PROGRESS = {"state": "error", "percent": 0, "message": "개발 모드에서는 자동 적용을 지원하지 않습니다."}
        return
    import tempfile
    import subprocess
    import time

    setup = os.path.join(tempfile.gettempdir(), "TheFeelIntranet-Setup.exe")
    try:
        PROGRESS = {"state": "downloading", "percent": 0, "message": "새 버전 다운로드 중"}
        req = urllib.request.Request(download_url, headers={"User-Agent": "thefeel-intranet"})
        with urllib.request.urlopen(req, timeout=180) as r, open(setup, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                pct = int(got * 100 / total) if total else 0
                PROGRESS = {"state": "downloading", "percent": pct, "message": "새 버전 다운로드 중"}
        PROGRESS = {"state": "installing", "percent": 100, "message": "설치 중 · 곧 재시작됩니다"}
        time.sleep(1.0)  # 상태바가 100%/설치중을 표시할 시간
        # 실행 중인 exe(onefile 부트로더 포함)가 완전히 종료된 뒤 설치해야 교체가 됨.
        # Windows 작업 스케줄러로 설치를 위임 → 앱 프로세스 트리와 완전히 분리되어
        # 앱이 종료돼도 설치가 끝까지 진행됨(동일 AppId: 이전 버전 제거 후 [Run] 재실행).
        CNW = 0x08000000  # CREATE_NO_WINDOW
        task = "TheFeelIntranetUpdate"
        action = (f'cmd /c ping 127.0.0.1 -n 4 >nul & '
                  f'"{setup}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART & '
                  f'schtasks /delete /tn {task} /f')
        subprocess.run(["schtasks", "/create", "/tn", task, "/sc", "once", "/st", "00:00",
                        "/tr", action, "/f"], creationflags=CNW)
        subprocess.run(["schtasks", "/run", "/tn", task], creationflags=CNW)
        time.sleep(1.0)
        os._exit(0)
    except Exception as e:
        PROGRESS = {"state": "error", "percent": 0, "message": f"업데이트 실패: {e}"}
