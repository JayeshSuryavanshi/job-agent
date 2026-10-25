from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup, Tag

from ..http import Http
from ..models import FormField, Job
from ..pay import from_lever, from_text
from ..text import html_to_text

API = "https://api.lever.co/v0/postings"
_STANDARD = {
    "name": ("Full name", "text"),
    "email": ("Email", "email"),
    "phone": ("Phone", "phone"),
    "location": ("Current location", "location"),
    "org": ("Current company", "text"),
    "resume": ("Resume/CV", "file"),
    "urls[LinkedIn]": ("LinkedIn URL", "text"),
    "urls[GitHub]": ("GitHub URL", "text"),
    "urls[Portfolio]": ("Portfolio URL", "text"),
    "urls[Twitter]": ("Twitter URL", "text"),
    "urls[Other]": ("Other website", "text"),
    "comments": ("Additional information", "textarea"),
}
_CARD_KIND = {
    "multiple-choice": "select",
    "multiple-select": "multiselect",
    "dropdown": "select",
    "text": "text",
    "textarea": "textarea",
    "file-upload": "file",
}
_TEMPLATE = re.compile(r"^cards\[(?P<card>[^\]]+)\]\[baseTemplate\]$")


def list_jobs(http: Http, slug: str, company: str) -> list[Job]:
    data = http.get_json(f"{API}/{slug}", params={"mode": "json"})
    jobs: list[Job] = []
    for j in data or []:
        cats = j.get("categories") or {}
        places = cats.get("allLocations") or [cats.get("location") or ""]
        description = " ".join(
            [j.get("descriptionPlain") or ""]
            + [html_to_text(item.get("content")) for item in j.get("lists") or []]
            + [j.get("additionalPlain") or ""]
        ).strip()
        created = j.get("createdAt")
        jobs.append(
            Job(
                source="lever",
                company=company,
                title=(j.get("text") or "").strip(),
                location="; ".join(p for p in places if p),
                url=j.get("hostedUrl") or f"https://jobs.lever.co/{slug}/{j['id']}",
                apply_url=j.get("applyUrl") or f"https://jobs.lever.co/{slug}/{j['id']}/apply",
                ats="lever",
                ats_slug=slug,
                ats_job_id=j["id"],
                remote=j.get("workplaceType") == "remote",
                pay=from_lever(j.get("salaryRange")) or from_text(description),
                posted_at=datetime.fromtimestamp(created / 1000, tz=UTC) if created else None,
                description=description,
            )
        )
    return jobs


def form_fields(http: Http, job: Job) -> list[FormField] | None:
    response = http.get(
        job.apply_url or f"https://jobs.lever.co/{job.ats_slug}/{job.ats_job_id}/apply"
    )
    if response.status_code != 200:
        return None
    return parse_form(response.text, job)


def parse_form(markup: str, job: Job) -> list[FormField]:
    soup = BeautifulSoup(markup, "html.parser")
    form = soup.find("form") or soup
    required = _required_names(form)
    out: list[FormField] = []
    for name, (label, kind) in _STANDARD.items():
        if form.find(attrs={"name": name}) is not None:
            out.append(FormField(name, label, kind, name in required, section="standard"))
    for hidden in form.find_all("input", attrs={"name": _TEMPLATE}):
        match = _TEMPLATE.match(str(hidden.get("name")))
        try:
            template = json.loads(str(hidden.get("value") or "{}"))
        except ValueError:
            continue
        for i, f in enumerate(template.get("fields") or []):
            out.append(
                FormField(
                    key=f"cards[{match.group('card')}][field{i}]" if match else f"card_field{i}",
                    label=(f.get("text") or "").strip(),
                    kind=_CARD_KIND.get(f.get("type", ""), "text"),
                    required=bool(f.get("required")),
                    options=[(o.get("text") or "").strip() for o in f.get("options") or []],
                    section="custom",
                    description=(f.get("description") or "").strip(),
                )
            )
    for select in form.find_all("select", attrs={"name": re.compile(r"^eeo\[")}):
        name = str(select.get("name"))
        options = [o.get_text(strip=True) for o in select.find_all("option") if o.get("value")]
        out.append(FormField(name, name[4:-1], "select", False, options, section="eeo"))
    if form.find(class_="h-captcha") is not None:
        job.raw["captcha"] = "hCaptcha"
    return out


def _required_names(form: Tag | BeautifulSoup) -> set[str]:
    names: set[str] = set()
    for el in form.find_all(["input", "textarea", "select"]):
        name = el.get("name")
        if not name:
            continue
        item = el.find_parent("li")
        if el.has_attr("required") or (item is not None and item.find(class_="required")):
            names.add(str(name))
    return names
