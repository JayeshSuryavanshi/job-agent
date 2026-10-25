from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from job_agent.answers import Answerer
from job_agent.config import AnswerBank, History, Persona, SearchConfig

FIXTURE = Path(__file__).parent / "fixtures" / "config"


def _read(name: str) -> Any:
    return yaml.safe_load((FIXTURE / name).read_text())


@pytest.fixture
def search() -> SearchConfig:
    return SearchConfig.model_validate(_read("search.yaml"))


@pytest.fixture
def answerer() -> Answerer:
    persona = Persona.model_validate(_read("persona.yaml"))
    bank = AnswerBank.model_validate(_read("answers.yaml"))
    history = History.model_validate({"applied": [{"company": "Acme", "title": "ML Engineer"}]})
    return Answerer(persona, bank, history, date(2026, 10, 23))
