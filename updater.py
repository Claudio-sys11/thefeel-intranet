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
        global UPDATE_INFO
        UPDATE_INFO = check_update()

    threading.Thread(target=_run, daemon=True).start()


def apply_update(download_url):
    """새 설치파일(Setup.exe)을 받아 사일런트로 실행 → 이전 버전 자동 제거·업그레이드
    후 앱을 재실행한다. 성공 시 현재 프로세스를 종료한다(반환 없음)."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("개발 모드에서는 자동 적용을 지원하지 않습니다.")
    import tempfile
    import subprocess

    setup = os.path.join(tempfile.gettempdir(), "ThefeelIntranet-Setup.exe")
    req = urllib.request.Request(download_url, headers={"User-Agent": "thefeel-intranet"})
    with urllib.request.urlopen(req, timeout=180) as r, open(setup, "wb") as f:
        f.write(r.read())

    # /VERYSILENT       : 무인 설치 (창 없음)
    # /SUPPRESSMSGBOXES : 확인창 생략
    # /CLOSEAPPLICATIONS: 실행 중인 앱을 닫고 진행
    # 동일 AppId 이므로 이전 버전을 제거하고 같은 위치에 덮어쓴다.
    # 설치 후 [Run] postinstall 로 새 버전이 자동 실행된다.
    subprocess.Popen(
        [setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/NORESTART"],
        close_fds=True,
    )
    os._exit(0)
