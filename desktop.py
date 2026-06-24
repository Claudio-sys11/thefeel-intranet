# -*- coding: utf-8 -*-
"""The Feel Intranet - 데스크톱 앱 진입점.

서버 모드 / 클라이언트 모드:
  - 서버 모드: 이 PC에서 Flask + DB 운영. (데이터 보유 PC는 항상 서버 모드 → 데이터 보존)
  - 클라이언트 모드: 서버 PC 주소에 접속만 함(로컬 서버/DB 없음).
모드는 %LOCALAPPDATA%\\ThefeelIntranet\\server.cfg ("self" 또는 서버 URL)에 저장.

모드 전환: 로그인 화면 → "서버 연결 설정"(/connect), 또는 최초 실행 시 설정창.
"""
import os
import sys
import socket
import threading
import webbrowser
import urllib.parse
import urllib.request

from werkzeug.serving import make_server

import app as appmod
import version

HOST, PORT = "0.0.0.0", 5000
TITLE = f"The Feel Intranet  v{version.__version__}"

LOGIN_SIZE = (440, 690)
SIGNUP_SIZE = (450, 830)
MAIN_SIZE = (1280, 860)

BASE = f"http://127.0.0.1:{PORT}"
_login_win = None
_main_win = None
_switched = False


def reachable(base):
    try:
        req = urllib.request.Request(base + "/login", headers={"User-Agent": "tfi-client"})
        urllib.request.urlopen(req, timeout=4)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- JS 브리지
class Api:
    def close_app(self):
        os._exit(0)


class ConfigApi:
    """최초 실행 연결 설정 창"""
    def use_self(self):
        appmod.write_server_cfg("self")
        appmod.relaunch_app()

    def connect(self, addr):
        url = appmod.normalize_server_url(addr)
        if url:
            appmod.write_server_cfg(url)
            appmod.relaunch_app()


# ---------------------------------------------------------------- 서버
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
    except OSError:
        pass


# ---------------------------------------------------------------- 창
def _show_main():
    global _switched
    if _switched:
        return
    _switched = True
    for fn in (lambda: _main_win.load_url(BASE),
               lambda: _main_win.show(),
               lambda: _main_win.maximize(),
               lambda: _login_win.destroy()):
        try:
            fn()
        except Exception:
            pass


def _on_login_loaded():
    try:
        path = urllib.parse.urlparse(_login_win.get_current_url() or "").path.rstrip("/")
    except Exception:
        return
    if path == "/signup":
        try: _login_win.resize(*SIGNUP_SIZE)
        except Exception: pass
    elif path in ("/login", "/connect"):
        try: _login_win.resize(*LOGIN_SIZE)
        except Exception: pass
    else:
        _show_main()


def launch_windows():
    global _login_win, _main_win
    import webview
    _login_win = webview.create_window(
        TITLE, BASE, js_api=Api(),
        width=LOGIN_SIZE[0], height=LOGIN_SIZE[1],
        frameless=True, easy_drag=True, resizable=False)
    _main_win = webview.create_window(
        TITLE, "about:blank",
        width=MAIN_SIZE[0], height=MAIN_SIZE[1],
        min_size=(1000, 660), hidden=True)
    _login_win.events.loaded += _on_login_loaded
    webview.start()


