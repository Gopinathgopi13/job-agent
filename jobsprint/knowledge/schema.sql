CREATE TABLE IF NOT EXISTS kb_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT NOT NULL UNIQUE,
    canonical_question TEXT NOT NULL,
    question_variants TEXT NOT NULL DEFAULT '[]',
    answer TEXT,
    source TEXT NOT NULL CHECK(source IN ('static_profile', 'user_taught', 'computed')),
    profile_field TEXT,
    usage_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kb_question_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_question TEXT NOT NULL,
    matched_entry_id INTEGER REFERENCES kb_entries(id) ON DELETE SET NULL,
    match_score REAL,
    decision TEXT NOT NULL CHECK(decision IN ('auto', 'confirmed', 'user_taught', 'skipped', 'timeout', 'auto_skill', 'auto_default')),
    answer_given TEXT,
    job_context TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datetime TEXT NOT NULL,
    company TEXT,
    job_role TEXT,
    experience TEXT,
    salary TEXT,
    posted_date TEXT,
    naukri_url TEXT UNIQUE,
    external_url TEXT,
    application_type TEXT NOT NULL CHECK(application_type IN ('direct', 'external', 'skipped')),
    status TEXT NOT NULL,
    site TEXT
);

CREATE INDEX IF NOT EXISTS idx_question_log_created ON kb_question_log(created_at);
CREATE INDEX IF NOT EXISTS idx_applications_datetime ON applications(datetime);
