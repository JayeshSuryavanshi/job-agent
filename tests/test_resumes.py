from job_agent.config import ResumeRegistry, ResumeVariant
from job_agent.models import Job
from job_agent.resumes import pick

REGISTRY = ResumeRegistry(
    default="general",
    variants=[
        ResumeVariant(name="ml", file="ml.pdf", keywords={r"\bfraud\b": 3, r"\brisk\b": 2}),
        ResumeVariant(name="llm", file="llm.pdf", keywords={r"\bllms?\b": 2, r"\bevals?\b": 3}),
        ResumeVariant(name="general", file="general.pdf"),
    ],
)


def _job(title: str, description: str = "") -> Job:
    return Job("greenhouse", "Acme", title, "SF", "u", description=description)


def test_keywords_pick_the_resume() -> None:
    assert pick(_job("ML Engineer, Fraud"), REGISTRY).variant == "ml"
    assert pick(_job("LLM Evals Engineer"), REGISTRY).variant == "llm"
    assert pick(_job("Backend Engineer"), REGISTRY).variant == "general"


def test_a_close_call_falls_back_to_the_default() -> None:
    mixed = _job("Engineer", "fraud fraud fraud llm llm llm evals")
    assert pick(mixed, REGISTRY).variant == "general"
