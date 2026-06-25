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
import time
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
_user_closing = False   # 사용자가 직접 창을 닫았는지(자동 재시작 여부 판단)


def _should_restart():
    """비정상 종료 시 자동 재시작 — 단, 짧은 시간 내 반복(크래시 루프) 방지."""
    try:
        path = os.path.join(appmod.DATA_DIR, "restart.cfg")
        now = time.time()
        times = []
        if os.path.exists(path):
            times = [float(x) for x in open(path).read().split() if x.strip()]
        times = [t for t in times if now - t < 120]   # 최근 2분 내 기록만
        times.append(now)
        with open(path, "w") as f:
            f.write(" ".join("%.0f" % t for t in times))
        return len(times) <= 3                          # 2분 내 3회까지만 자동 재시작
    except Exception:
        return False


def _crash_restart(where):
    """비정상 종료 감지 → 로그 남기고 자동 재시작(루프 방지)."""
    appmod.log_event(where, "비정상 종료 감지")
    if getattr(sys, "frozen", False) and _should_restart():
        appmod.log_event("auto-restart", "프로그램을 자동으로 다시 시작합니다")
        appmod.relaunch_app()   # spawn 후 os._exit
    os._exit(0)


def reachable(base):
    try:
        req = urllib.request.Request(base + "/login", headers={"User-Agent": "tfi-client"})
        urllib.request.urlopen(req, timeout=4)
        return True
    except Exception:
        return False


def is_designated_server():
    """이 PC의 LAN IP 가 기본 서버 주소(version.DEFAULT_SERVER_HOST)와 같으면
    이 PC가 '지정 서버 PC' → 무조건 서버 모드로 동작."""
    try:
        host = getattr(version, "DEFAULT_SERVER_HOST", "")
        return bool(host) and appmod.lan_ip() == host
    except Exception:
        return False


# ---------------------------------------------------------------- JS 브리지
class Api:
    def close_app(self):
        os._exit(0)


class ConfigApi:
    """최초 실행 연결 설정 창. 모드 저장 후 진행바가 보이도록 약간의 지연 뒤 재시작."""
    def _schedule_relaunch(self):
        threading.Timer(5.5, appmod.relaunch_app).start()

    def use_self(self):
        appmod.write_server_cfg("self")
        self._schedule_relaunch()
        return True

    def use_auto(self):
        """직원 PC: 서버 자동 탐색 모드로 설정 후 재시작."""
        appmod.write_server_cfg("auto")
        self._schedule_relaunch()
        return True

    def connect(self, addr):
        url = appmod.normalize_server_url(addr)
        if not url:
            return False
        appmod.write_server_cfg(url)
        self._schedule_relaunch()
        return True

    def auto_detect(self):
        """LAN에서 서버를 자동 탐색해 'host:port' 문자열로 반환(JS 입력칸 채우기). 없으면 ''"""
        try:
            url = appmod.discover_server(timeout=2.5)
            if url:
                p = urllib.parse.urlparse(url)
                return f"{p.hostname}:{p.port or PORT}"
        except Exception:
            pass
        return ""


# ---------------------------------------------------------------- 서버
class ServerThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.srv = make_server(HOST, PORT, appmod.app, threaded=True)

    def run(self):
        try:
            self.srv.serve_forever()
        except Exception:
            appmod.log_event("ServerThread", "내부 웹서버 오류")


def start_server():
    appmod.init_db()
    appmod.updater.check_async()
    # 서버 IP 변경 감지 + 기록 (서버 연결 설정 화면에서 안내)
    try:
        cur_ip = appmod.lan_ip()
        prev_ip = appmod.read_last_server_ip()
        if prev_ip and prev_ip != cur_ip:
            appmod.SERVER_IP_CHANGED = (prev_ip, cur_ip)
        appmod.write_last_server_ip(cur_ip)
    except Exception:
        pass
    # 직원 PC가 IP 없이 서버를 자동으로 찾도록 UDP 응답 데몬 시작
    try:
        appmod.start_discovery_responder()
    except Exception:
        pass
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


def _on_closing(*args, **kwargs):
    # 사용자가 창을 직접 닫음 → 정상 종료(자동 재시작 안 함)
    global _user_closing
    _user_closing = True


