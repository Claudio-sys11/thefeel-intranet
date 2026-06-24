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
import sqlite3
import webbrowser
import threading
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask, g, session, request, redirect, url_for,
    render_template, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

import version
import updater

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_path(rel):
    """PyInstaller 번들 내부(templates/static) 경로"""
    return os.path.join(getattr(sys, "_MEIPASS", BASE_DIR), rel)


# 데이터(db, 설정)는 exe 옆에 영구 저장, 번들 리소스는 _MEIPASS 에서 로드
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE_DIR
DB_PATH = os.path.join(APP_DIR, "intranet.db")

app = Flask(__name__,
            template_folder=resource_path("templates"),
            static_folder=resource_path("static"))


def _load_secret():
    p = os.path.join(APP_DIR, "secret.key")
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


def init_db():
    first = not os.path.exists(DB_PATH)
    db = sqlite3.connect(DB_PATH)
    with open(resource_path("schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    # 최초 실행 시 관리자 계정 생성
    cur = db.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        db.execute(
            "INSERT INTO users (username, password_hash, name, email, dept, position, role, hire_date, annual_leave)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            ("admin", generate_password_hash("admin1234"), "관리자", "admin@thefeel.co.kr",
             "경영지원", "관리자", "admin", date.today().isoformat(), 15),
        )
        print(">> 관리자 계정 생성: admin / admin1234  (최초 로그인 후 비밀번호를 변경하세요)")
    db.commit()
    db.close()


# ---------------------------------------------------------------- auth
def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


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
                APP_VERSION=version.__version__, update_info=updater.UPDATE_INFO)


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


# ---------------------------------------------------------------- routes: auth
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        row = get_db().execute("SELECT * FROM users WHERE username=? AND is_active=1", (username,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            session.clear()
            session["uid"] = row["id"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    u = current_user()
    if request.method == "POST":
        cur = request.form.get("current_pw", "")
        new = request.form.get("new_pw", "")
        if not check_password_hash(u["password_hash"], cur):
            flash("현재 비밀번호가 일치하지 않습니다.", "error")
        elif len(new) < 4:
            flash("새 비밀번호는 4자 이상이어야 합니다.", "error")
        else:
            get_db().execute("UPDATE users SET password_hash=? WHERE id=?",
                             (generate_password_hash(new), u["id"]))
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
    """연차 부여/사용/잔여 계산 (승인 완료된 연차성 휴가만 차감)"""
    db = get_db()
    u = db.execute("SELECT annual_leave FROM users WHERE id=?", (uid,)).fetchone()
    total = u["annual_leave"] if u else 0
    used = db.execute("""
        SELECT COALESCE(SUM(lr.days),0) FROM leave_requests lr
        JOIN documents d ON d.id=lr.doc_id
        WHERE lr.user_id=? AND d.status='approved' AND lr.leave_type!='sick'""", (uid,)).fetchone()[0]
    pending = db.execute("""
        SELECT COALESCE(SUM(lr.days),0) FROM leave_requests lr
        JOIN documents d ON d.id=lr.doc_id
        WHERE lr.user_id=? AND d.status='pending' AND lr.leave_type!='sick'""", (uid,)).fetchone()[0]
    return {"total": total, "used": used, "pending": pending, "remain": total - used}


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


# ---------------------------------------------------------------- admin
@app.route("/admin/users")
@admin_required
def admin_users():
    users = get_db().execute("SELECT * FROM users ORDER BY is_active DESC, dept, name").fetchall()
    return render_template("admin/users.html", users=users)


@app.route("/admin/users/new", methods=["GET", "POST"])
@admin_required
def admin_user_new():
    if request.method == "POST":
        db = get_db()
        username = request.form.get("username", "").strip()
        if not username or not request.form.get("name", "").strip():
            flash("아이디와 이름은 필수입니다.", "error")
            return render_template("admin/user_form.html", u=request.form, mode="new")
        if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            flash("이미 존재하는 아이디입니다.", "error")
            return render_template("admin/user_form.html", u=request.form, mode="new")
        pw = request.form.get("password") or "1234"
        try:
            db.execute("""INSERT INTO users (username, password_hash, name, email, dept, position, role, hire_date, annual_leave)
                          VALUES (?,?,?,?,?,?,?,?,?)""",
                       (username, generate_password_hash(pw), request.form.get("name").strip(),
                        request.form.get("email", "").strip(), request.form.get("dept", "").strip(),
                        request.form.get("position", "").strip(), request.form.get("role", "employee"),
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
@admin_required
def admin_user_edit(uid):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        abort(404)
    if request.method == "POST":
        try:
            db.execute("""UPDATE users SET name=?, email=?, dept=?, position=?, role=?, hire_date=?, annual_leave=?, is_active=? WHERE id=?""",
                       (request.form.get("name").strip(), request.form.get("email", "").strip(),
                        request.form.get("dept", "").strip(), request.form.get("position", "").strip(),
                        request.form.get("role", "employee"), request.form.get("hire_date", "").strip() or None,
                        float(request.form.get("annual_leave") or 15),
                        1 if request.form.get("is_active") else 0, uid))
            if request.form.get("reset_pw"):
                db.execute("UPDATE users SET password_hash=? WHERE id=?",
                           (generate_password_hash("1234"), uid))
            db.commit()
        except ValueError:
            flash("연차 일수는 숫자여야 합니다.", "error")
            return render_template("admin/user_form.html", u=u, mode="edit")
        flash("직원 정보를 수정했습니다." + (" 비밀번호를 '1234'로 초기화했습니다." if request.form.get("reset_pw") else ""), "ok")
        return redirect(url_for("admin_users"))
    return render_template("admin/user_form.html", u=u, mode="edit")


# ---------------------------------------------------------------- update
@app.route("/update")
@login_required
def update_page():
    return render_template("update.html", info=updater.UPDATE_INFO)


@app.route("/update/apply", methods=["POST"])
@admin_required
def update_apply():
    info = updater.UPDATE_INFO
    if not info:
        flash("적용할 업데이트가 없습니다.", "error")
        return redirect(url_for("dashboard"))
    if not getattr(sys, "frozen", False):
        flash("개발 모드에서는 자동 적용이 불가합니다. 릴리스 페이지에서 받으세요.", "error")
        return redirect(url_for("update_page"))
    try:
        # 새 exe 다운로드 후 교체·재시작 (성공 시 프로세스 종료)
        threading.Thread(target=updater.apply_update, args=(info["download"],), daemon=True).start()
    except Exception as e:
        flash(f"업데이트 실패: {e}", "error")
        return redirect(url_for("update_page"))
    return render_template("update.html", info=info, applying=True)


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
