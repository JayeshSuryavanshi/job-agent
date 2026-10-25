from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = PROJECT_ROOT / "data"
FILES = (
    "persona.yaml",
    "answers.yaml",
    "search.yaml",
    "watchlist.yaml",
    "history.yaml",
    "resumes.yaml",
)


class Name(BaseModel):
    first: str
    middle: str | None = None
    last: str
    preferred: str | None = None

    @property
    def full(self) -> str:
        return " ".join(p for p in (self.first, self.middle, self.last) if p)


class Contact(BaseModel):
    email: str
    phone: str


class Address(BaseModel):
    city: str
    state: str
    state_code: str
    country: str = "United States"
    street: str | None = None
    postal_code: str | None = None

    @property
    def city_state_country(self) -> str:
        return f"{self.city}, {self.state}, {self.country}"


class Links(BaseModel):
    linkedin: str | None = None
    website: str | None = None
    github: str | None = None


class WorkAuth(BaseModel):
    authorized_us: bool
    needs_sponsorship: bool
    visa: str | None = None


class Employment(BaseModel):
    current_company: str
    current_title: str
    past_employers: list[str] = Field(default_factory=list)


class EEO(BaseModel):
    gender: str | None = None
    race: str | None = None
    hispanic_latino: str | None = None
    veteran: str | None = None
    disability: str | None = None
    sexual_orientation: str | None = None
    transgender: str | None = None
    pronouns: str | None = None


class Office(BaseModel):
    max_days: int = 3


class Consents(BaseModel):
    arbitration: bool = False
    interview_recording: bool = False
    confidentiality: bool = False


class Persona(BaseModel):
    name: Name
    contact: Contact
    address: Address
    links: Links = Field(default_factory=Links)
    work_auth: WorkAuth
    employment: Employment
    start_notice_days: int = 14
    eeo: EEO = Field(default_factory=EEO)
    office: Office = Field(default_factory=Office)
    consents: Consents = Field(default_factory=Consents)


class AnswerEntry(BaseModel):
    id: str
    match: list[str]
    require: list[str] = Field(default_factory=list)
    unless: list[str] = Field(default_factory=list)
    answer: str | None = None
    priority: int = 0
    companies: list[str] = Field(default_factory=list)
    note: str | None = None


class AnswerBank(BaseModel):
    entries: list[AnswerEntry] = Field(default_factory=list)


class Filters(BaseModel):
    title_include: list[str]
    title_exclude: list[str] = Field(default_factory=list)
    commute_area: list[str]
    non_us: list[str] = Field(default_factory=list)
    remote_ok: bool = True
    pay_floor: int = 300_000
    pay_basis: str = "top"
    require_pay: bool = True
    max_age_days: int = 14


class Limits(BaseModel):
    per_company_window_days: int = 90
    per_company_max: int = 2
    daily_max: int = 10
    max_plans_per_run: int = 60


class SearchConfig(BaseModel):
    filters: Filters
    limits: Limits = Field(default_factory=Limits)


class WatchCompany(BaseModel):
    name: str
    ats: str | None = None
    slug: str | None = None
    enabled: bool = True


class Watchlist(BaseModel):
    companies: list[WatchCompany] = Field(default_factory=list)


class Block(BaseModel):
    company: str
    aliases: list[str] = Field(default_factory=list)
    reason: str
    until: date | None = None


class PastApplication(BaseModel):
    company: str
    title: str | None = None
    job_id: str | None = None
    applied: date | None = None


class History(BaseModel):
    blocked: list[Block] = Field(default_factory=list)
    applied: list[PastApplication] = Field(default_factory=list)


class ResumeVariant(BaseModel):
    name: str
    file: str
    source: str | None = None
    use_for: str = ""
    keywords: dict[str, int] = Field(default_factory=dict)


class ResumeRegistry(BaseModel):
    default: str = "general"
    variants: list[ResumeVariant]


class Config(BaseModel):
    data_dir: Path
    persona: Persona
    answers: AnswerBank
    search: SearchConfig
    watchlist: Watchlist
    history: History
    resumes: ResumeRegistry


def _read(path: Path) -> Any:
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def load(data_dir: Path) -> Config:
    data_dir = data_dir.expanduser().resolve()
    missing = [name for name in FILES if not (data_dir / name).exists()]
    if missing:
        raise SystemExit(
            f"missing in {data_dir}: {', '.join(missing)} (templates are in config.example/)"
        )
    return Config(
        data_dir=data_dir,
        persona=Persona.model_validate(_read(data_dir / "persona.yaml")),
        answers=AnswerBank.model_validate(_read(data_dir / "answers.yaml")),
        search=SearchConfig.model_validate(_read(data_dir / "search.yaml")),
        watchlist=Watchlist.model_validate(_read(data_dir / "watchlist.yaml")),
        history=History.model_validate(_read(data_dir / "history.yaml")),
        resumes=ResumeRegistry.model_validate(_read(data_dir / "resumes.yaml")),
    )