def launch_windows():
    global _login_win, _main_win, _user_closing
    import webview
    _user_closing = False
    _login_win = webview.create_window(
        TITLE, BASE, js_api=Api(),
        width=LOGIN_SIZE[0], height=LOGIN_SIZE[1],
        frameless=True, easy_drag=True, resizable=False)
    _main_win = webview.create_window(
        TITLE, "about:blank",
        width=MAIN_SIZE[0], height=MAIN_SIZE[1],
        min_size=(1000, 660), hidden=True)
    _login_win.events.loaded += _on_login_loaded
    # 메인 창의 닫기(X)만 '사용자 종료'로 간주 → 자동 재시작 안 함.
    # (로그인 창은 로그인 성공 시 프로그램이 닫으므로 제외. 로그인 창의 X는 close_app→os._exit 라 start()가 반환되지 않음)
    try:
        _main_win.events.closing += _on_closing
    except Exception:
        pass
    try:
        webview.start()
    except Exception:
        _crash_restart("webview.start 예외")   # GUI 스레드 예외 → 재시작
        return
    # webview.start() 가 반환됨: 사용자가 닫았으면 정상 종료, 아니면 창이 사라진 것(크래시) → 재시작
    if not _user_closing:
        _crash_restart("창이 예기치 않게 닫힘(WebView 크래시 의심)")


