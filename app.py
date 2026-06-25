# -*- coding: utf-8 -*-
"""
사내 인트라넷 시스템 (더필코리아)
- 로그인 / 사용자 관리
- 전자결재 (결재선, 승인/반려)
- 사내 메일
- 연차/휴가 관리
Flask + SQLite, 단일 실행 파일.
"""
import os
import sys
import glob
import shutil
import socket
import sqlite3
import webbrowser
import threading
import subprocess
import urllib.parse
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask, g, session, request, redirect, url_for,
    render_template, flash, abort, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

# PyInstaller(frozen) 환경에서 OpenSSL scrypt 미지원으로 로그인이 실패하는 문제를
# 피하기 위해 항상 이식성 좋은 pbkdf2 방식으로 해시한다.
HASH_METHOD = "pbkdf2:sha256"


def hashpw(pw):
    return generate_password_hash(pw, method=HASH_METHOD)


def verifypw(stored, pw):
    try:
        return check_password_hash(stored, pw)
    except Exception:
        return False


def format_phone(s):
    """숫자만 입력해도 000-0000-0000(또는 00-000-0000) 형식으로 정규화"""
    d = "".join(ch for ch in (s or "") if ch.isdigit())[:11]
    if len(d) == 11:
        return f"{d[:3]}-{d[3:7]}-{d[7:]}"
    if len(d) == 10:
        return f"{d[:3]}-{d[3:6]}-{d[6:]}"
    return s or ""

import version
import updater

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_path(rel):
    """PyInstaller 번들 내부(templates/static) 경로"""
    return os.path.join(getattr(sys, "_MEIPASS", BASE_DIR), rel)


# 데이터(db, 설정)는 설치 폴더와 분리된 영구 위치에 저장 → 업그레이드·재설치에도 보존.
# 번들 리소스(templates/static/schema)는 _MEIPASS 에서 로드.
if getattr(sys, "frozen", False):
    DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.dirname(sys.executable),
                            "ThefeelIntranet")
else:
    DATA_DIR = BASE_DIR
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "intranet.db")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
SERVER_CFG = os.path.join(DATA_DIR, "server.cfg")

# 파일 로깅 (frozen/windowed 환경에서 오류 추적용) - 핸들러 강제 부착
import logging
_root = logging.getLogger()
for _h in list(_root.handlers):
    _root.removeHandler(_h)
