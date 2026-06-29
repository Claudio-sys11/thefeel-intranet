-- 사내 인트라넷 데이터베이스 스키마
PRAGMA foreign_keys = ON;

-- 직원 / 사용자
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,          -- 로그인 아이디(ID)
    password_hash TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    emp_no        TEXT,                             -- 사번
    ext           TEXT,                             -- 내선번호
    phone         TEXT,                             -- 전화번호
    email         TEXT,
    dept          TEXT,                             -- 부서(1)
    dept2         TEXT,                             -- 부서(2)
    position      TEXT,                             -- 직급
    job_title     TEXT,                             -- 직책
    role          TEXT    NOT NULL DEFAULT 'employee', -- admin | manager | employee
    perm_users    INTEGER NOT NULL DEFAULT 0,          -- 직원관리 권한
    perm_leave    INTEGER NOT NULL DEFAULT 0,          -- 연차관리 권한
    status        TEXT    NOT NULL DEFAULT 'active',   -- pending | active | rejected
    locked        INTEGER NOT NULL DEFAULT 0,          -- 계정 잠금(1=잠금, 로그인 불가)
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

-- 연차관리 직접 기록 (관리자가 상세에서 날짜로 입력 → 상신중/결재완료)
CREATE TABLE IF NOT EXISTS leave_records (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    start_date TEXT,                              -- 시작일 (YYYY-MM-DD)
    end_date   TEXT,                              -- 종료일 (YYYY-MM-DD)
    days       REAL    NOT NULL DEFAULT 0,        -- 사용 일수
    reason     TEXT,                              -- 사유
    status     TEXT    NOT NULL DEFAULT 'adjusted',-- adjusted(조정 기록, 즉시 반영)
    created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    approved_at TEXT,
    updated_at TEXT,                              -- 수정 일시
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 앱 설정(키-값): SMTP 외부 발신 설정 등
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- 사내 메일 / 쪽지
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id  INTEGER NOT NULL,
    subject    TEXT    NOT NULL,
    body       TEXT,
    ext_to     TEXT,                             -- 외부 수신 이메일(쉼표 구분)
    ext_cc     TEXT,                             -- 외부 참조 이메일
    created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (sender_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS message_recipients (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id   INTEGER NOT NULL,
    recipient_id INTEGER NOT NULL,
    rcpt_type    TEXT    NOT NULL DEFAULT 'to',   -- to(수신) | cc(참조) | bcc(숨은참조)
    is_read      INTEGER NOT NULL DEFAULT 0,
    read_at      TEXT,
    deleted_by_recipient INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (message_id)   REFERENCES messages(id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_id) REFERENCES users(id)
);

-- 메일 첨부파일
CREATE TABLE IF NOT EXISTS message_attachments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  INTEGER NOT NULL,
    filename    TEXT    NOT NULL,                 -- 원본 파일명
    stored_name TEXT    NOT NULL,                 -- 저장 파일명(attachments 폴더)
    size        INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
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
