from __future__ import annotations

from collections.abc import Callable

from .http import Http
from .models import Job
from .sources import ashby, greenhouse, lever

Lister = Callable[[Http, str, str], list[Job]]
LISTERS: dict[str, Lister] = {
    "greenhouse": greenhouse.list_jobs,
    "ashby": ashby.list_jobs,
    "lever": lever.list_jobs,
}


class Boards:
    def __init__(self, http: Http) -> None:
        self.http = http
        self._jobs: dict[tuple[str, str], list[Job]] = {}

    def jobs(self, ats: str, slug: str, company: str) -> list[Job]:
        key = (ats, slug)
        if key not in self._jobs:
            self._jobs[key] = LISTERS[ats](self.http, slug, company)
        return self._jobs[key]
