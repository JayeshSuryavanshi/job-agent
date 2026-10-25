from __future__ import annotations

from typing import Any

from ..http import Http
from ..models import FormField, Job
from ..pay import from_greenhouse, from_text
from ..text import html_to_text, parse_time

API = "https://boards-api.greenhouse.io/v1/boards"
_KIND = {
    "input_text": "text",
    "textarea": "textarea",
    "input_file": "file",
    "multi_value_single_select": "select",
    "multi_value_multi_select": "multiselect",
}
_STANDARD = {
    "first_name",
    "last_name",
    "preferred_name",
    "email",
    "phone",
    "resume",
    "cover_letter",
}


def list_jobs(http: Http, slug: str, company: str) -> list[Job]:
    data = http.get_json(f"{API}/{slug}/jobs")
    jobs: list[Job] = []
    for j in (data or {}).get("jobs") or []:
        job_id = str(j["id"])
        hosted = f"https://job-boards.greenhouse.io/{slug}/jobs/{job_id}"
        jobs.append(
            Job(
                source="greenhouse",
                company=company,
                title=(j.get("title") or "").strip(),
                location=((j.get("location") or {}).get("name") or "").strip(),
                url=j.get("absolute_url") or hosted,
                apply_url=hosted,
                ats="greenhouse",
                ats_slug=slug,
                ats_job_id=job_id,
                posted_at=parse_time(j.get("first_published") or j.get("updated_at")),
            )
        )
    return jobs


def enrich(http: Http, job: Job) -> bool:
    detail = http.get_json(
        f"{API}/{job.ats_slug}/jobs/{job.ats_job_id}",
        params={"questions": "true", "pay_transparency": "true"},
    )
    if not isinstance(detail, dict):
        return False
    job.raw["detail"] = detail
    job.description = html_to_text(detail.get("content"))
    job.pay = from_greenhouse(detail.get("pay_input_ranges")) or from_text(job.description)
    job.posted_at = parse_time(detail.get("first_published")) or job.posted_at
    return True


def form_fields(job: Job) -> list[FormField] | None:
    detail = job.raw.get("detail")
    if not isinstance(detail, dict):
        return None
    out: list[FormField] = []
    for q in detail.get("questions") or []:
        field = _pick(q.get("fields") or [])
        kind = _KIND.get(field.get("type", "")) if field else None
        if not field or not kind:
            continue
        name = field["name"]
        out.append(
            FormField(
                key=name,
                label=(q.get("label") or "").strip(),
                kind=kind,
                required=bool(q.get("required")),
                options=[(v.get("label") or "").strip() for v in field.get("values") or []],
                section="standard" if name in _STANDARD else "custom",
                description=html_to_text(q.get("description")),
            )
        )
    for block in detail.get("compliance") or []:
        for q in block.get("questions") or []:
            for field in q.get("fields") or []:
                kind = _KIND.get(field.get("type", ""))
                if not kind:
                    continue
                out.append(
                    FormField(
                        key=field["name"],
                        label=(q.get("label") or field["name"]).strip(),
                        kind=kind,
                        required=bool(q.get("required")),
                        options=[(v.get("label") or "").strip() for v in field.get("values") or []],
                        section="eeo",
                    )
                )
    demographic = detail.get("demographic_questions")
    if isinstance(demographic, dict):
        for q in demographic.get("questions") or []:
            multi = q.get("type") == "multi_value_multi_select"
            out.append(
                FormField(
                    key=f"demographic_{q.get('id')}",
                    label=(q.get("label") or "").strip(),
                    kind="multiselect" if multi else "select",
                    required=bool(q.get("required")),
                    options=[(o.get("label") or "").strip() for o in q.get("answer_options") or []],
                    section="eeo",
                )
            )
    for item in detail.get("data_compliance") or []:
        if item.get("requires_consent") or item.get("requires_processing_consent"):
            out.append(
                FormField(
                    key=f"consent_{item.get('type')}",
                    label=f"{str(item.get('type')).upper()} data processing consent",
                    kind="boolean",
                    required=True,
                    section="consent",
                )
            )
    return out


def _pick(fields: list[dict[str, Any]]) -> dict[str, Any] | None:
    for f in fields:
        if f.get("type") == "input_file":
            return f
    return fields[0] if fields else None
