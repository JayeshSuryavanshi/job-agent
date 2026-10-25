from __future__ import annotations

import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .answers import Answerer
from .boards import Boards
from .config import Config
from .filters import Gate
from .http import Http, RateLimited
from .models import Job
from .planner import Plan, build_plan
from .resumes import Pick, pick
from .sources import greenhouse
from .store import Store

Log = Callable[[str], None]


@dataclass
class RunResult:
    run_id: str
    started: datetime
    boards_read: int = 0
    board_jobs: int = 0
    survivors: int = 0
    plans: list[tuple[Job, Pick, Plan]] = field(default_factory=list)
    skipped: dict[str, list[Job]] = field(default_factory=lambda: defaultdict(list))
    unplanned: list[Job] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    requests: int = 0


def _stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def run(cfg: Config, log: Log = _stderr) -> RunResult:
    started = datetime.now(UTC)
    result = RunResult(started.strftime("%Y%m%dT%H%M%SZ"), started)
    http = Http()
    store = Store(cfg.data_dir / "jobagent.db")
    boards = Boards(http)
    gate = Gate(
        cfg.search.filters,
        cfg.history,
        cfg.search.limits,
        started.date(),
        store.agent_applied(),
        store.applied_jobs(),
        cfg.persona.work_auth.needs_sponsorship,
    )
    jobs: dict[str, Job] = {}
    try:
        _read_watchlist(cfg, boards, gate, jobs, result, log)
        survivors = _filter(http, gate, store, jobs, result, log)
        _plan(cfg, http, store, survivors, result, log)
    finally:
        result.requests = http.requests
        store.close()
        http.close()
    return result


def _read_watchlist(
    cfg: Config, boards: Boards, gate: Gate, jobs: dict[str, Job], result: RunResult, log: Log
) -> None:
    for c in cfg.watchlist.companies:
        if not (c.enabled and c.ats and c.slug) or gate.blocked(c.name):
            continue
        try:
            found = boards.jobs(c.ats, c.slug, c.name)
        except Exception as exc:
            result.errors.append(f"{c.name} board: {type(exc).__name__}: {exc}")
            continue
        result.boards_read += 1
        result.board_jobs += len(found)
        for job in found:
            jobs.setdefault(job.key, job)
    log(f"company boards: {result.board_jobs} open roles on {result.boards_read} boards")


def _filter(
    http: Http, gate: Gate, store: Store, jobs: dict[str, Job], result: RunResult, log: Log
) -> list[Job]:
    first: list[Job] = []
    for job in jobs.values():
        reason = gate.first_pass(job)
        if reason:
            result.skipped[reason].append(job)
        else:
            first.append(job)
    log(f"filters: {len(first)} roles pass title, location, history and age; reading postings")
    survivors: list[Job] = []
    for job in first:
        if job.ats == "greenhouse" and "detail" not in job.raw:
            try:
                ok = greenhouse.enrich(http, job)
            except RateLimited:
                ok = False
            except Exception as exc:
                result.errors.append(f"{job.company} / {job.title}: {type(exc).__name__}: {exc}")
                continue
            if not ok:
                result.skipped["posting could not be read"].append(job)
                continue
        store.upsert_job(job)
        reason = gate.second_pass(job)
        if reason:
            result.skipped[reason].append(job)
        else:
            survivors.append(job)
    survivors.sort(key=lambda j: -(j.posted_at.timestamp() if j.posted_at else 0))
    result.survivors = len(survivors)
    log(f"filters: {len(survivors)} roles clear the pay and sponsorship checks")
    return survivors


def _plan(
    cfg: Config, http: Http, store: Store, survivors: list[Job], result: RunResult, log: Log
) -> None:
    answerer = Answerer(
        cfg.persona,
        cfg.answers,
        cfg.history,
        result.started.date(),
        cfg.search.filters.commute_area,
    )
    cap = cfg.search.limits.max_plans_per_run
    for job in survivors[:cap]:
        choice = pick(job, cfg.resumes)
        try:
            plan, unanswered = build_plan(http, job, answerer, choice.variant)
        except Exception as exc:
            result.errors.append(f"{job.company} / {job.title}: {type(exc).__name__}: {exc}")
            continue
        store.save_plan(
            result.run_id, job.key, plan.status, plan.resume, plan.blockers, plan.to_json()
        )
        store.record_decision(
            result.run_id, job, plan.status, "; ".join(plan.blockers), plan.resume
        )
        for f in unanswered:
            store.bump_unanswered(f, job)
        result.plans.append((job, choice, plan))
    result.unplanned = survivors[cap:]
    counts = Counter(p.status for _, _, p in result.plans)
    log(
        f"plans: {counts['ready']} ready, {counts['needs_answers']} need your answers, "
        f"{counts['blocked']} need your decision, {counts['error']} unreadable forms"
    )
