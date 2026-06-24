# -*- coding: utf-8 -*-
"""더필코리아 인트라넷 - 데스크톱 앱 진입점.
Flask 서버를 백그라운드로 띄우고 네이티브 창(pywebview)으로 표시한다.
같은 사내망의 다른 PC는 브라우저로 http://서버IP:5000 접속."""
import sys
import threading
import webbrowser

from werkzeug.serving import make_server

import app as appmod
import version

HOST, PORT = "0.0.0.0", 5000
URL = f"http://127.0.0.1:{PORT}"
TITLE = f"The Feel Intranet  v{version.__version__}"

LOGIN_SIZE = (440, 690)     # 로그인 팝업 (기억 체크 + 하단 푸터 포함)
SIGNUP_SIZE = (440, 770)    # 회원가입 팝업 (한 화면에 다 보이게)
APP_SIZE = (1240, 860)      # 로그인 후 메인 앱
_login_win = None
_main_win = None


class Api:
    """프레임 없는 로그인 팝업에서 호출하는 JS 브리지"""
    def close_app(self):
        os._exit(0)


class ServerThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.srv = make_server(HOST, PORT, appmod.app, threaded=True)

    def run(self):
        self.srv.serve_forever()


def start_server():
    """서버 시작. 포트가 이미 쓰이면(다른 인스턴스) 조용히 건너뛴다."""
    appmod.init_db()
    appmod.updater.check_async()
    try:
        ServerThread().start()
        return True
    except OSError:
        return False  # 이미 실행 중 → 기존 서버 창만 띄움


def _on_login_loaded():
    """로그인 팝업에서 페이지가 바뀔 때:
    - /login : 로그인 팝업 크기
    - /signup: 회원가입 팝업 크기(한 화면에 다 보이게)
    - 그 외(로그인 성공): 메인 앱 창을 열고 팝업을 닫는다."""
    global _login_win, _main_win
    try:
        import webview
        import urllib.parse
        url = _login_win.get_current_url() or ""
        path = urllib.parse.urlparse(url).path.rstrip("/")
    except Exception:
        return
    if path == "/signup":
        _login_win.resize(*SIGNUP_SIZE)
    elif path in ("/login", ""):
        _login_win.resize(*LOGIN_SIZE)
    elif _main_win is None:
        # 로그인 성공 → 최대화된 메인(테두리 있는) 창을 열고 팝업 닫기 (세션 쿠키 공유)
        try:
            _main_win = webview.create_window(TITLE, url, width=APP_SIZE[0], height=APP_SIZE[1],
                                              min_size=(960, 640), maximized=True)
            _login_win.destroy()
        except Exception:
            # 새 창 생성 실패 시: 기존 팝업을 최대화해 그대로 사용
            _main_win = _login_win
            try:
                _login_win.resize(*APP_SIZE)
                _login_win.maximize()
            except Exception:
                pass


def main():
    global _login_win
    start_server()
    try:
        import webview
        # 프레임 없는(윈도우 창 없는) 로그인 팝업으로 시작 → 실행 즉시 버전 체크 + 로그인
        _login_win = webview.create_window(
            TITLE, URL, js_api=Api(),
            width=LOGIN_SIZE[0], height=LOGIN_SIZE[1],
            frameless=True, easy_drag=True, resizable=False)
        _login_win.events.loaded += _on_login_loaded
        webview.start()
    except Exception:
        # WebView2 런타임이 없는 환경 등 → 기본 브라우저로 폴백
        webbrowser.open(URL)
        threading.Event().wait()  # 서버 유지


if __name__ == "__main__":
    main()
