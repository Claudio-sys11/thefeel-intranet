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
TITLE = f"더필코리아 인트라넷  v{version.__version__}"


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


def main():
    start_server()
    try:
        import webview
        webview.create_window(TITLE, URL, width=1240, height=860, min_size=(960, 640))
        webview.start()
    except Exception:
        # WebView2 런타임이 없는 환경 등 → 기본 브라우저로 폴백
        webbrowser.open(URL)
        threading.Event().wait()  # 서버 유지


if __name__ == "__main__":
    main()
