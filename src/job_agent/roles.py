from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .answers import AFFIRM, DECLINE, RESUME
from .config import Config
from .filters import Gate
from .models import Job
from .pay import from_text
from .resumes import path_for, sha1
from .store import Store, row_job
from .text import linkedin_job_id

_MARKS = {"answered": "ok", "blank": "--", "unknown": "??", "blocked": "!!"}


def gate_for(cfg: Config, store: Store, today: date) -> Gate:
    return Gate(
        cfg.search.filters,
        cfg.history,
        cfg.search.limits,
        today,
        store.agent_applied(),
        store.applied_jobs(),
        cfg.persona.work_auth.needs_sponsorship,
    )


def outside_job(ref: str, company: str, title: str, location: str, posting: str) -> Job:
    return Job(
        source="manual",
        company=company,
        title=title,
        location=location,
        url=ref,
        remote="remote" in location.lower(),
        pay=from_text(posting) if posting else None,
        description=posting,
        linkedin_id=linkedin_job_id(ref),
    )


def _value(value: Any) -> str:
    if value is None:
        return "(leave blank)"
    if value == RESUME:
        return "attach the resume file"
    if value == AFFIRM:
        return "tick it / pick the agree option"
    if value == DECLINE:
        return "pick the decline-to-answer option"
    if isinstance(value, bool):
        return "Yes (tick)" if value else "No (leave unticked)"
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


def _applied(store: Store, job: Job) -> str | None:
    row = store.application(job.key)
    if row is None:
        return None
    return f"{row['status']} on {row['intent_at'][:10]}"


def show(
    cfg: Config,
    store: Store,
    ref: str,
    today: date,
    company: str | None = None,
    title: str | None = None,
    location: str | None = None,
    posting: Path | None = None,
) -> list[str]:
    gate = gate_for(cfg, store, today)
    sent = f"sent today: {store.sent_on(today)} of {cfg.search.limits.daily_max}"
    row = store.find_job(ref)
    if row is None:
        if not (company and title):
            raise SystemExit(
                "this role is not in the database; pass --company and --title, plus --location"
                " and --posting FILE with the posting text"
            )
        text = posting.read_text() if posting else ""
        job = outside_job(ref, company, title, location or "", text)
        if posting is None:
            reason = gate.first_pass(job) or "posting not checked: pass --posting FILE"
        else:
            reason = gate.first_pass(job) or gate.second_pass(job)
        done = _applied(store, job)
        return [
            f"role: {job.company} / {job.title} ({job.location or 'location not given'})",
            f"link: {ref}",
            f"key: {job.key}",
            f"pay: {job.pay.label() if job.pay else 'no range found in the posting'}",
            f"verdict: {'SKIP: ' + reason if reason else 'OK to apply'}",
            f"applied: {done or 'no'}",
            sent,
            "plan: none saved; fill from data/persona.yaml and data/answers.yaml,"
            " then run `job-agent record`",
        ]
    job = row_job(row)
    reason = gate.recheck(job)
    lines = [
        f"role: {job.company} / {job.title} ({job.location})",
        f"form: {job.apply_url or job.url} ({job.ats})",
        f"key: {job.key}",
        f"pay: {job.pay.label() if job.pay else '?'}",
        f"verdict: {'SKIP: ' + reason if reason else 'OK to apply'}",
        f"applied: {_applied(store, job) or 'no'}",
        sent,
    ]
    saved = store.plan(job.key)
    if saved is None:
        return lines + ["plan: none saved (run `job-agent run` first)"]
    plan = json.loads(saved["plan_json"])
    how = "fill in Chrome with the values below, submit, then `job-agent record`"
    lines += [f"plan: {plan['status']} (run {saved['run_id']})", f"apply with: {how}"]
    if plan.get("resume"):
        path = path_for(cfg.resumes, cfg.data_dir, plan["resume"])
        lines.append(f"resume: {plan['resume']} -> {path}")
    lines.append("fields:")
    for f in plan["fields"]:
        need = ", required" if f["required"] else ""
        mark = _MARKS.get(f["status"], f["status"])
        lines.append(f"  [{mark}] {f['label']} ({f['kind']}{need}): {_value(f['value'])}")
        if f["status"] in ("unknown", "blocked") and f["options"]:
            lines.append(f"       options: {'; '.join(f['options'])[:400]}")
    lines += [f"blocker: {b}" for b in plan.get("blockers", [])]
    lines += [f"note: {n}" for n in plan.get("notes", [])]
    return lines


def record(
    cfg: Config,
    store: Store,
    ref: str,
    status: str,
    company: str | None = None,
    title: str | None = None,
    resume: str | None = None,
) -> tuple[bool, str]:
    row = store.find_job(ref)
    if row is not None:
        job = row_job(row)
        saved = store.plan(job.key)
        if resume is None and saved is not None:
            resume = json.loads(saved["plan_json"]).get("resume")
    elif company and title:
        job = outside_job(ref, company, title, "", "")
    else:
        raise SystemExit("this role is not in the database; pass --company and --title")
    sha = None
    if resume:
        if resume not in {v.name for v in cfg.resumes.variants}:
            raise SystemExit(f"unknown resume {resume!r}; see data/resumes.yaml")
        path = path_for(cfg.resumes, cfg.data_dir, resume)
        sha = sha1(path) if path.exists() else None
    if not store.record(job, status, resume, sha, {"url": ref, "via": "record"}):
        return False, f"already recorded: {job.company} / {job.title} ({_applied(store, job)})"
    return True, f"recorded {status}: {job.company} / {job.title} ({job.key})"
