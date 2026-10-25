from datetime import UTC, date, datetime, timedelta
from typing import Any

from job_agent.config import History, SearchConfig
from job_agent.filters import NO_SPONSOR, Gate
from job_agent.models import Job, Pay


def job(**overrides: Any) -> Job:
    base: dict[str, Any] = {
        "source": "greenhouse",
        "company": "Acme AI",
        "title": "Senior Machine Learning Engineer",
        "location": "San Francisco, CA",
        "url": "u",
        "ats": "greenhouse",
        "ats_slug": "acme",
        "ats_job_id": "1",
        "posted_at": datetime.now(UTC),
    }
    base.update(overrides)
    return Job(**base)


def gate(search: SearchConfig) -> Gate:
    history = History.model_validate(
        {
            "blocked": [{"company": "Blocked Co", "aliases": ["BlockedSub"], "reason": "test"}],
            "applied": [
                {"company": "Capped", "applied": "2026-10-01"},
                {"company": "Capped", "applied": "2026-10-02"},
                {"company": "Acme AI", "title": "Staff ML Engineer", "job_id": "99"},
            ],
        }
    )
    return Gate(search.filters, history, search.limits, date(2026, 10, 23))


def test_titles(search: SearchConfig) -> None:
    g = gate(search)
    assert g.first_pass(job()) is None
    assert g.first_pass(job(title="Account Executive, AI")) == "title excluded (level or function)"
    assert g.first_pass(job(title="Senior Backend Engineer")) == "title is not an ML/AI role"
    assert g.first_pass(job(title="Machine Learning Intern")) is not None
    assert g.first_pass(job(title="Engineering Manager, Machine Learning")) is not None
    assert g.first_pass(job(title="Personalization Product Lead")) is not None
    assert g.first_pass(job(title="AI Research Fund Grants: Economics of AI")) is not None
    assert g.first_pass(job(title="Member of Technical Staff (Android Engineer, AI)")) is not None
    assert g.first_pass(job(title="Member of Technical Staff, Finance Data")) is not None
    assert g.first_pass(job(title="Member of Technical Staff, Model Efficiency")) is None
    assert g.first_pass(job(title="Research Engineer, Post-Training")) is None


def test_locations(search: SearchConfig) -> None:
    g = gate(search)
    assert g.location_ok(job(location="Remote - US"))
    assert g.location_ok(job(location="Remote (U.S.)"))
    assert g.location_ok(job(location="New York, NY", remote=True))
    assert g.location_ok(job(location="New York, NY; Palo Alto, CA"))
    assert g.location_ok(job(location="Remote - Milwaukee, WI"))
    assert not g.location_ok(job(location="Remote - Canada"))
    assert not g.location_ok(job(location="London, UK"))
    assert not g.location_ok(job(location="New York, NY"))


def test_history_and_caps(search: SearchConfig) -> None:
    g = gate(search)
    assert g.first_pass(job(company="BlockedSub")).startswith("blocked company")
    assert g.first_pass(job(company="Capped")).startswith("company cap")
    assert g.first_pass(job(ats_job_id="99")) == "already applied"
    assert g.first_pass(job(title="Staff ML Engineer")) == "already applied"
    old = datetime.now(UTC) - timedelta(days=40)
    assert g.first_pass(job(posted_at=old)).startswith("posted more than")
    assert g.first_pass(job(posted_at=old, linkedin_id="123")) is None


def test_pay_and_sponsorship(search: SearchConfig) -> None:
    g = gate(search)
    assert g.second_pass(job(pay=None)) == "no posted pay range"
    assert g.second_pass(job(pay=Pay(200_000, 300_000))).startswith("pay midpoint")
    assert g.second_pass(job(pay=Pay(217_000, 303_000))).startswith("pay midpoint")
    assert g.second_pass(job(pay=Pay(225_000, 315_000))).startswith("pay midpoint")
    assert g.second_pass(job(pay=Pay(266_000, 372_000))) is None
    assert g.second_pass(job(pay=Pay(250_000, 385_000))) is None
    assert g.second_pass(job(pay=Pay(None, 320_000))) is None
    assert g.second_pass(job(pay=Pay(250_000, 340_000))).startswith("pay midpoint")
    no_visa = job(pay=Pay(280_000, 360_000), description="We are unable to sponsor visas.")
    assert g.second_pass(no_visa) == "posting says no visa sponsorship"


def test_no_sponsor_language() -> None:
    hits = [
        "We are unable to sponsor visas for this role.",
        "Visa sponsorship is not available for this position.",
        "This role is not eligible for visa sponsorship.",
        "We do not offer H-1B sponsorship at this time.",
        "Candidates must be authorized to work in the US without sponsorship.",
        "Must be a U.S. citizen.",
        "Requires an active Secret security clearance.",
        "No visa sponsorship.",
    ]
    misses = [
        "We sponsor visas.",
        "Visa sponsorship is available.",
        "We will consider candidates who require sponsorship.",
        "We are an equal opportunity employer regardless of citizenship status.",
    ]
    assert [t for t in hits if not NO_SPONSOR.search(t)] == []
    assert [t for t in misses if NO_SPONSOR.search(t)] == []


def test_recheck_before_applying(search: SearchConfig) -> None:
    g = gate(search)
    remote_elsewhere = job(location="Toronto; Canada; United States", pay=Pay(260_000, 360_000))
    assert g.recheck(remote_elsewhere) is None
    assert g.recheck(job(company="BlockedSub")).startswith("blocked company")
    assert g.recheck(job(ats_job_id="99")) == "already applied"
    assert g.recheck(job(pay=Pay(217_000, 303_000))).startswith("pay midpoint")
    g.record("Acme AI", date(2026, 10, 23))
    assert g.recheck(job(ats_job_id="7")).startswith("company cap")
