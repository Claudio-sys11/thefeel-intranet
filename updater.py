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
    download = None
    for a in data.get("assets", []):
        if a.get("name") == ASSET_NAME or a.get("name", "").endswith(".exe"):
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
    """새 exe를 받아 실행 파일을 교체하고 재시작 (frozen 전용).
    성공 시 현재 프로세스를 종료한다(반환 없음)."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("개발 모드에서는 자동 교체를 지원하지 않습니다.")
    exe_path = sys.executable
    app_dir = os.path.dirname(exe_path)
    new_exe = os.path.join(app_dir, "_update_new.exe")

    req = urllib.request.Request(download_url, headers={"User-Agent": "thefeel-intranet"})
    with urllib.request.urlopen(req, timeout=60) as r, open(new_exe, "wb") as f:
        f.write(r.read())

    bat = os.path.join(app_dir, "_apply_update.bat")
    exe_name = os.path.basename(exe_path)
    with open(bat, "w", encoding="cp949") as f:
        f.write(
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            f'move /y "{exe_name}" "_old_{exe_name}" >nul 2>nul\r\n'
            f'move /y "_update_new.exe" "{exe_name}" >nul\r\n'
            f'del /q "_old_{exe_name}" >nul 2>nul\r\n'
            f'start "" "{exe_name}"\r\n'
            'del /q "_apply_update.bat" >nul 2>nul\r\n'
        )
    import subprocess
    subprocess.Popen(["cmd", "/c", bat], cwd=app_dir,
                     creationflags=0x00000008)  # DETACHED_PROCESS
    os._exit(0)