CONFIG_HTML = """<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<style>
*{box-sizing:border-box;font-family:'Malgun Gothic',sans-serif}
body{margin:0;background:linear-gradient(135deg,#2a0a5e,#5b21b6);color:#fff;height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#fff;color:#1e1b2e;border-radius:16px;padding:30px;width:380px;box-shadow:0 20px 50px rgba(0,0,0,.3)}
h1{font-size:19px;margin:0 0 4px;text-align:center}
.sub{text-align:center;color:#6b6480;font-size:13px;margin:0 0 20px}
.err{background:#fee2e2;color:#991b1b;border-radius:8px;padding:9px 12px;font-size:13px;margin-bottom:14px;white-space:pre-line}
button{width:100%;padding:12px;border:0;border-radius:10px;font-weight:800;font-size:14px;cursor:pointer;color:#fff}
.primary{background:linear-gradient(135deg,#6d28d9,#c026d3)}
.alt{background:#475569;margin-top:6px}
label{display:block;font-weight:700;font-size:13px;margin:16px 0 6px}
input{width:100%;padding:11px;border:1px solid #e6e2f0;border-radius:10px;font-size:14px}
.divider{display:flex;align-items:center;gap:10px;color:#9b93b5;font-size:12px;margin:18px 0}
.divider::before,.divider::after{content:"";flex:1;height:1px;background:#e6e2f0}
.ipbox{background:#f4f2f9;border-radius:8px;padding:8px 10px;font-size:12px;color:#6b6480;margin-top:8px;text-align:center}
b{color:#5b21b6}
</style></head><body>
<div class="card">
  <h1>The Feel Intranet 연결 설정</h1>
  <p class="sub">이 PC를 어떻게 사용할지 한 번만 선택하세요</p>
  __ERR__
  <button class="primary" onclick="self_()">이 PC를 서버로 사용 (관리자 PC)</button>
  <div class="ipbox">이 PC 주소: <b>__IP__:5000</b><br>직원에게 이 주소를 알려주세요</div>
  <div class="divider">또는</div>
  <label>서버(관리자 PC) 주소</label>
  <input id="srv" value="__VAL__" placeholder="예: 192.168.0.74">
  <button class="alt" onclick="conn()">이 주소의 서버에 접속 (직원 PC)</button>
</div>
<script>
function self_(){ try{ pywebview.api.use_self(); }catch(e){} }
function conn(){ var v=document.getElementById('srv').value.trim();
  if(!v){ alert('서버(관리자 PC) IP 주소를 입력하세요'); return; }
  try{ pywebview.api.connect(v); }catch(e){} }
</script></body></html>"""


def show_config(error="", value=""):
    import webview
    html = (CONFIG_HTML
            .replace("__ERR__", f'<div class="err">{error}</div>' if error else "")
            .replace("__IP__", appmod.lan_ip())
            .replace("__VAL__", value))
    webview.create_window("연결 설정 · The Feel Intranet", html=html,
                          js_api=ConfigApi(), width=440, height=600, resizable=False)
    webview.start()


# ---------------------------------------------------------------- main
def main():
    global BASE
    cfg = appmod.read_server_cfg()
    db_exists = os.path.exists(appmod.DB_PATH)

    # 데이터가 있는 PC(또는 self 설정)는 '항상' 서버 모드 → 데이터 절대 손실/숨김 없음
    if cfg == "self" or (cfg is None and db_exists):
        BASE = f"http://127.0.0.1:{PORT}"
        try:
            start_server()
            launch_windows()
        except Exception:
            webbrowser.open(BASE); threading.Event().wait()
        return

    # 클라이언트 모드 (server.cfg 가 URL)
    if cfg and cfg != "self":
        BASE = cfg
        appmod.updater.check_async()
        try:
            if reachable(BASE):
                launch_windows()
            else:
                show_config(error=f"서버에 연결할 수 없습니다:\n{BASE}\n서버 PC가 켜져 있고 방화벽(5000)이 열려 있는지 확인하세요.",
                            value=urllib.parse.urlparse(BASE).hostname or "")
        except Exception:
            webbrowser.open(BASE); threading.Event().wait()
        return

    # 최초 실행 (설정/데이터 모두 없음) → 연결 설정창
    try:
        show_config()
    except Exception:
        # webview 불가 → 안전하게 서버 모드로
        BASE = f"http://127.0.0.1:{PORT}"
        start_server()
        webbrowser.open(BASE); threading.Event().wait()


if __name__ == "__main__":
    main()
