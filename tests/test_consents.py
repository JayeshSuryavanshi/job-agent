from datetime import date
from pathlib import Path
from typing import Any

import yaml
from job_agent.answers import Answerer
from job_agent.config import AnswerBank, History, Persona
from job_agent.models import FormField, Job

FIXTURE = Path(__file__).parent / "fixtures" / "config"
COMMUTE = ["san francisco", "bay area", "palo alto", "redwood city", "san mateo", "cupertino"]
ROBLOX = (
    "I acknowledge that I received and had the opportunity to review Roblox's Candidate"
    " Arbitration Agreement, and I agree to be bound by its terms."
)
METAVIEW = (
    "We use Metaview, an AI notetaking tool, to streamline interviews by recoding and summarizing"
    " discussions, enabling interviewers to be fully present without manual notetaking. With your"
    " approval, it silently records notes during interviews. Can Metaview transcribe all your"
    " interviews?"
)
SUNO_OFFICE = (
    "Suno fosters an in-office culture with reasonable flexibility. We expect teammates to work"
    " from one of our offices Monday through Friday because we believe frequent in-person"
    " collaboration helps us move faster. Please confirm that you have read and understand"
    " Suno's in-office expectations and policy."
)
SIERRA = [
    "Yes, and I currently live in the SF Bay Area.",
    "Yes, and while I do not currently live in the SF Bay Area, I am open to relocation.",
    "No or Other. Please explain.",
]


def answerer(consent: bool = True, days: int = 5) -> Answerer:
    data = yaml.safe_load((FIXTURE / "persona.yaml").read_text())
    data["office"] = {"max_days": days}
    data["consents"] = dict.fromkeys(
        ("arbitration", "interview_recording", "confidentiality"), consent
    )
    bank = AnswerBank.model_validate(yaml.safe_load((FIXTURE / "answers.yaml").read_text()))
    return Answerer(Persona.model_validate(data), bank, History(), date(2026, 10, 24), COMMUTE)


def ask(
    a: Answerer,
    label: str,
    kind: str = "select",
    options: list[str] | None = None,
    location: str = "San Francisco, CA",
) -> tuple[str, Any]:
    job = Job("ashby", "Acme", "Staff Machine Learning Engineer", location, "u")
    r = a.resolve(FormField("q", label, kind, True, options or []), job)
    return r.status, r.value


def test_arbitration_needs_his_consent() -> None:
    roblox = "Please review and acknowledge Roblox's Candidate Arbitration Agreement"
    assert ask(answerer(), roblox, options=[ROBLOX]) == ("answered", ROBLOX)
    assert ask(answerer(consent=False), roblox, options=[ROBLOX])[0] == "blocked"
    agree = "I understand and agree to the terms of the Agreement to Arbitrate set forth above."
    assert ask(answerer(), "Agreement to Arbitrate", options=[agree]) == ("answered", agree)


def test_ai_policy_stays_his_decision() -> None:
    assert ask(answerer(), "AI Policy for Application", options=["Yes", "No"])[0] == "blocked"


def test_recording_and_confidentiality() -> None:
    assert ask(answerer(), METAVIEW, options=["Yes", "No"]) == ("answered", "Yes")
    notice = "Candidate Confidentiality Acknowledgment"
    options = ["I agree", "I do not agree"]
    assert ask(answerer(), notice, options=options) == ("answered", "I agree")
    assert ask(answerer(consent=False), METAVIEW, options=["Yes", "No"])[0] == "unknown"


def test_office_answers_follow_the_commute_area() -> None:
    a = answerer()
    suno_offices = [
        "Boston (Cambridge)",
        "New York City (Chelsea)",
        "Los Angeles (Venice)",
        "San Francisco",
        "Remote only",
    ]
    which = "Which office are you willing to work out of?"
    assert ask(a, which, "multiselect", suno_offices) == ("answered", ["San Francisco"])
    assert ask(a, SUNO_OFFICE, "boolean", location="Boston; San Francisco") == ("answered", True)
    assert ask(a, "Are you able to work from San Francisco, CA?", options=SIERRA) == (
        "answered",
        SIERRA[0],
    )
    plaid = ["San Francisco HQ", "New York City Office", "Seattle Office", "Remote US"]
    assert ask(a, "Preferred Location (In Office)", "multiselect", plaid) == (
        "answered",
        ["San Francisco HQ"],
    )
    character = "Are you open to working full-time in our New York or Redwood City, CA office?"
    assert ask(a, character, "boolean") == ("answered", True)
    four = "Are you able to come into the office four days per week?"
    assert ask(a, four, "boolean", location="San Francisco; Seattle; New York") == (
        "answered",
        True,
    )


def test_office_answers_stay_open_when_they_should() -> None:
    four = "Are you able to come into the office four days per week?"
    assert ask(answerer(days=3), four, "boolean")[0] == "unknown"
    five = "Are you able to come into the office 5 days a week?"
    assert ask(answerer(), five, "boolean", location="Boston, MA")[0] == "unknown"
    relocate = "Are you open to relocation for this role?"
    assert ask(answerer(), relocate, options=["Yes", "No"])[0] == "unknown"
    assert ask(answerer(), "Have you used Microsoft Office?", "boolean")[0] == "unknown"


def test_preferred_full_name_beats_the_field_id() -> None:
    a = answerer()
    job = Job("ashby", "Sierra", "Software Engineer", "San Francisco, CA", "u")
    field = FormField("_systemfield_name", "Preferred First & Last Name", "text", True)
    assert a.resolve(field, job).value == "Alex Example"
    plain = FormField("_systemfield_name", "Name", "text", True)
    assert a.resolve(plain, job).value == a.persona.name.full
