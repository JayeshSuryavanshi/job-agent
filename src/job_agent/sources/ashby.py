from __future__ import annotations

from ..http import Http
from ..models import FormField, Job
from ..pay import from_ashby, from_text
from ..text import html_to_text, parse_time

API = "https://api.ashbyhq.com/posting-api/job-board"
GRAPHQL = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting"
_QUERY = (
    "query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {"
    " jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName,"
    " jobPostingId: $jobPostingId) { id title applicationForm { sections { title"
    " fieldEntries { field isRequired descriptionHtml } } } } }"
)
_KIND = {
    "String": "text",
    "Email": "email",
    "Phone": "phone",
    "File": "file",
    "Location": "location",
    "ValueSelect": "select",
    "MultiValueSelect": "multiselect",
    "Boolean": "boolean",
    "LongText": "textarea",
    "Date": "date",
    "Number": "number",
}


def list_jobs(http: Http, org: str, company: str) -> list[Job]:
    data = http.get_json(f"{API}/{org}", params={"includeCompensation": "true"})
    jobs: list[Job] = []
    for j in (data or {}).get("jobs") or []:
        if j.get("isListed") is False:
            continue
        places = [j.get("location") or ""]
        for extra in j.get("secondaryLocations") or []:
            if isinstance(extra, dict):
                places.append(extra.get("location") or "")
        description = j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml"))
        jobs.append(
            Job(
                source="ashby",
                company=company,
                title=(j.get("title") or "").strip(),
                location="; ".join(p for p in places if p),
                url=j.get("jobUrl") or f"https://jobs.ashbyhq.com/{org}/{j['id']}",
                apply_url=j.get("applyUrl")
                or f"https://jobs.ashbyhq.com/{org}/{j['id']}/application",
                ats="ashby",
                ats_slug=org,
                ats_job_id=j["id"],
                remote=bool(j.get("isRemote")),
                pay=from_ashby(j.get("compensation")) or from_text(description),
                posted_at=parse_time(j.get("publishedAt")),
                description=description,
            )
        )
    return jobs


def form_fields(http: Http, job: Job) -> list[FormField] | None:
    data = http.post_json(
        GRAPHQL,
        {
            "operationName": "ApiJobPosting",
            "query": _QUERY,
            "variables": {
                "organizationHostedJobsPageName": job.ats_slug,
                "jobPostingId": job.ats_job_id,
            },
        },
    )
    posting = ((data or {}).get("data") or {}).get("jobPosting")
    if not posting:
        return None
    out: list[FormField] = []
    for section in (posting.get("applicationForm") or {}).get("sections") or []:
        for entry in section.get("fieldEntries") or []:
            field = entry.get("field") or {}
            kind = _KIND.get(field.get("type", ""))
            path = field.get("path") or field.get("id") or ""
            if not kind or not path:
                continue
            out.append(
                FormField(
                    key=path,
                    label=(field.get("title") or "").strip(),
                    kind=kind,
                    required=bool(entry.get("isRequired")),
                    options=[
                        (v.get("label") or "").strip() for v in field.get("selectableValues") or []
                    ],
                    section="standard" if path.startswith("_systemfield_") else "custom",
                    description=html_to_text(entry.get("descriptionHtml")),
                )
            )
    return out