_fh = logging.FileHandler(os.path.join(DATA_DIR, "app.log"), encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
_root.addHandler(_fh)
_root.setLevel(logging.INFO)
# werkzeug 요청 로그 소음 줄여 실제 오류가 묻히지 않게 (오류는 그대로 기록됨)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# --- 크래시/예외 로깅 (흔적 없이 종료되는 문제 추적용) ---------------------
import traceback as _tb
import faulthandler as _fault

CRASH_LOG = os.path.join(DATA_DIR, "crash.log")


def log_event(where, detail=""):
    """현재 예외(있으면)와 함께 crash.log 에 한 줄 기록. 흔적 없이 종료되는 문제 추적."""
    try:
        from datetime import datetime as _dt
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write("\n===== %s =====\n[%s] %s\n" % (_dt.now().strftime("%Y-%m-%d %H:%M:%S"), where, detail))
            ei = sys.exc_info()
            if ei and ei[0]:
                f.write("".join(_tb.format_exception(*ei)))
    except Exception:
        pass


def _sys_excepthook(t, v, tb):
    try:
        from datetime import datetime as _dt
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write("\n===== %s =====\n[uncaught:main]\n" % _dt.now().strftime("%Y-%m-%d %H:%M:%S"))
            f.write("".join(_tb.format_exception(t, v, tb)))
    except Exception:
        pass


def _thread_excepthook(a):
    try:
        from datetime import datetime as _dt
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write("\n===== %s =====\n[uncaught:thread %s]\n" %
                    (_dt.now().strftime("%Y-%m-%d %H:%M:%S"), getattr(a.thread, "name", "?")))
            f.write("".join(_tb.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))
    except Exception:
        pass


sys.excepthook = _sys_excepthook
try:
    threading.excepthook = _thread_excepthook   # Py3.8+
except Exception:
    pass
try:                                            # 네이티브(WebView2 등) 치명적 크래시 스택 덤프
    _fault.enable(file=open(os.path.join(DATA_DIR, "fatal.log"), "a", encoding="utf-8"), all_threads=True)
except Exception:
    pass

app = Flask(__name__,
            template_folder=resource_path("templates"),
            static_folder=resource_path("static"))


def _load_secret():
    p = os.path.join(DATA_DIR, "secret.key")
    try:
        if os.path.exists(p):
            return open(p, "rb").read()
        key = os.urandom(24)
        open(p, "wb").write(key)
        return key
    except OSError:
        return b"thefeel-intranet-fallback-key"


app.config["SECRET_KEY"] = _load_secret()

DOC_TYPES = {
    "general":  "일반품의",
    "expense":  "지출결의",
    "purchase": "구매요청",
    "leave":    "휴가신청",
}
LEAVE_TYPES = {
    "annual":  ("연차", 1.0),
    "half_am": ("오전반차", 0.5),
    "half_pm": ("오후반차", 0.5),
    "sick":    ("병가", 1.0),
}


# ---------------------------------------------------------------- DB helpers
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


ADMIN_USER = "THEFEELKOREA"
ADMIN_PW = "231900"


# ---------------------------------------------------------------- 데이터 보호(백업/복구)
def _backup_db():
    """사용자 데이터가 있으면 타임스탬프 백업 생성, 최신 30개만 유지."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        chk = sqlite3.connect(DB_PATH)
        n = chk.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        chk.close()
        if n <= 0:
            return
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = os.path.join(BACKUP_DIR, f"intranet-{ts}.db")
        if not os.path.exists(dst):
            shutil.copy2(DB_PATH, dst)
        for old in sorted(glob.glob(os.path.join(BACKUP_DIR, "intranet-*.db")))[:-30]:
            try:
                os.remove(old)
            except OSError:
                pass
    except Exception:
        pass


def _restore_if_missing():
    """메인 DB가 없으면 최신 백업에서 복원(데이터 손실 방지)."""
    if os.path.exists(DB_PATH):
        return
    try:
        bks = sorted(glob.glob(os.path.join(BACKUP_DIR, "intranet-*.db")))
        if bks:
            shutil.copy2(bks[-1], DB_PATH)
    except Exception:
        pass


# ---------------------------------------------------------------- 서버/클라이언트 설정
def read_server_cfg():
    try:
        v = open(SERVER_CFG, encoding="utf-8").read().strip()
        return v or None
    except OSError:
        return None


def write_server_cfg(val):
    try:
        with open(SERVER_CFG, "w", encoding="utf-8") as f:
            f.write(val or "")
    except OSError:
        pass


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def normalize_server_url(s):
    s = (s or "").strip()
    if not s:
        return None
    if "://" not in s:
        s = "http://" + s
    p = urllib.parse.urlparse(s)
    if not p.hostname:
        return None
    return f"http://{p.hostname}:{p.port or 5000}"


# ---------------------------------------------------------------- LAN 서버 자동 탐색 (UDP 브로드캐스트)
# 직원 PC가 서버 PC를 IP 없이 자동으로 찾고, 서버 IP가 바뀌어도 다시 찾을 수 있게 함.
DISCOVERY_PORT = 50505
DISCOVERY_MAGIC = b"TFI_DISCOVER_V1"
WEB_PORT = getattr(version, "DEFAULT_SERVER_PORT", 5000)
SERVER_IP_CFG = os.path.join(DATA_DIR, "server_ip.cfg")   # 서버가 마지막으로 기록한 자기 IP(변경 감지용)
SERVER_IP_CHANGED = None   # (이전IP, 현재IP) — 서버 시작 시 IP가 바뀌었으면 설정됨
_discovery_started = False


def read_last_server_ip():
    try:
        return (open(SERVER_IP_CFG, encoding="utf-8").read().strip() or None)
    except OSError:
        return None


def write_last_server_ip(ip):
    try:
        with open(SERVER_IP_CFG, "w", encoding="utf-8") as f:
            f.write(ip or "")
    except OSError:
        pass


def _subnet_broadcast():
    ip = lan_ip()
    if ip and ip != "127.0.0.1" and ip.count(".") == 3:
        return ip.rsplit(".", 1)[0] + ".255"
    return None


def start_discovery_responder():
    """서버 모드 전용: 직원 PC의 탐색 요청에 '현재' IP로 응답하는 UDP 데몬."""
    global _discovery_started
    if _discovery_started:
        return
    _discovery_started = True

    def _serve():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", DISCOVERY_PORT))
        except Exception:
            return
        while True:
            try:
                data, addr = s.recvfrom(1024)
                if data.startswith(DISCOVERY_MAGIC):
                    # 응답마다 현재 IP를 다시 평가 → IP가 바뀌어도 항상 최신값 응답
                    reply = ("TFI_SERVER|%s|%d" % (lan_ip(), WEB_PORT)).encode("utf-8")
                    s.sendto(reply, addr)
            except Exception:
                pass

    threading.Thread(target=_serve, daemon=True).start()


def find_other_server(timeout=1.5):
    """LAN에 이미 '다른' 서버가 있으면 그 주소를 반환(자기 자신 제외). 없으면 None.
    → 서버는 하나만 두기 위해, 다른 서버가 있으면 이 PC는 직원 PC로만 설정하게 함."""
    url = discover_server(timeout=timeout)
    if not url:
        return None
    try:
        host = urllib.parse.urlparse(url).hostname
    except Exception:
        host = None
    if host and host == lan_ip():
        return None      # 자기 자신(이미 이 PC가 서버) → '다른 서버' 아님
    return url


def discover_server(timeout=2.0):
    """클라이언트(직원 PC): LAN 브로드캐스트로 서버 주소(http://ip:port)를 찾음. 없으면 None."""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        targets = ["255.255.255.255"]
        sb = _subnet_broadcast()
        if sb and sb not in targets:
            targets.append(sb)
        for b in targets:
            try:
                s.sendto(DISCOVERY_MAGIC, (b, DISCOVERY_PORT))
            except Exception:
                pass
        while True:                       # timeout 안에서 첫 유효 응답 반환
            data, addr = s.recvfrom(1024)
            if data.startswith(b"TFI_SERVER|"):
                parts = data.decode("utf-8", "ignore").split("|")
                ip = parts[1] if len(parts) > 1 and parts[1] else addr[0]
                port = parts[2] if len(parts) > 2 and parts[2] else str(WEB_PORT)
                return f"http://{ip}:{port}"
    except Exception:
        return None
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass
    return None


def relaunch_app():
    """현재 앱(exe)을 재시작 (모드 변경 적용). 성공 시 반환 없음.
    Windows 작업 스케줄러로 위임해 새 인스턴스를 확실히 띄움(분리 프로세스만으로는
    상위 잡 오브젝트/세션 문제로 실행이 누락될 수 있음). 실패 시 분리 프로세스로 폴백."""
    exe = sys.executable
    if getattr(sys, "frozen", False):
        CNW = 0x08000000  # CREATE_NO_WINDOW
        ok = False
        try:
            task = "TheFeelIntranetRelaunch"
            action = (f'cmd /c ping 127.0.0.1 -n 2 >nul & '
                      f'"{exe}" & schtasks /delete /tn {task} /f')
            r1 = subprocess.run(["schtasks", "/create", "/tn", task, "/sc", "once",
                                 "/st", "00:00", "/tr", action, "/f"], creationflags=CNW)
            r2 = subprocess.run(["schtasks", "/run", "/tn", task], creationflags=CNW)
            ok = (r1.returncode == 0 and r2.returncode == 0)
        except Exception:
            ok = False
        if not ok:
            try:  # 폴백: 분리 프로세스로 직접 재실행
                subprocess.Popen(["cmd", "/c", f'ping 127.0.0.1 -n 2 >nul & "{exe}"'],
                                 creationflags=0x00000208, close_fds=True)
            except Exception:
                pass
    os._exit(0)


def init_db():
    _restore_if_missing()
    db = sqlite3.connect(DB_PATH)
    with open(resource_path("schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())

    # --- 컬럼 마이그레이션 (기존 DB 호환) ---
    cols = [r[1] for r in db.execute("PRAGMA table_info(users)")]
    if "phone" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    if "status" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    if "emp_no" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN emp_no TEXT")
    if "locked" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN locked INTEGER NOT NULL DEFAULT 0")
    if "dept2" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN dept2 TEXT")
    if "ext" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN ext TEXT")
    if "job_title" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN job_title TEXT")
    if "perm_users" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN perm_users INTEGER NOT NULL DEFAULT 0")
    if "perm_leave" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN perm_leave INTEGER NOT NULL DEFAULT 0")
    if "approved_at" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN approved_at TEXT")  # 가입 승인 일시
        # 기존 승인(active) 계정은 가입일시를 승인일시로 백필
        db.execute("UPDATE users SET approved_at=created_at WHERE approved_at IS NULL AND status='active'")
    if "last_login" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN last_login TEXT")   # 최근 접속(로그인) 일시
    if "used_manual" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN used_manual REAL NOT NULL DEFAULT 0")  # 연차 사용(수기 입력)
    # 로그인 ID는 대문자만 사용 → 기존 username 대문자로 통일
    db.execute("UPDATE users SET username = UPPER(username) WHERE username <> UPPER(username)")
    # 기존 전화번호도 000-0000-0000 형식으로 정리(하이픈 없는 것만)
    for rid, ph in db.execute("SELECT id, phone FROM users WHERE phone IS NOT NULL AND phone<>'' AND phone NOT LIKE '%-%'").fetchall():
        db.execute("UPDATE users SET phone=? WHERE id=?", (format_phone(ph), rid))

    # --- 관리자 계정 보장 ---
    cnt = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    has_admin_id = db.execute("SELECT 1 FROM users WHERE username=?", (ADMIN_USER,)).fetchone()
    legacy = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if cnt == 0:
        db.execute(
            "INSERT INTO users (username, password_hash, name, dept, position, role, status, hire_date, annual_leave, approved_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
            (ADMIN_USER, hashpw(ADMIN_PW), "관리자",
             "경영지원", "관리자", "admin", "active", date.today().isoformat(), 15),
        )
    elif legacy and not has_admin_id:
        # 구버전 기본 admin 계정 → THEFEELKOREA 로 이관
        db.execute("UPDATE users SET username=?, password_hash=?, role='admin', status='active', is_active=1 WHERE id=?",
                   (ADMIN_USER, hashpw(ADMIN_PW), legacy["id"] if hasattr(legacy, "keys") else legacy[0]))

    # frozen 환경에서 검증 불가한 scrypt 해시 자가 복구 (관리자 계정 한정, 평문 알고 있음)
    db.execute("UPDATE users SET password_hash=? WHERE username=? AND password_hash LIKE 'scrypt:%'",
               (hashpw(ADMIN_PW), ADMIN_USER))
    db.commit()
    db.close()
    _backup_db()   # 데이터 백업 (손실 방지)


# ---------------------------------------------------------------- auth
def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def can_manage_users(u):
    """직원관리 권한: 관리자 또는 직원관리 권한 부여자"""
    return bool(u and (u["role"] == "admin" or u["perm_users"]))


def can_manage_leave(u):
    """연차관리 권한: 관리자 또는 연차관리 권한 부여자"""
    return bool(u and (u["role"] == "admin" or u["perm_leave"]))


@app.context_processor
def inject_globals():
    user = current_user()
    unread = pending = 0
    if user:
        unread = get_db().execute(
            "SELECT COUNT(*) FROM message_recipients WHERE recipient_id=? AND is_read=0 AND deleted_by_recipient=0",
            (user["id"],)).fetchone()[0]
        pending = get_db().execute(
            "SELECT COUNT(*) FROM approval_lines WHERE approver_id=? AND status='pending'",
            (user["id"],)).fetchone()[0]
    return dict(current_user=user, nav_unread=unread, nav_pending=pending,
                DOC_TYPES=DOC_TYPES, LEAVE_TYPES=LEAVE_TYPES,
                APP_VERSION=version.__version__, update_info=updater.UPDATE_INFO,
                can_users=can_manage_users(user), can_leave=can_manage_leave(user))


def login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if not session.get("uid"):
            return redirect(url_for("login", next=request.path))
        return f(*a, **k)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        u = current_user()
        if not u or u["role"] != "admin":
            abort(403)
        return f(*a, **k)
    return wrapper


def users_required(f):
    """직원관리 권한 필요 (관리자 또는 직원관리 권한 부여자)"""
    @wraps(f)
    def wrapper(*a, **k):
        if not can_manage_users(current_user()):
            abort(403)
        return f(*a, **k)
    return wrapper


def leave_admin_required(f):
    """연차관리 권한 필요 (관리자 또는 연차관리 권한 부여자)"""
    @wraps(f)
    def wrapper(*a, **k):
        if not can_manage_leave(current_user()):
            abort(403)
        return f(*a, **k)
    return wrapper


# ---------------------------------------------------------------- routes: auth
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().upper()   # 로그인 ID는 대문자만
        password = request.form.get("password", "")
        row = get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if row and verifypw(row["password_hash"], password):
            if row["status"] == "pending":
                flash("관리자 승인 대기 중인 계정입니다.", "error")
            elif row["locked"]:
                flash("잠긴 계정입니다. 관리자에게 문의하세요.", "error")
            elif not row["is_active"]:
                flash("퇴사 처리되어 로그인할 수 없습니다. 관리자에게 문의하세요.", "error")
            elif row["status"] == "rejected":
                flash("이용이 제한된 계정입니다. 관리자에게 문의하세요.", "error")
            else:
                db = get_db()
                db.execute("UPDATE users SET last_login=datetime('now','localtime') WHERE id=?", (row["id"],))
                db.commit()
                session.clear()
                session["uid"] = row["id"]
                return redirect(request.args.get("next") or url_for("dashboard"))
        else:
            flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/connect", methods=["GET", "POST"])
def connect_settings():
    """서버/클라이언트 연결 모드 설정 (로그인 전에도 접근 가능)."""
    if request.method == "POST":
        mode = request.form.get("mode")
        if mode == "auto":
            newcfg = "auto"
        elif mode == "client":
            url = normalize_server_url(request.form.get("server", ""))
            if not url:
                flash("서버(관리자 PC) 주소를 올바르게 입력하세요.", "error")
                return redirect(url_for("connect_settings"))
            newcfg = url
        else:
            newcfg = "self"
        # 서버는 하나만: 이미 다른 서버가 있으면 '이 PC를 서버로'는 거부 → 직원 PC로만
        if newcfg == "self":
            other = find_other_server()
            if other:
                flash(f"이미 서버 PC가 사용 중입니다({other}). 이 PC는 직원 PC로만 설정할 수 있습니다.", "error")
                return redirect(url_for("connect_settings"))
        cur = read_server_cfg()
        write_server_cfg(newcfg)
        # 모드 변경이 없으면 재시작 불필요 → 바로 로그인 화면으로 (멈춘 듯 보이는 문제 방지)
        if (cur or "self") == newcfg:
            flash("이미 해당 모드로 설정되어 있습니다." if newcfg == "self"
                  else "설정을 저장했습니다.", "ok")
            return redirect(url_for("login"))
        threading.Timer(5.5, relaunch_app).start()   # 진행바가 거의 찬 뒤 재시작
        return render_template("connect.html", restarting=True, lan_ip=lan_ip())
    return render_template("connect.html", cur=read_server_cfg(), lan_ip=lan_ip(),
                           ip_changed=SERVER_IP_CHANGED, other_server=find_other_server())


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("uid"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().upper()   # 로그인 ID(대문자)
        name = request.form.get("name", "").strip()
        phone = format_phone(request.form.get("phone", "").strip())
        pw = request.form.get("password", "")
        pw2 = request.form.get("password2", "")
        if not username or not name:
            flash("아이디와 이름을 입력하세요.", "error")
        elif len(username) < 3:
            flash("아이디는 3자 이상이어야 합니다.", "error")
        elif len(pw) < 4:
            flash("비밀번호는 4자 이상이어야 합니다.", "error")
        elif pw != pw2:
            flash("비밀번호가 일치하지 않습니다.", "error")
        elif get_db().execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            flash("이미 사용 중인 아이디입니다. 다른 아이디를 입력하세요.", "error")
        else:
            get_db().execute(
                "INSERT INTO users (username, password_hash, name, phone, role, status, is_active, annual_leave)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (username, hashpw(pw), name, phone, "employee", "pending", 0, 15))
            get_db().commit()
            flash("가입 신청이 완료되었습니다. 관리자 승인 후 로그인할 수 있습니다.", "ok")
            return redirect(url_for("login"))
    return render_template("signup.html", form=request.form)


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    u = current_user()
    if request.method == "POST":
        form = request.form.get("form")
        if form == "profile":
            name = request.form.get("name", "").strip()
            if not name:
                flash("이름은 비울 수 없습니다.", "error")
            else:
                get_db().execute("UPDATE users SET name=?, phone=?, email=? WHERE id=?",
                                 (name, format_phone(request.form.get("phone", "").strip()),
                                  request.form.get("email", "").strip(), u["id"]))
                get_db().commit()
                flash("내 정보가 수정되었습니다.", "ok")
        else:  # 비밀번호 변경
            cur = request.form.get("current_pw", "")
            new = request.form.get("new_pw", "")
            if not verifypw(u["password_hash"], cur):
                flash("현재 비밀번호가 일치하지 않습니다.", "error")
            elif len(new) < 4:
                flash("새 비밀번호는 4자 이상이어야 합니다.", "error")
            else:
                get_db().execute("UPDATE users SET password_hash=? WHERE id=?",
                                 (hashpw(new), u["id"]))
                get_db().commit()
                flash("비밀번호가 변경되었습니다.", "ok")
        return redirect(url_for("account"))
    return render_template("account.html")


# ---------------------------------------------------------------- dashboard
@app.route("/")
@login_required
def dashboard():
    db = get_db()
    uid = current_user()["id"]
    # 내 결재 대기
    pending_docs = db.execute("""
        SELECT d.*, u.name AS drafter_name FROM approval_lines al
        JOIN documents d ON d.id = al.doc_id
        JOIN users u ON u.id = d.drafter_id
        WHERE al.approver_id=? AND al.status='pending' AND d.status='pending'
        ORDER BY d.created_at DESC""", (uid,)).fetchall()
    # 내가 기안한 진행중 문서
    my_docs = db.execute(
        "SELECT * FROM documents WHERE drafter_id=? ORDER BY created_at DESC LIMIT 5", (uid,)).fetchall()
    # 최근 받은 메일
    recent_mail = db.execute("""
        SELECT m.*, u.name AS sender_name, mr.is_read FROM message_recipients mr
        JOIN messages m ON m.id = mr.message_id
        JOIN users u ON u.id = m.sender_id
        WHERE mr.recipient_id=? AND mr.deleted_by_recipient=0
        ORDER BY m.created_at DESC LIMIT 5""", (uid,)).fetchall()
    notices = db.execute("""
        SELECT n.*, u.name AS author_name FROM notices n JOIN users u ON u.id=n.author_id
        ORDER BY n.is_pinned DESC, n.created_at DESC LIMIT 5""").fetchall()
    leave = leave_summary(uid)
    return render_template("dashboard.html", pending_docs=pending_docs,
                           my_docs=my_docs, recent_mail=recent_mail, leave=leave, notices=notices)


# ---------------------------------------------------------------- notice
@app.route("/notice")
@login_required
def notice_list():
    rows = get_db().execute("""
        SELECT n.*, u.name AS author_name FROM notices n JOIN users u ON u.id=n.author_id
        ORDER BY n.is_pinned DESC, n.created_at DESC""").fetchall()
    return render_template("notice/list.html", rows=rows)


@app.route("/notice/<int:nid>")
@login_required
def notice_view(nid):
    n = get_db().execute("""SELECT n.*, u.name AS author_name, u.dept AS author_dept
                            FROM notices n JOIN users u ON u.id=n.author_id WHERE n.id=?""", (nid,)).fetchone()
    if not n:
        abort(404)
    return render_template("notice/view.html", n=n)


@app.route("/notice/new", methods=["GET", "POST"])
@admin_required
def notice_new():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("제목을 입력하세요.", "error")
            return render_template("notice/form.html", n=request.form, mode="new")
        db = get_db()
        db.execute("INSERT INTO notices (author_id, title, content, is_pinned) VALUES (?,?,?,?)",
                   (current_user()["id"], title, request.form.get("content", "").strip(),
                    1 if request.form.get("is_pinned") else 0))
        db.commit()
        flash("공지사항을 등록했습니다.", "ok")
        return redirect(url_for("notice_list"))
    return render_template("notice/form.html", n={}, mode="new")


@app.route("/notice/<int:nid>/edit", methods=["GET", "POST"])
@admin_required
def notice_edit(nid):
    db = get_db()
    n = db.execute("SELECT * FROM notices WHERE id=?", (nid,)).fetchone()
    if not n:
        abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("제목을 입력하세요.", "error")
            return render_template("notice/form.html", n=n, mode="edit")
        db.execute("UPDATE notices SET title=?, content=?, is_pinned=? WHERE id=?",
                   (title, request.form.get("content", "").strip(),
                    1 if request.form.get("is_pinned") else 0, nid))
        db.commit()
        flash("공지사항을 수정했습니다.", "ok")
        return redirect(url_for("notice_view", nid=nid))
    return render_template("notice/form.html", n=n, mode="edit")


@app.route("/notice/<int:nid>/delete", methods=["POST"])
@admin_required
def notice_delete(nid):
    db = get_db()
    db.execute("DELETE FROM notices WHERE id=?", (nid,))
    db.commit()
    flash("공지사항을 삭제했습니다.", "ok")
    return redirect(url_for("notice_list"))


# ---------------------------------------------------------------- approval
def next_doc_number(db, doc_type):
    prefix = {"general": "GEN", "expense": "EXP", "purchase": "PUR", "leave": "LEA"}.get(doc_type, "DOC")
    ymd = date.today().strftime("%Y%m")
    cnt = db.execute("SELECT COUNT(*) FROM documents WHERE doc_number LIKE ?",
                     (f"{prefix}-{ymd}-%",)).fetchone()[0]
    return f"{prefix}-{ymd}-{cnt+1:03d}"


@app.route("/approval")
@login_required
def approval_list():
    db = get_db()
    uid = current_user()["id"]
    tab = request.args.get("tab", "todo")
    if tab == "todo":      # 결재할 문서
        docs = db.execute("""
            SELECT d.*, u.name AS drafter_name FROM approval_lines al
            JOIN documents d ON d.id=al.doc_id JOIN users u ON u.id=d.drafter_id
            WHERE al.approver_id=? AND al.status='pending' AND d.status='pending'
            ORDER BY d.created_at DESC""", (uid,)).fetchall()
    elif tab == "drafted":  # 내가 기안
        docs = db.execute("""
            SELECT d.*, u.name AS drafter_name FROM documents d JOIN users u ON u.id=d.drafter_id
            WHERE d.drafter_id=? ORDER BY d.created_at DESC""", (uid,)).fetchall()
    else:                   # 내가 결재한 (완료/이력)
        docs = db.execute("""
            SELECT d.*, u.name AS drafter_name FROM approval_lines al
            JOIN documents d ON d.id=al.doc_id JOIN users u ON u.id=d.drafter_id
            WHERE al.approver_id=? AND al.status IN ('approved','rejected')
            ORDER BY d.created_at DESC""", (uid,)).fetchall()
    return render_template("approval/list.html", docs=docs, tab=tab)


@app.route("/approval/new", methods=["GET", "POST"])
@login_required
def approval_new():
    db = get_db()
    uid = current_user()["id"]
    users = db.execute("SELECT id, name, dept, position FROM users WHERE is_active=1 AND id!=? ORDER BY name", (uid,)).fetchall()
    if request.method == "POST":
        doc_type = request.form.get("doc_type", "general")
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        approvers = request.form.getlist("approvers")  # 순서대로 user id 리스트
        approvers = [a for a in approvers if a]
        if not title or not approvers:
            flash("제목과 결재선(1명 이상)을 입력하세요.", "error")
            return render_template("approval/new.html", users=users, form=request.form)

        # 휴가신청이면 추가 검증
        leave_data = None
        if doc_type == "leave":
            leave_data = parse_leave_form(request.form)
            if isinstance(leave_data, str):
                flash(leave_data, "error")
                return render_template("approval/new.html", users=users, form=request.form)

        doc_number = next_doc_number(db, doc_type)
        cur = db.execute(
            "INSERT INTO documents (doc_number, drafter_id, doc_type, title, content) VALUES (?,?,?,?,?)",
            (doc_number, uid, doc_type, title, content))
        doc_id = cur.lastrowid
        for i, aid in enumerate(approvers):
            db.execute(
                "INSERT INTO approval_lines (doc_id, approver_id, step_order, status) VALUES (?,?,?,?)",
                (doc_id, int(aid), i + 1, "pending" if i == 0 else "waiting"))
        if leave_data:
            lt, sd, ed, days, reason = leave_data
            db.execute(
                "INSERT INTO leave_requests (doc_id, user_id, leave_type, start_date, end_date, days, reason)"
                " VALUES (?,?,?,?,?,?,?)", (doc_id, uid, lt, sd, ed, days, reason))
        db.commit()
        flash(f"결재 문서가 상신되었습니다. (문서번호 {doc_number})", "ok")
        return redirect(url_for("approval_detail", doc_id=doc_id))
    return render_template("approval/new.html", users=users, form={})


def parse_leave_form(form):
    lt = form.get("leave_type", "annual")
    sd = form.get("start_date", "")
    ed = form.get("end_date", "") or sd
    reason = form.get("reason", "").strip()
    if lt not in LEAVE_TYPES:
        return "휴가 종류가 올바르지 않습니다."
    try:
        d1 = datetime.strptime(sd, "%Y-%m-%d").date()
        d2 = datetime.strptime(ed, "%Y-%m-%d").date()
    except ValueError:
        return "휴가 시작일/종료일을 입력하세요."
    if d2 < d1:
        return "종료일이 시작일보다 빠릅니다."
    unit = LEAVE_TYPES[lt][1]
    if unit == 0.5:
        days = 0.5
        ed = sd  # 반차는 당일
    else:
        days = (d2 - d1).days + 1
    return (lt, sd, ed, days, reason)


@app.route("/approval/<int:doc_id>")
@login_required
def approval_detail(doc_id):
    db = get_db()
    doc = db.execute("""SELECT d.*, u.name AS drafter_name, u.dept AS drafter_dept, u.position AS drafter_pos
                        FROM documents d JOIN users u ON u.id=d.drafter_id WHERE d.id=?""", (doc_id,)).fetchone()
    if not doc:
        abort(404)
    lines = db.execute("""SELECT al.*, u.name, u.dept, u.position FROM approval_lines al
                          JOIN users u ON u.id=al.approver_id WHERE al.doc_id=? ORDER BY al.step_order""",
                       (doc_id,)).fetchall()
    leave = db.execute("SELECT * FROM leave_requests WHERE doc_id=?", (doc_id,)).fetchone()
    uid = current_user()["id"]
    # 내가 지금 결재할 차례인가
    my_line = next((l for l in lines if l["approver_id"] == uid and l["status"] == "pending"), None)
    can_act = my_line is not None and doc["status"] == "pending"
    return render_template("approval/detail.html", doc=doc, lines=lines, leave=leave,
                           can_act=can_act, my_line=my_line)


@app.route("/approval/<int:doc_id>/act", methods=["POST"])
@login_required
def approval_act(doc_id):
    db = get_db()
    uid = current_user()["id"]
    action = request.form.get("action")     # approve | reject
    comment = request.form.get("comment", "").strip()
    doc = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc or doc["status"] != "pending":
        abort(404)
    line = db.execute("SELECT * FROM approval_lines WHERE doc_id=? AND approver_id=? AND status='pending'",
                      (doc_id, uid)).fetchone()
    if not line:
        flash("결재 권한이 없거나 이미 처리된 문서입니다.", "error")
        return redirect(url_for("approval_detail", doc_id=doc_id))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if action == "reject":
        db.execute("UPDATE approval_lines SET status='rejected', comment=?, acted_at=? WHERE id=?",
                   (comment, now, line["id"]))
        db.execute("UPDATE documents SET status='rejected', completed_at=? WHERE id=?", (now, doc_id))
        flash("문서를 반려했습니다.", "ok")
    else:
        db.execute("UPDATE approval_lines SET status='approved', comment=?, acted_at=? WHERE id=?",
                   (comment, now, line["id"]))
        nxt = db.execute("SELECT * FROM approval_lines WHERE doc_id=? AND step_order>? ORDER BY step_order LIMIT 1",
                         (doc_id, line["step_order"])).fetchone()
        if nxt:
            db.execute("UPDATE approval_lines SET status='pending' WHERE id=?", (nxt["id"],))
            flash("결재를 승인했습니다. 다음 결재자에게 전달됩니다.", "ok")
        else:
            db.execute("UPDATE documents SET status='approved', completed_at=? WHERE id=?", (now, doc_id))
            flash("최종 승인 처리되었습니다.", "ok")
    db.commit()
    return redirect(url_for("approval_detail", doc_id=doc_id))


@app.route("/approval/<int:doc_id>/cancel", methods=["POST"])
@login_required
def approval_cancel(doc_id):
    db = get_db()
    uid = current_user()["id"]
    doc = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc or doc["drafter_id"] != uid or doc["status"] != "pending":
        abort(403)
    db.execute("UPDATE documents SET status='canceled' WHERE id=?", (doc_id,))
    db.commit()
    flash("문서를 회수(취소)했습니다.", "ok")
    return redirect(url_for("approval_detail", doc_id=doc_id))


# ---------------------------------------------------------------- mail
@app.route("/mail")
@login_required
def mail_inbox():
    db = get_db()
    uid = current_user()["id"]
    box = request.args.get("box", "inbox")
    if box == "sent":
        mails = db.execute("""
            SELECT m.*, GROUP_CONCAT(u.name, ', ') AS to_names FROM messages m
            JOIN message_recipients mr ON mr.message_id=m.id
            JOIN users u ON u.id=mr.recipient_id
            WHERE m.sender_id=? GROUP BY m.id ORDER BY m.created_at DESC""", (uid,)).fetchall()
    else:
        mails = db.execute("""
            SELECT m.*, u.name AS sender_name, mr.is_read, mr.id AS mr_id FROM message_recipients mr
            JOIN messages m ON m.id=mr.message_id JOIN users u ON u.id=m.sender_id
            WHERE mr.recipient_id=? AND mr.deleted_by_recipient=0
            ORDER BY m.created_at DESC""", (uid,)).fetchall()
    return render_template("mail/inbox.html", mails=mails, box=box)


@app.route("/mail/compose", methods=["GET", "POST"])
@login_required
def mail_compose():
    db = get_db()
    uid = current_user()["id"]
    users = db.execute("SELECT id, name, dept, position FROM users WHERE is_active=1 AND id!=? ORDER BY dept, name", (uid,)).fetchall()
    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        recipients = [r for r in request.form.getlist("recipients") if r]
        if not subject or not recipients:
            flash("제목과 받는 사람을 선택하세요.", "error")
            return render_template("mail/compose.html", users=users, form=request.form)
        cur = db.execute("INSERT INTO messages (sender_id, subject, body) VALUES (?,?,?)", (uid, subject, body))
        mid = cur.lastrowid
        for rid in recipients:
            db.execute("INSERT INTO message_recipients (message_id, recipient_id) VALUES (?,?)", (mid, int(rid)))
        db.commit()
        flash("메일을 보냈습니다.", "ok")
        return redirect(url_for("mail_inbox", box="sent"))
    return render_template("mail/compose.html", users=users, form={})


@app.route("/mail/<int:msg_id>")
@login_required
def mail_view(msg_id):
    db = get_db()
    uid = current_user()["id"]
    msg = db.execute("""SELECT m.*, u.name AS sender_name, u.dept AS sender_dept
                        FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.id=?""", (msg_id,)).fetchone()
    if not msg:
        abort(404)
    recips = db.execute("""SELECT u.name FROM message_recipients mr JOIN users u ON u.id=mr.recipient_id
                           WHERE mr.message_id=?""", (msg_id,)).fetchall()
    mr = db.execute("SELECT * FROM message_recipients WHERE message_id=? AND recipient_id=?", (msg_id, uid)).fetchone()
    if msg["sender_id"] != uid and not mr:
        abort(403)
    if mr and not mr["is_read"]:
        db.execute("UPDATE message_recipients SET is_read=1, read_at=? WHERE id=?",
                   (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), mr["id"]))
        db.commit()
    return render_template("mail/view.html", msg=msg, recips=recips)


@app.route("/mail/<int:msg_id>/delete", methods=["POST"])
@login_required
def mail_delete(msg_id):
    db = get_db()
    uid = current_user()["id"]
    db.execute("UPDATE message_recipients SET deleted_by_recipient=1 WHERE message_id=? AND recipient_id=?",
               (msg_id, uid))
    db.commit()
    flash("메일을 삭제했습니다.", "ok")
    return redirect(url_for("mail_inbox"))


# ---------------------------------------------------------------- leave
def leave_summary(uid):
    """연차 부여/사용/잔여 계산.
    사용 = 수기입력(used_manual) + 승인된 휴가신청(leave_requests) + 결재완료된 연차관리 기록(leave_records)
    상신중 = 결재 대기중인 휴가신청 + 연차관리 기록"""
    db = get_db()
    u = db.execute("SELECT annual_leave, used_manual FROM users WHERE id=?", (uid,)).fetchone()
    total = u["annual_leave"] if u else 0
    manual = (u["used_manual"] if u and u["used_manual"] is not None else 0)
    used_req = db.execute("""
        SELECT COALESCE(SUM(lr.days),0) FROM leave_requests lr
        JOIN documents d ON d.id=lr.doc_id
        WHERE lr.user_id=? AND d.status='approved' AND lr.leave_type!='sick'""", (uid,)).fetchone()[0]
    pending_req = db.execute("""
        SELECT COALESCE(SUM(lr.days),0) FROM leave_requests lr
        JOIN documents d ON d.id=lr.doc_id
        WHERE lr.user_id=? AND d.status='pending' AND lr.leave_type!='sick'""", (uid,)).fetchone()[0]
    used_rec = db.execute(
        "SELECT COALESCE(SUM(days),0) FROM leave_records WHERE user_id=? AND status='approved'", (uid,)).fetchone()[0]
    pending_rec = db.execute(
        "SELECT COALESCE(SUM(days),0) FROM leave_records WHERE user_id=? AND status='pending'", (uid,)).fetchone()[0]
    used = manual + used_req + used_rec
    pending = pending_req + pending_rec
    return {"total": total, "manual": manual, "used": used, "pending": pending,
            "remain": total - used}


@app.route("/leave")
@login_required
def leave_my():
    db = get_db()
    uid = current_user()["id"]
    rows = db.execute("""
        SELECT lr.*, d.doc_number, d.status, d.title, d.id AS doc_id FROM leave_requests lr
        JOIN documents d ON d.id=lr.doc_id WHERE lr.user_id=? ORDER BY lr.start_date DESC""", (uid,)).fetchall()
    return render_template("leave/my.html", rows=rows, leave=leave_summary(uid))


@app.route("/leave/calendar")
@login_required
def leave_calendar():
    db = get_db()
    rows = db.execute("""
        SELECT lr.*, u.name, u.dept, d.status FROM leave_requests lr
        JOIN documents d ON d.id=lr.doc_id JOIN users u ON u.id=lr.user_id
        WHERE d.status IN ('approved','pending') ORDER BY lr.start_date DESC LIMIT 200""").fetchall()
    return render_template("leave/calendar.html", rows=rows)


# ---------------------------------------------------------------- 연차관리(권한)
@app.route("/leave/admin")
@leave_admin_required
def leave_admin():
    db = get_db()
    members = db.execute("""
        SELECT * FROM users WHERE status='active' AND is_active=1
        ORDER BY dept, name""").fetchall()
    rows = []
    for m in members:
        s = leave_summary(m["id"])
        rows.append({"u": m, "leave": s})
    return render_template("leave/admin.html", rows=rows)


@app.route("/leave/admin/set", methods=["POST"])
@leave_admin_required
def leave_admin_set():
    db = get_db()
    uid = request.form.get("uid")
    try:
        val = float(request.form.get("annual_leave"))
        used = float(request.form.get("used_manual") or 0)
        if val < 0 or used < 0:
            raise ValueError
    except (TypeError, ValueError):
        flash("연차/사용 일수는 0 이상의 숫자여야 합니다.", "error")
        return redirect(request.referrer or url_for("leave_admin"))
    u = db.execute("SELECT username, name FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        abort(404)
    db.execute("UPDATE users SET annual_leave=?, used_manual=? WHERE id=?", (val, used, uid))
    db.commit()
    flash(f"{u['name']}({u['username']}) 연차 부여 {val}일 · 사용 {used}일로 설정했습니다.", "ok")
    return redirect(request.referrer or url_for("leave_admin"))


@app.route("/leave/admin/<int:uid>")
@leave_admin_required
def leave_admin_detail(uid):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        abort(404)
    # 연차관리 직접 기록(상신중/결재완료)
    records = db.execute(
        "SELECT * FROM leave_records WHERE user_id=? ORDER BY COALESCE(start_date,created_at) DESC, id DESC",
        (uid,)).fetchall()
    # 직원이 올린 휴가신청(전자결재) 기록도 함께 표시(읽기 전용)
    reqs = db.execute("""
        SELECT lr.start_date, lr.end_date, lr.days, lr.reason, lr.leave_type,
               d.status AS doc_status, d.doc_number
        FROM leave_requests lr JOIN documents d ON d.id=lr.doc_id
        WHERE lr.user_id=? ORDER BY lr.start_date DESC""", (uid,)).fetchall()
    return render_template("leave/admin_detail.html", u=u, records=records, reqs=reqs,
                           leave=leave_summary(uid))


@app.route("/leave/admin/<int:uid>/add", methods=["POST"])
@leave_admin_required
def leave_admin_add(uid):
    db = get_db()
    u = db.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        abort(404)
    start = (request.form.get("start_date") or "").strip()
    end = (request.form.get("end_date") or "").strip() or start
    reason = (request.form.get("reason") or "").strip()
    try:
        days = float(request.form.get("days") or 0)
        if days <= 0:
            raise ValueError
    except (TypeError, ValueError):
        flash("사용 일수는 0보다 큰 숫자여야 합니다.", "error")
        return redirect(url_for("leave_admin_detail", uid=uid))
    if not start:
        flash("시작일을 입력하세요.", "error")
        return redirect(url_for("leave_admin_detail", uid=uid))
    db.execute("""INSERT INTO leave_records (user_id, start_date, end_date, days, reason, status)
                  VALUES (?,?,?,?,?,'pending')""", (uid, start, end, days, reason))
    db.commit()
    flash("휴가 기록을 상신했습니다. (상신중)", "ok")
    return redirect(url_for("leave_admin_detail", uid=uid))


@app.route("/leave/admin/record/<int:rid>/<action>", methods=["POST"])
@leave_admin_required
def leave_admin_record(rid, action):
    db = get_db()
    rec = db.execute("SELECT * FROM leave_records WHERE id=?", (rid,)).fetchone()
    if not rec:
        abort(404)
    uid = rec["user_id"]
    if action == "approve":
        db.execute("UPDATE leave_records SET status='approved', approved_at=datetime('now','localtime') WHERE id=?", (rid,))
        flash("결재 완료 처리했습니다. (결재완료)", "ok")
    elif action == "reopen":
        db.execute("UPDATE leave_records SET status='pending', approved_at=NULL WHERE id=?", (rid,))
        flash("상신중으로 되돌렸습니다.", "ok")
    elif action == "delete":
        db.execute("DELETE FROM leave_records WHERE id=?", (rid,))
        flash("기록을 삭제했습니다.", "ok")
    else:
        abort(400)
    db.commit()
    return redirect(url_for("leave_admin_detail", uid=uid))


# ---------------------------------------------------------------- admin
@app.route("/admin/users")
@users_required
def admin_users():
    db = get_db()
    # 가입 대기(pending)를 맨 위로, 그 다음 부서/이름 순
    users = db.execute("""
        SELECT * FROM users
        ORDER BY (status='pending') DESC, is_active DESC, dept, name""").fetchall()
    pending_cnt = db.execute("SELECT COUNT(*) FROM users WHERE status='pending'").fetchone()[0]
    return render_template("admin/users.html", users=users, pending_cnt=pending_cnt)


@app.route("/admin/users/bulk", methods=["POST"])
@users_required
def admin_users_bulk():
    action = request.form.get("action")
    ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()]
    if not ids:
        flash("선택된 직원이 없습니다. 앞쪽 체크박스를 선택하세요.", "error")
        return redirect(url_for("admin_users"))
    db = get_db()
    ph = ",".join("?" * len(ids))
    if action == "approve":
        cur = db.execute(f"UPDATE users SET status='active', is_active=1, approved_at=datetime('now','localtime') WHERE id IN ({ph}) AND status='pending'", ids)
        flash(f"{cur.rowcount}명 가입 승인 처리했습니다.", "ok")
    elif action == "lock":
        cur = db.execute(f"UPDATE users SET locked=1 WHERE id IN ({ph}) AND role!='admin'", ids)
        flash(f"{cur.rowcount}개 계정을 잠갔습니다.", "ok")
    elif action == "unlock":
        cur = db.execute(f"UPDATE users SET locked=0 WHERE id IN ({ph})", ids)
        flash(f"{cur.rowcount}개 계정을 잠금 해제했습니다.", "ok")
    elif action == "delete":
        # 관리자 계정은 삭제 불가 → 삭제 대상(직원)만 추림
        del_ids = [r[0] for r in db.execute(
            f"SELECT id FROM users WHERE id IN ({ph}) AND role!='admin'", ids).fetchall()]
        if not del_ids:
            flash("삭제할 직원이 없습니다. (관리자 계정은 삭제할 수 없습니다.)", "error")
            return redirect(url_for("admin_users"))
        d = ",".join("?" * len(del_ids))
        # 관련 기록 정리 후 직원 삭제 (FK 무결성 유지)
        db.execute(f"DELETE FROM message_recipients WHERE recipient_id IN ({d})", del_ids)
        db.execute(f"DELETE FROM messages WHERE sender_id IN ({d})", del_ids)
        db.execute(f"DELETE FROM approval_lines WHERE approver_id IN ({d})", del_ids)
        db.execute(f"DELETE FROM documents WHERE drafter_id IN ({d})", del_ids)
        db.execute(f"DELETE FROM leave_requests WHERE user_id IN ({d})", del_ids)
        db.execute(f"DELETE FROM users WHERE id IN ({d})", del_ids)
        flash(f"{len(del_ids)}명을 삭제했습니다.", "ok")
    else:
        flash("알 수 없는 작업입니다.", "error")
        return redirect(url_for("admin_users"))
    db.commit()
    return redirect(url_for("admin_users"))


@app.route("/admin/pending/<int:uid>", methods=["GET", "POST"])
@users_required
def admin_pending(uid):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=? AND status='pending'", (uid,)).fetchone()
    if not u:
        abort(404)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "reject":
            db.execute("UPDATE users SET status='rejected', is_active=0 WHERE id=?", (uid,))
            db.commit()
            flash("가입 신청을 거절했습니다.", "ok")
            return redirect(url_for("admin_users"))
        # 승인: ID(변경, 대문자) + 부서/직급 지정
        username = request.form.get("username", "").strip().upper()
        if not username:
            flash("ID를 입력하세요.", "error")
            return render_template("admin/pending.html", u=u)
        dup = db.execute("SELECT 1 FROM users WHERE username=? AND id!=?", (username, uid)).fetchone()
        if dup:
            flash("이미 사용 중인 ID입니다.", "error")
            return render_template("admin/pending.html", u=u)
        try:
            db.execute("""UPDATE users SET username=?, emp_no=?, dept=?, position=?, role=?, hire_date=?,
                          annual_leave=?, status='active', is_active=1,
                          approved_at=datetime('now','localtime') WHERE id=?""",
                       (username, request.form.get("emp_no", "").strip(),
                        request.form.get("dept", "").strip(), request.form.get("position", "").strip(),
                        request.form.get("role", "employee"), request.form.get("hire_date", "").strip() or None,
                        float(request.form.get("annual_leave") or 15), uid))
            db.commit()
        except ValueError:
            flash("연차 일수는 숫자여야 합니다.", "error")
            return render_template("admin/pending.html", u=u)
        flash(f"가입을 승인했습니다. (ID: {username})", "ok")
        return redirect(url_for("admin_users"))
    return render_template("admin/pending.html", u=u)


@app.route("/admin/users/new", methods=["GET", "POST"])
@users_required
def admin_user_new():
    if request.method == "POST":
        db = get_db()
        username = request.form.get("username", "").strip().upper()
        if not username:
            flash("아이디(ID)는 반드시 입력해야 합니다. (나머지 항목은 비워도 저장됩니다)", "error")
            return render_template("admin/user_form.html", u=request.form, mode="new")
        if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            flash("이미 존재하는 아이디입니다.", "error")
            return render_template("admin/user_form.html", u=request.form, mode="new")
        pw = request.form.get("password") or "1234"
        # 역할/권한은 관리자만 부여 (권한 상승 방지)
        editor_admin = current_user()["role"] == "admin"
        role = request.form.get("role", "employee")
        if not editor_admin or role not in ("employee", "manager", "admin"):
            role = role if role in ("employee", "manager") else "employee"
        if not editor_admin and role == "admin":
            role = "employee"
        perm_users = 1 if (editor_admin and request.form.get("perm_users")) else 0
        perm_leave = 1 if (editor_admin and request.form.get("perm_leave")) else 0
        try:
            db.execute("""INSERT INTO users (username, emp_no, ext, phone, password_hash, name, email, dept, dept2, position, job_title, role, perm_users, perm_leave, hire_date, annual_leave, approved_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))""",
                       (username, request.form.get("emp_no", "").strip(),
                        request.form.get("ext", "").strip(), format_phone(request.form.get("phone", "").strip()),
                        hashpw(pw), request.form.get("name", "").strip(),
                        request.form.get("email", "").strip(), request.form.get("dept", "").strip(),
                        request.form.get("dept2", "").strip(),
                        request.form.get("position", "").strip(), request.form.get("job_title", "").strip(),
                        role, perm_users, perm_leave,
                        request.form.get("hire_date", "").strip() or None,
                        float(request.form.get("annual_leave") or 15)))
            db.commit()
        except ValueError:
            flash("연차 일수는 숫자여야 합니다.", "error")
            return render_template("admin/user_form.html", u=request.form, mode="new")
        flash(f"직원 계정을 추가했습니다. (초기 비밀번호: {pw})", "ok")
        return redirect(url_for("admin_users"))
    return render_template("admin/user_form.html", u={"role": "employee", "annual_leave": 15}, mode="new")


@app.route("/admin/users/<int:uid>/edit", methods=["GET", "POST"])
@users_required
def admin_user_edit(uid):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        abort(404)
    if request.method == "POST":
        new_username = request.form.get("username", "").strip().upper()
        if not new_username:
            flash("아이디는 비울 수 없습니다.", "error")
            return render_template("admin/user_form.html", u=u, mode="edit")
        if db.execute("SELECT 1 FROM users WHERE username=? AND id!=?", (new_username, uid)).fetchone():
            flash("이미 사용 중인 아이디입니다.", "error")
            return render_template("admin/user_form.html", u=u, mode="edit")
        # 역할/권한은 관리자만 변경 가능 (비관리자는 기존 값 유지 → 권한 상승 방지)
        if current_user()["role"] == "admin":
            role = request.form.get("role", "employee")
            if role not in ("employee", "manager", "admin"):
                role = "employee"
            perm_users = 1 if request.form.get("perm_users") else 0
            perm_leave = 1 if request.form.get("perm_leave") else 0
        else:
            role, perm_users, perm_leave = u["role"], u["perm_users"], u["perm_leave"]
        try:
            db.execute("""UPDATE users SET username=?, emp_no=?, ext=?, name=?, email=?, phone=?, dept=?, dept2=?, position=?, job_title=?, role=?, perm_users=?, perm_leave=?, hire_date=?, annual_leave=?, is_active=? WHERE id=?""",
                       (new_username, request.form.get("emp_no", "").strip(),
                        request.form.get("ext", "").strip(),
                        request.form.get("name", "").strip(), request.form.get("email", "").strip(),
                        format_phone(request.form.get("phone", "").strip()),
                        request.form.get("dept", "").strip(), request.form.get("dept2", "").strip(),
                        request.form.get("position", "").strip(), request.form.get("job_title", "").strip(),
                        role, perm_users, perm_leave, request.form.get("hire_date", "").strip() or None,
                        float(request.form.get("annual_leave") or 15),
                        1 if request.form.get("emp_status", "active") == "active" else 0, uid))
            if request.form.get("reset_pw"):
                db.execute("UPDATE users SET password_hash=? WHERE id=?",
                           (hashpw("1234"), uid))
            db.commit()
        except ValueError:
            flash("연차 일수는 숫자여야 합니다.", "error")
            return render_template("admin/user_form.html", u=u, mode="edit")
        flash("직원 정보를 수정했습니다." + (" 비밀번호를 '1234'로 초기화했습니다." if request.form.get("reset_pw") else ""), "ok")
        return redirect(url_for("admin_users"))
    return render_template("admin/user_form.html", u=u, mode="edit")


@app.route("/admin/users/<int:uid>/lock", methods=["POST"])
@users_required
def admin_user_lock(uid):
    db = get_db()
    u = db.execute("SELECT username, locked, role FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        abort(404)
    if u["role"] == "admin" and not u["locked"]:
        flash("관리자 계정은 잠글 수 없습니다.", "error")
        return redirect(url_for("admin_users"))
    new_locked = 0 if u["locked"] else 1
    db.execute("UPDATE users SET locked=? WHERE id=?", (new_locked, uid))
    db.commit()
    flash(f"{u['username']} 계정을 " + ("잠갔습니다." if new_locked else "잠금 해제했습니다."), "ok")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:uid>/reset_pw", methods=["POST"])
@users_required
def admin_user_reset_pw(uid):
    db = get_db()
    u = db.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        abort(404)
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (hashpw("1234"), uid))
    db.commit()
    flash(f"{u['username']} 비밀번호를 '1234'로 초기화했습니다.", "ok")
    return redirect(url_for("admin_users"))


# ---------------------------------------------------------------- update
@app.route("/update")
@login_required
def update_page():
    return render_template("update.html", info=updater.UPDATE_INFO)


def _is_local_request():
    """이 요청이 서버 PC 자기 자신(로컬)에서 온 것인지 — 로그인 팝업 업데이트는 로컬만 허용"""
    return request.remote_addr in ("127.0.0.1", "::1", "localhost")


@app.route("/update/public_status")
def update_public_status():
    """로그인 전(시작 팝업)에서도 버전 확인 가능한 공개 엔드포인트"""
    info = updater.UPDATE_INFO
    return jsonify({
        "checked": updater.UPDATE_CHECKED,
        "current": version.__version__,
        "latest": info["latest"] if info else version.__version__,
        "available": bool(info),
        "is_local": _is_local_request(),          # 서버 PC 자기 자신에서 접속했는지
        "frozen": getattr(sys, "frozen", False),
    })


@app.route("/update/status")
@login_required
def update_status():
    """하단 상태바용: 최신버전 확인 상태"""
    info = updater.UPDATE_INFO
    return jsonify({
        "checked": updater.UPDATE_CHECKED,
        "current": version.__version__,
        "latest": info["latest"] if info else version.__version__,
        "available": bool(info),
        "is_admin": bool(current_user() and current_user()["role"] == "admin"),
        "frozen": getattr(sys, "frozen", False),
    })


@app.route("/update/progress")
def update_progress():
    return jsonify(updater.PROGRESS)


@app.route("/update/apply", methods=["POST"])
def update_apply():
    # 로그인 팝업/상태바에서 호출. 단, 이 서버 PC 자기 자신(로컬)에서만 허용
    # (원격 직원 PC가 서버 앱을 업데이트/재시작시키는 것 방지)
    if not _is_local_request():
        return jsonify({"ok": False, "error": "이 PC(서버)에서만 업데이트할 수 있습니다."})
    info = updater.UPDATE_INFO
    if not info:
        return jsonify({"ok": False, "error": "적용할 업데이트가 없습니다."})
    if not getattr(sys, "frozen", False):
        return jsonify({"ok": False, "error": "개발 모드에서는 자동 적용이 불가합니다."})
    updater.start_apply(info["download"])
    return jsonify({"ok": True})


@app.errorhandler(403)
def e403(e):
    return render_template("error.html", code=403, msg="접근 권한이 없습니다."), 403


@app.errorhandler(404)
def e404(e):
    return render_template("error.html", code=404, msg="페이지를 찾을 수 없습니다."), 404


def main():
    init_db()
    updater.check_async()          # 백그라운드 업데이트 확인
    port = 5000
    url = f"http://127.0.0.1:{port}"
    print("=" * 50)
    print(f"  더필 사내 인트라넷  v{version.__version__}")
    print(f"  접속 주소: {url}")
    print("  (종료: 이 창에서 Ctrl+C)")
    print("=" * 50)
    # frozen(exe) 실행 시 브라우저 자동 오픈
    if getattr(sys, "frozen", False):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
