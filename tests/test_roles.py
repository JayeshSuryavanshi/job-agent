import shutil
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from job_agent.answers import Answerer
from job_agent.config import AnswerBank, AnswerEntry, Config, History, SearchConfig, load
from job_agent.filters import Gate
from job_agent.models import FormField, Job, Pay
from job_agent.report import write_questions
from job_agent.roles import record, show
from job_agent.store import Store

FIXTURE = Path(__file__).parent / "fixtures" / "config"
LINK = "https://www.linkedin.com/jobs/view/senior-machine-learning-engineer-at-example-4474113276"
TITLE = "Senior Machine Learning Engineer"


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[Config, Store]]:
    for f in FIXTURE.iterdir():
        shutil.copy(f, tmp_path / f.name)
    store = Store(tmp_path / "jobagent.db")
    yield load(tmp_path), store
    store.close()


def _field(label: str, kind: str, status: str, value: object, options: list[str]) -> dict:
    return {
        "key": label.lower(),
        "label": label,
        "kind": kind,
        "required": status != "blank",
        "section": "",
        "status": status,
        "source": "test",
        "value": value,
        "options": options,
    }


def _today() -> date:
    return datetime.now().date()


def test_show_and_record_a_chrome_application(setup: tuple[Config, Store]) -> None:
    cfg, store = setup
    job = Job(
        source="lever",
        company="Acme AI",
        title=TITLE,
        location="San Francisco, CA",
        url="https://jobs.lever.co/acme/abc-123",
        apply_url="https://jobs.lever.co/acme/abc-123/apply",
        ats="lever",
        ats_slug="acme",
        ats_job_id="abc-123",
        pay=Pay(300_000, 400_000),
    )
    store.upsert_job(job)
    fields = [
        _field("Full name", "text", "answered", "Alex Example", []),
        _field("Resume/CV", "file", "answered", "<resume>", []),
        _field("Pronouns", "select", "blank", None, ["He/him", "She/her"]),
        _field("Which office?", "select", "unknown", None, ["SF", "NYC"]),
    ]
    plan = {"status": "needs_answers", "resume": "general", "fields": fields}
    plan |= {"blockers": ["answer: Which office?"], "notes": ["form has hCaptcha"]}
    store.save_plan("run1", job.key, "needs_answers", "general", plan["blockers"], plan)
    store.commit()

    out = "\n".join(show(cfg, store, "https://jobs.lever.co/acme/abc-123/apply?src=x", _today()))
    assert "verdict: OK to apply" in out
    assert "[ok] Full name (text, required): Alex Example" in out
    assert "attach the resume file" in out
    assert "[--] Pronouns (select): (leave blank)" in out
    assert "options: SF; NYC" in out
    assert "fill in Chrome" in out
    assert "blocker: answer: Which office?" in out

    ok, message = record(cfg, store, "https://jobs.lever.co/acme/abc-123", "submitted")
    assert ok and message.startswith("recorded submitted")
    ok, message = record(cfg, store, job.key, "submitted")
    assert not ok and message.startswith("already recorded")
    out = "\n".join(show(cfg, store, job.key, _today()))
    assert "verdict: SKIP: already applied" in out
    assert "sent today: 1 of 10" in out


def test_outside_role_is_checked_from_its_posting(
    setup: tuple[Config, Store], tmp_path: Path
) -> None:
    cfg, store = setup

    def verdict(text: str | None) -> str:
        posting = None
        if text is not None:
            posting = tmp_path / "posting.txt"
            posting.write_text(text)
        lines = show(cfg, store, LINK, _today(), "Example Co", TITLE, "San Francisco, CA", posting)
        return next(line for line in lines if line.startswith("verdict:"))

    assert "posting not checked" in verdict(None)
    assert verdict("Base salary: $280,000 - $380,000 per year.") == "verdict: OK to apply"
    assert verdict("Base salary: $150,000 - $250,000.").startswith("verdict: SKIP: pay midpoint")
    assert verdict("No pay listed.") == "verdict: SKIP: no posted pay range"
    no_visa = "Base salary: $280,000 - $380,000. We are unable to sponsor visas for this role."
    assert verdict(no_visa) == "verdict: SKIP: posting says no visa sponsorship"
    cfg.persona.work_auth.needs_sponsorship = False
    assert verdict(no_visa) == "verdict: OK to apply"

    ok, _ = record(cfg, store, LINK, "submitted", "Example Co", TITLE)
    assert ok
    assert verdict("Base salary: $280,000 - $380,000.") == "verdict: SKIP: already applied"
    assert store.applied_jobs() == [("linkedin:4474113276", "Example Co", TITLE)]


def test_agent_applications_count_as_applied(search: SearchConfig) -> None:
    sent = [("greenhouse:acme:5", "Acme AI", "Principal Machine Learning Engineer")]
    g = Gate(search.filters, History(), search.limits, date(2026, 10, 24), {}, sent)

    def job(job_id: str, title: str = TITLE) -> Job:
        return Job(
            "greenhouse",
            "Acme AI",
            title,
            "San Francisco, CA",
            "u",
            None,
            "greenhouse",
            "acme",
            job_id,
        )

    assert g.recheck(job("5")) == "already applied"
    assert g.recheck(job("6", "Principal Machine Learning Engineer")) == "already applied"
    assert g.recheck(job("7")) is None


def test_company_answers_clear_their_questions(setup: tuple[Config, Store]) -> None:
    cfg, store = setup
    suno = Job("ashby", "Suno", TITLE, "San Francisco, CA", "u", None, "ashby", "suno", "1")
    why = FormField("q1", "Why are you interested in working at Suno?", "textarea", True)
    store.bump_unanswered(why, suno)
    store.commit()
    today = date(2026, 10, 24)
    before = Answerer(cfg.persona, cfg.answers, cfg.history, today)
    assert write_questions(store, before, cfg.data_dir)[1] == 1
    entry = AnswerEntry(
        id="why_suno", match=["interested in working at suno"], answer="Music.", companies=["Suno"]
    )
    bank = AnswerBank(entries=[*cfg.answers.entries, entry])
    after = Answerer(cfg.persona, bank, cfg.history, today)
    assert write_questions(store, after, cfg.data_dir)[1] == 0