CONFIG_HTML = """<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<style>
*{box-sizing:border-box;font-family:'Malgun Gothic',sans-serif}
body{margin:0;background:linear-gradient(135deg,#2a0a5e,#5b21b6);color:#fff;height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#fff;color:#1e1b2e;border-radius:16px;padding:30px;width:360px;box-shadow:0 20px 50px rgba(0,0,0,.3)}
h1{font-size:19px;margin:0 0 4px;text-align:center}
.sub{text-align:center;color:#6b6480;font-size:13px;margin:0 0 22px}
.err{background:#fee2e2;color:#991b1b;border-radius:8px;padding:9px 12px;font-size:13px;margin-bottom:16px;white-space:pre-line}
.choice{width:100%;padding:16px;border:0;border-radius:12px;font-weight:800;font-size:15px;cursor:pointer;color:#fff;margin-bottom:12px;line-height:1.5}
.choice small{display:block;font-weight:600;font-size:12px;opacity:.85;margin-top:2px}
.server{background:linear-gradient(135deg,#6d28d9,#c026d3)}
.client{background:#0ea5e9}
.choice:hover{filter:brightness(1.06)}
.manual-link{text-align:center;margin-top:6px}
.manual-link a{color:#9b93b5;font-size:12px;cursor:pointer;text-decoration:underline}
label{display:block;font-weight:700;font-size:13px;margin:14px 0 6px}
input{width:100%;padding:11px;border:1px solid #e6e2f0;border-radius:10px;font-size:14px}
.btn2{width:100%;padding:11px;border:0;border-radius:10px;font-weight:800;font-size:14px;cursor:pointer;color:#fff;background:#475569;margin-top:10px}
#manual{display:none;margin-top:8px}
#restart{display:none;text-align:center}
#restart h2{font-size:18px;margin:6px 0 4px}
#restart p{color:#6b6480;font-size:13px;margin:0 0 18px}
.rtrack{position:relative;background:#e6e2f0;border-radius:999px;height:10px;width:100%;overflow:hidden}
.rfill{height:10px;width:0;background:linear-gradient(90deg,#6d28d9,#c026d3);transition:width .25s}
#rp{display:block;margin-top:10px;font-size:13px;font-weight:800;color:#5b21b6}
</style></head><body>
<div class="card">
  <div id="choose">
    <h1>The Feel Intranet</h1>
    <p class="sub">이 PC를 어떻게 사용할까요?</p>
    __ERR__
    <button class="choice server" onclick="pick('use_self')">🖥 이 PC를 서버로 사용<small>관리자 PC (직원이 접속하는 중앙 PC)</small></button>
    <button class="choice client" onclick="pick('use_auto')">💻 직원 PC로 사용<small>서버를 자동으로 찾아 연결합니다</small></button>
    <div class="manual-link"><a onclick="toggleManual()">서버를 못 찾으면 직접 입력하기</a></div>
    <div id="manual">
      <label>서버(관리자 PC) 주소</label>
      <input id="srv" value="__VAL__" placeholder="예: 192.168.0.74">
      <button class="btn2" onclick="conn()">이 주소로 접속</button>
    </div>
  </div>
  <div id="restart">
    <h2>적용 중…</h2>
    <p>설정을 저장하고 프로그램을 다시 시작합니다.</p>
    <div class="rtrack"><div id="rfill" class="rfill"></div></div>
    <span id="rp">0%</span>
  </div>
</div>
<script>
function showRestart(){
  document.getElementById('choose').style.display='none';
  document.getElementById('restart').style.display='block';
  var fill=document.getElementById('rfill'), rp=document.getElementById('rp'), t0=Date.now(), dur=5500;
  var iv=setInterval(function(){
    var p=Math.min(99, Math.round((Date.now()-t0)/dur*100));
    fill.style.width=p+'%'; rp.textContent=p+'%';
    if(p>=99) clearInterval(iv);
  },100);
}
function pick(fn){ try{ pywebview.api[fn]().then(function(ok){ if(ok) showRestart(); }); }catch(e){} }
function toggleManual(){ var m=document.getElementById('manual'); m.style.display=(m.style.display==='block')?'none':'block'; }
function conn(){ var v=document.getElementById('srv').value.trim();
  if(!v){ alert('서버(관리자 PC) 주소를 입력하세요'); return; }
  try{ pywebview.api.connect(v).then(function(ok){ if(ok) showRestart(); else alert('주소가 올바르지 않습니다'); }); }catch(e){} }
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


def _run_server_mode():
    global BASE
    BASE = f"http://127.0.0.1:{PORT}"
    try:
        start_server()
        launch_windows()
    except Exception:
        webbrowser.open(BASE); threading.Event().wait()


def _run_client_mode(url):
    """직원 PC 접속. url=None 이면 순수 자동 탐색 모드.
    저장 주소 → 자동 탐색(서버 IP 인식) → 기본 주소 순으로 시도."""
    global BASE
    appmod.updater.check_async()
    default = getattr(version, "DEFAULT_SERVER_URL", "")
    try:
        # 1) 저장된 특정 주소(수동 입력)가 있으면 우선
        if url and reachable(url):
            BASE = url; launch_windows(); return
        # 2) 서버 자동 탐색 (IP 자동 인식 — 서버 IP가 바뀌어도 다시 찾음)
        found = appmod.discover_server(timeout=3.0)
        if found and reachable(found):
            BASE = found; launch_windows(); return
        # 3) 기본 서버 주소 폴백
        if default and reachable(default):
            BASE = default; launch_windows(); return
        # 4) 못 찾음 → 설정창
        BASE = url or found or default or f"http://127.0.0.1:{PORT}"
        show_config(error="서버를 찾지 못했습니다.\n서버(관리자) PC가 켜져 있고 같은 네트워크인지\n확인 후 '직원 PC로 사용'을 다시 눌러주세요.")
    except Exception:
        BASE = url or default or f"http://127.0.0.1:{PORT}"
        webbrowser.open(BASE); threading.Event().wait()


# ---------------------------------------------------------------- main
def decide_mode(cfg, db_exists, is_server_pc, default_url):
    """모드 결정(부수효과 없음 → 테스트 용이).
    반환: ("server", None) | ("client", url) | ("client", None=자동탐색) | ("config", None)
    """
    # 1) 명시적 설정 우선 (서버 연결 설정에서 선택한 경우)
    if cfg == "self":
        return ("server", None)
    if cfg == "auto":
        return ("client", None)          # 직원 PC: 서버 자동 탐색 모드
    if cfg and cfg != "self":
        return ("client", cfg)           # 특정 주소(수동 입력)
    # 2) 설정 없음(최초 실행) → 자동 결정
    #    - 이 PC가 '지정 서버 IP' 이거나 이미 데이터 보유 → 무조건 서버
    #    - 그 외(직원 PC) → 서버 자동 탐색(IP 인식)
    if is_server_pc or db_exists:
        return ("server", None)
    return ("client", None)              # 직원 PC 기본 = 자동 탐색


def _main_impl():
    cfg = appmod.read_server_cfg()
    db_exists = os.path.exists(appmod.DB_PATH)
    default_url = getattr(version, "DEFAULT_SERVER_URL", "")

    mode, url = decide_mode(cfg, db_exists, is_designated_server(), default_url)

    if mode == "server":
        if cfg != "self":
            appmod.write_server_cfg("self")
        _run_server_mode(); return
    if mode == "client":
        if url is None:                        # 자동 탐색 모드
            if cfg != "auto":
                appmod.write_server_cfg("auto")
        elif cfg != url:                       # 특정 주소
            appmod.write_server_cfg(url)
        _run_client_mode(url); return

    try:
        show_config()
    except Exception:
        _run_server_mode()


def main():
    try:
        _main_impl()
    except Exception:
        _crash_restart("main 치명적 오류")   # 최후 안전망: 로그 남기고 재시작


if __name__ == "__main__":
    main()
