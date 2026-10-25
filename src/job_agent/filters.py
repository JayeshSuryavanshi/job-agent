from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from .config import Filters, History, Limits
from .models import Job, Pay
from .text import company_key, title_key

NO_SPONSOR = re.compile(
    r"""
    (?:unable|not\ able|cannot|can\s?not|won'?t|will\ not|do\ not|does\ not|don'?t|doesn'?t
       |are\ not\ able|is\ not\ able|not\ in\ a\ position)
       \s+(?:to\s+)?(?:currently\s+|presently\s+)?
       (?:offer|provide|support|sponsor|consider\ candidates\ who\ (?:will\ )?require)\w*
       \s+(?:[\w-]+\s+){0,4}?(?:visas?|sponsorship|immigration|h-?1b|work\ authori[sz]ation)
    |no\s+(?:visa\s+|immigration\s+|employment\s+)?sponsorship
    |not\s+(?:be\s+)?(?:eligible|available)\s+for\s+(?:visa\s+|immigration\s+)?sponsorship
    |sponsorship\s+(?:is\s+|will\s+)?not\s+(?:be\s+)?(?:available|offered|provided|possible)
    |without\s+(?:the\s+)?(?:need\s+for\s+|requiring\s+)?(?:current\s+or\s+future\s+|future\s+)?
       (?:visa\s+|employer\s+|employment\s+)?sponsorship
    |must\s+be\s+(?:a\s+)?(?:u\.?s\.?|united\ states)\s+(?:citizen|person)
    |(?:u\.?s\.?|united\ states)\s+citizenship\s+(?:is\s+)?required
    |(?:active|current|ability\ to\ obtain(?:\ and\ maintain)?)\s+(?:an?\s+)?(?:u\.?s\.?\s+)?
       (?:government\s+)?(?:(?:secret|top\ secret|ts/sci|security)\s+){1,2}clearance
    |\bitar\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_US = re.compile(r"(?<![a-z])(us|usa|u\.s\.?|united states|north america|americas)(?![a-z])")


@dataclass
class Gate:
    filters: Filters
    history: History
    limits: Limits
    today: date
    agent_applied: dict[str, list[date]] = field(default_factory=dict)
    agent_jobs: list[tuple[str, str, str]] = field(default_factory=list)
    needs_sponsorship: bool = True

    def __post_init__(self) -> None:
        self._include = [re.compile(p, re.IGNORECASE) for p in self.filters.title_include]
        self._exclude = [re.compile(p, re.IGNORECASE) for p in self.filters.title_exclude]
        self._commute = _words(self.filters.commute_area)
        self._non_us = _words(self.filters.non_us)
        self._blocked: dict[str, str] = {}
        for block in self.history.blocked:
            if block.until is not None and block.until < self.today:
                continue
            for name in (block.company, *block.aliases):
                self._blocked[company_key(name)] = block.reason
        self._applied_ids = {a.job_id for a in self.history.applied if a.job_id}
        self._applied_titles = {
            (company_key(a.company), title_key(a.title)) for a in self.history.applied if a.title
        }
        self._applied_keys = {key for key, _, _ in self.agent_jobs}
        for _, company, title in self.agent_jobs:
            if title:
                self._applied_titles.add((company_key(company), title_key(title)))
        self._dates: dict[str, list[date | None]] = defaultdict(list)
        for past in self.history.applied:
            self._dates[company_key(past.company)].append(past.applied)
        for ck, dates in self.agent_applied.items():
            self._dates[ck].extend(dates)

    def record(self, company: str, when: date) -> None:
        self._dates[company_key(company)].append(when)

    def blocked(self, company: str) -> str | None:
        return self._blocked.get(company_key(company))

    def first_pass(self, job: Job) -> str | None:
        reason = self.blocked(job.company)
        if reason:
            return f"blocked company ({reason})"
        if not any(p.search(job.title) for p in self._include):
            return "title is not an ML/AI role"
        if any(p.search(job.title) for p in self._exclude):
            return "title excluded (level or function)"
        if not self.location_ok(job):
            return "location outside your commute area or US remote"
        history = self._history(job)
        if history:
            return history
        if not job.linkedin_id and job.posted_at is not None:
            if datetime.now(UTC) - job.posted_at > timedelta(days=self.filters.max_age_days):
                return f"posted more than {self.filters.max_age_days} days ago"
        return None

    def recheck(self, job: Job) -> str | None:
        reason = self.blocked(job.company)
        if reason:
            return f"blocked company ({reason})"
        history = self._history(job)
        if history:
            return history
        return self.pay_reason(job.pay) if job.pay is not None else None

    def _history(self, job: Job) -> str | None:
        applied_title = (company_key(job.company), title_key(job.title)) in self._applied_titles
        if job.key in self._applied_keys or job.ats_job_id in self._applied_ids or applied_title:
            return "already applied"
        if self._capped(job.company):
            return (
                f"company cap ({self.limits.per_company_max} applications per "
                f"{self.limits.per_company_window_days} days)"
            )
        return None

    def second_pass(self, job: Job) -> str | None:
        reason = self.pay_reason(job.pay)
        if reason:
            return reason
        if self.needs_sponsorship and NO_SPONSOR.search(job.description or ""):
            return "posting says no visa sponsorship"
        return None

    def pay_reason(self, pay: Pay | None) -> str | None:
        if pay is None:
            return "no posted pay range" if self.filters.require_pay else None
        if _pay_value(pay.low, pay.high, self.filters.pay_basis) <= self.filters.pay_floor:
            basis = self.filters.pay_basis
            basis = basis if basis in ("top", "bottom", "midpoint") else "top"
            return f"pay {basis} at or below ${self.filters.pay_floor // 1000}k"
        return None

    def location_ok(self, job: Job) -> bool:
        loc = job.location.lower()
        if self._commute and self._commute.search(loc):
            return True
        remote = job.remote or "remote" in loc or "anywhere" in loc
        if not (remote and self.filters.remote_ok):
            return False
        if _US.search(loc):
            return True
        return not (self._non_us and self._non_us.search(loc))

    def _capped(self, company: str) -> bool:
        since = self.today - timedelta(days=self.limits.per_company_window_days)
        dates = self._dates.get(company_key(company), [])
        recent = [d for d in dates if d is None or d >= since]
        return len(recent) >= self.limits.per_company_max


def _words(items: list[str]) -> re.Pattern[str] | None:
    if not items:
        return None
    alternatives = "|".join(re.escape(i.lower()) for i in items)
    return re.compile(rf"(?<![a-z])({alternatives})(?![a-z])")


def _pay_value(low: float | None, high: float | None, basis: str) -> float:
    top = high or low or 0.0
    bottom = low if low is not None else top
    if basis == "midpoint":
        return (bottom + top) / 2
    if basis == "bottom":
        return bottom
    return top
