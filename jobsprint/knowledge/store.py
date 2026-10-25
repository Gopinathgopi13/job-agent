"""SQLite-backed knowledge base store.

One app.db per installation, in the app-data dir. Single connection shared
across threads (the Playwright worker thread and the FastAPI/asyncio
thread), guarded by a lock — write volume for a local single-user app is
low enough that a single connection + lock is simpler and safer than a
connection pool.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

from .seed_intents import build_seed_entries

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def _now():
    return datetime.now(timezone.utc).isoformat()


class KBStore:
    def __init__(self, db_path: str, profile: dict = None):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        with open(_SCHEMA_PATH, "r") as f:
            self._conn.executescript(f.read())
        self._conn.commit()
        self._migrate_question_log_decisions()
        self._migrate_application_site()
        self._corpus_cache = None
        if profile is not None:
            self.sync_seeds(profile)

    # ── migrations ─────────────────────────────────────────────

    def _migrate_question_log_decisions(self):
        """Widen kb_question_log.decision's CHECK constraint to cover
        'auto_skill' and 'auto_default', added after this table first
        shipped. `CREATE TABLE IF NOT EXISTS` in schema.sql only affects a
        brand-new database — an existing app.db keeps its original
        constraint forever unless the table is rebuilt, so every skill or
        yes/no-default answer on an older install hit a CHECK-constraint
        error instead of being logged.
        """
        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='kb_question_log'"
        ).fetchone()
        if not row or "auto_skill" in row["sql"]:
            return
        self._conn.executescript(
            """
            ALTER TABLE kb_question_log RENAME TO kb_question_log_old;

            CREATE TABLE kb_question_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_question TEXT NOT NULL,
                matched_entry_id INTEGER REFERENCES kb_entries(id) ON DELETE SET NULL,
                match_score REAL,
                decision TEXT NOT NULL CHECK(decision IN
                    ('auto', 'confirmed', 'user_taught', 'skipped', 'timeout',
                     'auto_skill', 'auto_default')),
                answer_given TEXT,
                job_context TEXT,
                created_at TEXT NOT NULL
            );

            INSERT INTO kb_question_log
                SELECT id, raw_question, matched_entry_id, match_score, decision,
                       answer_given, job_context, created_at
                FROM kb_question_log_old;

            DROP TABLE kb_question_log_old;

            CREATE INDEX IF NOT EXISTS idx_question_log_created ON kb_question_log(created_at);
            """
        )
        self._conn.commit()

    def _migrate_application_site(self):
        columns = {
            row[1] for row in self._conn.execute("PRAGMA table_info(applications)").fetchall()
        }
        if "site" in columns:
            return
        self._conn.execute("ALTER TABLE applications ADD COLUMN site TEXT")
        self._conn.commit()

    # ── seeding ────────────────────────────────────────────────

    def sync_seeds(self, profile: dict) -> dict:
        """Bring an existing knowledge base up to date with the seed corpus.

        Additive and idempotent, so it can run on every launch: new intents
        get inserted, and intents that already exist gain any new phrasings
        without losing the ones passive learning picked up along the way.
        Answers are never overwritten — an entry the user edited by hand
        (or taught from scratch) keeps exactly what they set.
        """
        added = updated = 0
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, tag, question_variants, source FROM kb_entries"
            ).fetchall()
            by_tag = {r["tag"]: r for r in rows}
            now = _now()

            for entry in build_seed_entries(profile):
                existing = by_tag.get(entry["tag"])
                if existing is None:
                    self._conn.execute(
                        """INSERT INTO kb_entries
                           (tag, canonical_question, question_variants, answer,
                            source, profile_field, usage_count, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                        (
                            entry["tag"], entry["canonical_question"],
                            json.dumps(entry["variants"]), entry.get("answer"),
                            entry["source"], entry.get("profile_field"), now, now,
                        ),
                    )
                    added += 1
                    continue

                if existing["source"] == "user_taught":
                    continue  # entirely the user's — leave it alone

                known = json.loads(existing["question_variants"] or "[]")
                # Phrasings that turned out to belong to a different intent
                # are dropped, or they keep matching the wrong answer.
                retired = set(entry.get("retired_variants", ()))
                kept = [v for v in known if v not in retired]
                merged = kept + [v for v in entry["variants"] if v not in kept]
                if merged != known:
                    self._conn.execute(
                        "UPDATE kb_entries SET question_variants = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(merged), now, existing["id"]),
                    )
                    updated += 1

            self._conn.commit()

        if added or updated:
            self._invalidate_corpus()
        return {"added": added, "updated": updated}

    # ── entries ────────────────────────────────────────────────

    def _row_to_dict(self, row):
        d = dict(row)
        d["question_variants"] = json.loads(d["question_variants"] or "[]")
        return d

    def get_entry(self, entry_id: int):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM kb_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            return self._row_to_dict(row) if row else None

    def list_entries(self, query: str = None, source: str = None):
        with self._lock:
            sql = "SELECT * FROM kb_entries WHERE 1=1"
            params = []
            if source:
                sql += " AND source = ?"
                params.append(source)
            if query:
                sql += " AND (canonical_question LIKE ? OR question_variants LIKE ? OR answer LIKE ?)"
                like = f"%{query}%"
                params += [like, like, like]
            sql += " ORDER BY updated_at DESC"
            rows = self._conn.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_corpus(self):
        """(entry_id, variant_text) pairs for every phrasing in the KB, cached."""
        if self._corpus_cache is not None:
            return self._corpus_cache
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, canonical_question, question_variants FROM kb_entries"
            ).fetchall()
        corpus = []
        for row in rows:
            corpus.append((row["id"], row["canonical_question"]))
            for variant in json.loads(row["question_variants"] or "[]"):
                corpus.append((row["id"], variant))
        self._corpus_cache = corpus
        return corpus

    def _invalidate_corpus(self):
        self._corpus_cache = None

    def add_variant(self, entry_id: int, phrase: str):
        with self._lock:
            row = self._conn.execute(
                "SELECT question_variants FROM kb_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if not row:
                return
            variants = json.loads(row["question_variants"] or "[]")
            if phrase not in variants:
                variants.append(phrase)
                self._conn.execute(
                    "UPDATE kb_entries SET question_variants = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(variants), _now(), entry_id),
                )
                self._conn.commit()
        self._invalidate_corpus()

    def touch_usage(self, entry_id: int):
        with self._lock:
            now = _now()
            self._conn.execute(
                "UPDATE kb_entries SET usage_count = usage_count + 1, last_used_at = ? WHERE id = ?",
                (now, entry_id),
            )
            self._conn.commit()

    def create_user_taught(self, question: str, answer: str, tag: str = None):
        now = _now()
        tag = tag or ("user::" + "_".join(question.lower().split())[:60])
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO kb_entries
                   (tag, canonical_question, question_variants, answer,
                    source, profile_field, usage_count, last_used_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'user_taught', NULL, 1, ?, ?, ?)""",
                (tag, question, json.dumps([question]), answer, now, now, now),
            )
            self._conn.commit()
            entry_id = cur.lastrowid
        self._invalidate_corpus()
        return self.get_entry(entry_id)

    def update_entry(self, entry_id: int, answer: str = None, canonical_question: str = None):
        fields, params = [], []
        if answer is not None:
            fields.append("answer = ?")
            params.append(answer)
        if canonical_question is not None:
            fields.append("canonical_question = ?")
            params.append(canonical_question)
        if not fields:
            return self.get_entry(entry_id)
        fields.append("updated_at = ?")
        params.append(_now())
        params.append(entry_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE kb_entries SET {', '.join(fields)} WHERE id = ?", params
            )
            self._conn.commit()
        self._invalidate_corpus()
        return self.get_entry(entry_id)

    def delete_entry(self, entry_id: int):
        with self._lock:
            self._conn.execute("DELETE FROM kb_entries WHERE id = ?", (entry_id,))
            self._conn.commit()
        self._invalidate_corpus()

    # ── question log ───────────────────────────────────────────

    def log_question(self, raw_question, matched_entry_id, match_score, decision,
                      answer_given, job_context: dict = None):
        with self._lock:
            self._conn.execute(
                """INSERT INTO kb_question_log
                   (raw_question, matched_entry_id, match_score, decision,
                    answer_given, job_context, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (raw_question, matched_entry_id, match_score, decision,
                 answer_given, json.dumps(job_context or {}), _now()),
            )
            self._conn.commit()

    def list_question_log(self, limit: int = 50, offset: int = 0):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM kb_question_log ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_learned(self):
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM kb_entries WHERE source = 'user_taught'"
            ).fetchone()[0]

    # ── applications ───────────────────────────────────────────

    def insert_application(self, record: dict):
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO applications
                   (datetime, company, job_role, experience, salary, posted_date,
                    naukri_url, external_url, application_type, status, site)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("datetime", _now()), record.get("company"),
                    record.get("job_role"), record.get("experience"),
                    record.get("salary"), record.get("posted_date"),
                    record.get("naukri_url"), record.get("external_url"),
                    record["application_type"], record["status"],
                    record.get("site") or "",
                ),
            )
            self._conn.commit()

    def update_application_status(self, naukri_url: str, status: str):
        with self._lock:
            self._conn.execute(
                "UPDATE applications SET status = ? WHERE naukri_url = ?",
                (status, naukri_url),
            )
            self._conn.commit()

    def list_applications(self, limit: int = 50, offset: int = 0, status: str = None):
        with self._lock:
            sql = "SELECT * FROM applications"
            params = []
            if status:
                sql += " WHERE status = ?"
                params.append(status)
            sql += " ORDER BY datetime DESC LIMIT ? OFFSET ?"
            params += [limit, offset]
            rows = self._conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def count_applications(self, application_type: str = None):
        with self._lock:
            sql = "SELECT COUNT(*) FROM applications"
            params = []
            if application_type:
                sql += " WHERE application_type = ?"
                params.append(application_type)
            return self._conn.execute(sql, params).fetchone()[0]

    def close(self):
        with self._lock:
            self._conn.close()
