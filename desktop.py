# -*- coding: utf-8 -*-
"""The Feel Intranet - 데스크톱 앱 진입점.
Flask 서버를 백그라운드로 띄우고 네이티브 창(pywebview)으로 표시한다.
- 시작: 프레임 없는 작은 로그인 팝업
- 로그인 성공: 미리 만들어둔 큰 메인 창을 최대화하여 표시(팝업은 닫음)
같은 사내망의 다른 PC는 브라우저로 http://서버IP:5000 접속."""
import os
import sys
import threading
import webbrowser
import urllib.parse

from werkzeug.serving import make_server

import app as appmod
import version

HOST, PORT = "0.0.0.0", 5000
URL = f"http://127.0.0.1:{PORT}"
TITLE = f"The Feel Intranet  v{version.__version__}"

LOGIN_SIZE = (440, 690)     # 로그인 팝업 (기억 체크 + 하단 푸터)
SIGNUP_SIZE = (450, 830)    # 회원가입 팝업 (ID·전화·비번 한 화면에)
MAIN_SIZE = (1280, 860)     # 로그인 후 메인 창 기본 크기(최대화 전 폴백)
_login_win = None
_main_win = None
_switched = False


class Api:
    """프레임 없는 로그인 팝업에서 호출하는 JS 브리지 (닫기 버튼)"""
    def close_app(self):
        os._exit(0)


class ServerThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.srv = make_server(HOST, PORT, appmod.app, threaded=True)

    def run(self):
        self.srv.serve_forever()


def start_server():
    appmod.init_db()
    appmod.updater.check_async()
    try:
        ServerThread().start()
        return True
    except OSError:
        return False  # 이미 실행 중


def _show_main():
    """미리 만들어둔 메인 창을 대시보드로 로드 → 최대화 표시, 로그인 팝업 닫기."""
    global _switched
    if _switched:
        return
    _switched = True
    try:
        _main_win.load_url(URL)     # 세션 쿠키 공유 → 대시보드 로드
    except Exception:
        pass
    try:
        _main_win.show()
    except Exception:
        pass
    try:
        _main_win.maximize()        # 전체 화면(최대화)으로 크게 열기
    except Exception:
        pass
    try:
        _login_win.destroy()
    except Exception:
        pass


def _on_login_loaded():
    """로그인 팝업의 페이지 전환 처리:
    - /login  : 로그인 팝업 크기
    - /signup : 회원가입 팝업 크기
    - 그 외(로그인 성공): 메인 창을 최대화하여 표시"""
    try:
        path = urllib.parse.urlparse(_login_win.get_current_url() or "").path.rstrip("/")
    except Exception:
        return
    if path == "/signup":
        try: _login_win.resize(*SIGNUP_SIZE)
        except Exception: pass
    elif path == "/login":
        try: _login_win.resize(*LOGIN_SIZE)
        except Exception: pass
    else:
        # 로그인 성공(대시보드 등) → 큰 메인 창으로 전환
        _show_main()


def main():
    global _login_win, _main_win
    start_server()
    try:
        import webview
        # 로그인 팝업(프레임 없음, 작게)
        _login_win = webview.create_window(
            TITLE, URL, js_api=Api(),
            width=LOGIN_SIZE[0], height=LOGIN_SIZE[1],
            frameless=True, easy_drag=True, resizable=False)
        # 메인 창(테두리 있는 일반 창, 크게) - 미리 숨겨서 생성 → 로그인 후 표시
        _main_win = webview.create_window(
            TITLE, "about:blank",
            width=MAIN_SIZE[0], height=MAIN_SIZE[1],
            min_size=(1000, 660), hidden=True)
        _login_win.events.loaded += _on_login_loaded
        webview.start()
    except Exception:
        # WebView2 미설치 등 → 기본 브라우저로 폴백
        webbrowser.open(URL)
        threading.Event().wait()


if __name__ == "__main__":
    main()
