from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Pay:
    low: float | None
    high: float | None
    currency: str = "USD"
    source: str = ""

    def label(self) -> str:
        def k(v: float | None) -> str:
            return "?" if v is None else f"${v / 1000:,.0f}k"

        return f"{k(self.low)}-{k(self.high)}"


@dataclass
class Job:
    source: str
    company: str
    title: str
    location: str
    url: str
    apply_url: str | None = None
    ats: str | None = None
    ats_slug: str | None = None
    ats_job_id: str | None = None
    remote: bool = False
    pay: Pay | None = None
    posted_at: datetime | None = None
    description: str = ""
    linkedin_id: str | None = None
    linkedin_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def key(self) -> str:
        if self.ats and self.ats_slug and self.ats_job_id:
            return f"{self.ats}:{self.ats_slug}:{self.ats_job_id}"
        if self.linkedin_id:
            return f"linkedin:{self.linkedin_id}"
        return f"{self.source}:{self.url}"


@dataclass
class FormField:
    key: str
    label: str
    kind: str
    required: bool
    options: list[str] = field(default_factory=list)
    section: str = "custom"
    description: str = ""
