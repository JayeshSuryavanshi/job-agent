from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .models import FormField, Job, Pay
from .text import company_key, linkedin_job_id, norm, url_key

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key TEXT PRIMARY KEY, source TEXT, company TEXT, title TEXT, location TEXT, url TEXT,
    apply_url TEXT, ats TEXT, ats_slug TEXT, ats_job_id TEXT, pay_low REAL, pay_high REAL,
    pay_source TEXT, posted_at TEXT, linkedin_id TEXT, first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    run_id TEXT, job_key TEXT, verdict TEXT, reason TEXT, resume TEXT, created_at TEXT,
    PRIMARY KEY (run_id, job_key)
);
CREATE TABLE IF NOT EXISTS plans (
    job_key TEXT PRIMARY KEY, run_id TEXT, status TEXT, resume TEXT, blockers TEXT,
    plan_json TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    job_key TEXT PRIMARY KEY, company TEXT, title TEXT, status TEXT, resume TEXT,
    resume_sha TEXT, intent_at TEXT, submitted_at TEXT, detail_json TEXT
);
CREATE TABLE IF NOT EXISTS unanswered (
    qkey TEXT PRIMARY KEY, label TEXT, kind TEXT, options TEXT, required INTEGER,
    jobs INTEGER, first_seen TEXT, last_seen TEXT, example TEXT
);
CREATE TABLE IF NOT EXISTS seen_questions (
    qkey TEXT, job_key TEXT, PRIMARY KEY (qkey, job_key)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def row_job(r: sqlite3.Row) -> Job:
    pay = Pay(r["pay_low"], r["pay_high"], "USD", r["pay_source"] or "") if r["pay_high"] else None
    return Job(
        source=r["source"],
        company=r["company"],
        title=r["title"],
        location=r["location"],
        url=r["url"],
        apply_url=r["apply_url"],
        ats=r["ats"],
        ats_slug=r["ats_slug"],
        ats_job_id=r["ats_job_id"],
        pay=pay,
        linkedin_id=r["linkedin_id"],
    )


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def upsert_job(self, job: Job) -> None:
        pay = job.pay
        stamp = _now()
        self.db.execute(
            """INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET title=excluded.title, location=excluded.location,
                 pay_low=excluded.pay_low, pay_high=excluded.pay_high,
                 pay_source=excluded.pay_source, last_seen=excluded.last_seen,
                 linkedin_id=COALESCE(excluded.linkedin_id, jobs.linkedin_id)""",
            (
                job.key,
                job.source,
                job.company,
                job.title,
                job.location,
                job.url,
                job.apply_url,
                job.ats,
                job.ats_slug,
                job.ats_job_id,
                pay.low if pay else None,
                pay.high if pay else None,
                pay.source if pay else None,
                job.posted_at.isoformat() if job.posted_at else None,
                job.linkedin_id,
                stamp,
                stamp,
            ),
        )

    def record_decision(
        self, run_id: str, job: Job, verdict: str, reason: str, resume: str | None
    ) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?)",
            (run_id, job.key, verdict, reason, resume, _now()),
        )

    def save_plan(
        self,
        run_id: str,
        job_key: str,
        status: str,
        resume: str | None,
        blockers: list[str],
        plan: dict[str, Any],
    ) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO plans VALUES (?,?,?,?,?,?,?)",
            (job_key, run_id, status, resume, json.dumps(blockers), json.dumps(plan), _now()),
        )

    def bump_unanswered(self, field: FormField, job: Job) -> None:
        qkey = f"{norm(field.label)}|{field.kind}"
        stamp = _now()
        fresh = self.db.execute(
            "INSERT OR IGNORE INTO seen_questions VALUES (?, ?)", (qkey, job.key)
        ).rowcount
        self.db.execute(
            """INSERT INTO unanswered VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(qkey) DO UPDATE SET jobs = jobs + ?, last_seen = excluded.last_seen,
                 required = MAX(required, excluded.required), options = excluded.options""",
            (
                qkey,
                field.label,
                field.kind,
                json.dumps(field.options),
                int(field.required),
                fresh,
                stamp,
                stamp,
                f"{job.company}: {job.title}",
                fresh,
            ),
        )

    def unanswered(self) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM unanswered ORDER BY required DESC, jobs DESC, label"
        ).fetchall()

    def agent_applied(self) -> dict[str, list[date]]:
        out: dict[str, list[date]] = {}
        for row in self.db.execute("SELECT company, intent_at FROM applications").fetchall():
            when = datetime.fromisoformat(row["intent_at"]).date()
            out.setdefault(company_key(row["company"]), []).append(when)
        return out

    def applied_jobs(self) -> list[tuple[str, str, str]]:
        rows = self.db.execute("SELECT job_key, company, title FROM applications").fetchall()
        return [(r["job_key"], r["company"], r["title"] or "") for r in rows]

    def find_job(self, ref: str) -> sqlite3.Row | None:
        want = url_key(ref)
        linkedin_id = linkedin_job_id(ref)
        for row in self.db.execute("SELECT * FROM jobs ORDER BY last_seen DESC"):
            if ref == row["key"] or (linkedin_id and row["linkedin_id"] == linkedin_id):
                return row
            if want and want in (url_key(row["url"]), url_key(row["apply_url"])):
                return row
        return None

    def plan(self, job_key: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM plans WHERE job_key = ?", (job_key,)).fetchone()

    def record(
        self,
        job: Job,
        status: str,
        resume: str | None,
        resume_sha: str | None,
        detail: dict[str, Any],
    ) -> bool:
        stamp = _now()
        submitted = stamp if status == "submitted" else None
        cursor = self.db.execute(
            "INSERT OR IGNORE INTO applications VALUES (?,?,?,?,?,?,?,?,?)",
            (
                job.key,
                job.company,
                job.title,
                status,
                resume,
                resume_sha,
                stamp,
                submitted,
                json.dumps(detail),
            ),
        )
        self.db.commit()
        return cursor.rowcount == 1

    def application(self, job_key: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM applications WHERE job_key = ?", (job_key,)
        ).fetchone()

    def sent_on(self, day: date) -> int:
        rows = self.db.execute("SELECT intent_at FROM applications").fetchall()
        return sum(
            1 for r in rows if datetime.fromisoformat(r["intent_at"]).astimezone().date() == day
        )

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.commit()
        self.db.close()
