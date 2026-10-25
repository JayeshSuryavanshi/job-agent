from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .answers import Answerer
from .http import Http
from .models import FormField, Job
from .sources import ashby, greenhouse, lever

AI_BAN = re.compile(
    r"\b(do not|don't|must not|may not|should not|cannot) use (any )?(ai|artificial intelligence"
    r"|chatgpt|generative ai|llms?)\b|\bai[- ]generated (content|answers|responses|applications)"
    r" (will|may)\b|\bwithout (the )?(use|help|assistance) of"
    r" (ai|artificial intelligence|chatgpt)\b",
    re.IGNORECASE,
)


@dataclass
class PlannedField:
    key: str
    label: str
    kind: str
    required: bool
    section: str
    status: str
    source: str
    value: Any = None
    options: list[str] = field(default_factory=list)


@dataclass
class Plan:
    job_key: str
    status: str
    resume: str | None
    fields: list[PlannedField] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def fetch_fields(http: Http, job: Job) -> list[FormField] | None:
    if job.ats == "greenhouse":
        if "detail" not in job.raw and not greenhouse.enrich(http, job):
            return None
        return greenhouse.form_fields(job)
    if job.ats == "ashby":
        return ashby.form_fields(http, job)
    if job.ats == "lever":
        return lever.form_fields(http, job)
    return None


def build_plan(
    http: Http, job: Job, answerer: Answerer, resume: str
) -> tuple[Plan, list[FormField]]:
    fields = fetch_fields(http, job)
    if fields is None:
        return Plan(job.key, "error", resume, blockers=["could not read the application form"]), []
    plan = Plan(job.key, "ready", resume)
    unanswered: list[FormField] = []
    for f in fields:
        r = answerer.resolve(f, job)
        plan.fields.append(
            PlannedField(
                f.key,
                f.label,
                f.kind,
                f.required,
                f.section,
                r.status,
                r.source,
                r.value,
                f.options,
            )
        )
        if r.status == "blocked":
            plan.blockers.append(f"decide: {f.label}")
        elif r.status == "unknown":
            plan.blockers.append(f"answer: {f.label}")
        if r.status in ("unknown", "blank") and (
            r.source == "none" or r.source.endswith("(no matching option)")
        ):
            unanswered.append(f)
    if AI_BAN.search(job.description):
        plan.blockers.append("decide: the posting restricts AI use in applications")
    if job.raw.get("captcha"):
        plan.notes.append(f"form has {job.raw['captcha']}; you may have to solve it at Submit")
    if any(b.startswith("decide:") for b in plan.blockers):
        plan.status = "blocked"
    elif plan.blockers:
        plan.status = "needs_answers"
    return plan, unanswered
