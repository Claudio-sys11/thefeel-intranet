-- 사내 인트라넷 데이터베이스 스키마
PRAGMA foreign_keys = ON;

-- 직원 / 사용자
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,          -- 로그인 아이디(ID)
    password_hash TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    emp_no        TEXT,                             -- 사번
    phone         TEXT,                             -- 전화번호
    email         TEXT,
    dept          TEXT,                             -- 부서
    position      TEXT,                             -- 직급
    role          TEXT    NOT NULL DEFAULT 'employee', -- admin | employee
    status        TEXT    NOT NULL DEFAULT 'active',   -- pending | active | rejected
    hire_date     TEXT,                             -- 입사일 (YYYY-MM-DD)
    annual_leave  REAL    NOT NULL DEFAULT 15,      -- 연간 부여 연차(일)
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 전자결재 문서
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_number  TEXT    NOT NULL UNIQUE,            -- 문서번호
    drafter_id  INTEGER NOT NULL,                   -- 기안자
    doc_type    TEXT    NOT NULL,                   -- general | expense | leave | purchase
    title       TEXT    NOT NULL,
    content     TEXT,
    status      TEXT    NOT NULL DEFAULT 'pending', -- pending | approved | rejected | canceled
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    completed_at TEXT,
    FOREIGN KEY (drafter_id) REFERENCES users(id)
);

-- 결재선 (문서별 결재자 순서)
CREATE TABLE IF NOT EXISTS approval_lines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id      INTEGER NOT NULL,
    approver_id INTEGER NOT NULL,
    step_order  INTEGER NOT NULL,                   -- 결재 순서(1,2,3...)
    status      TEXT    NOT NULL DEFAULT 'waiting', -- waiting | pending | approved | rejected
    comment     TEXT,
    acted_at    TEXT,
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (approver_id) REFERENCES users(id)
);

-- 연차/휴가 신청 (결재 문서와 연결)
CREATE TABLE IF NOT EXISTS leave_requests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id     INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    leave_type TEXT    NOT NULL,                    -- annual | half_am | half_pm | sick
    start_date TEXT    NOT NULL,
    end_date   TEXT    NOT NULL,
    days       REAL    NOT NULL,                    -- 사용 일수
    reason     TEXT,
    FOREIGN KEY (doc_id)  REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 사내 메일 / 쪽지
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id  INTEGER NOT NULL,
    subject    TEXT    NOT NULL,
    body       TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (sender_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS message_recipients (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id   INTEGER NOT NULL,
    recipient_id INTEGER NOT NULL,
    is_read      INTEGER NOT NULL DEFAULT 0,
    read_at      TEXT,
    deleted_by_recipient INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (message_id)   REFERENCES messages(id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_id) REFERENCES users(id)
);

-- 공지사항
CREATE TABLE IF NOT EXISTS notices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id  INTEGER NOT NULL,
    title      TEXT    NOT NULL,
    content    TEXT,
    is_pinned  INTEGER NOT NULL DEFAULT 0,            -- 상단 고정
    created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (author_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_lines_approver ON approval_lines(approver_id, status);
CREATE INDEX IF NOT EXISTS idx_recip ON message_recipients(recipient_id, is_read);
