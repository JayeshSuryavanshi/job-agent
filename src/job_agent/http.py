from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import httpx

USER_AGENT = "job-agent/0.1 (+https://github.com/JayeshSuryavanshi/job-agent)"


class RateLimited(Exception):
    pass


class Http:
    def __init__(self, spacing: dict[str, float] | None = None, default_spacing: float = 0.25):
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True
        )
        self._spacing = dict(spacing or {})
        self._default = default_spacing
        self._last: dict[str, float] = {}
        self.requests = 0

    def _pace(self, url: str) -> None:
        host = urlparse(url).netloc
        gap = self._spacing.get(host, self._default)
        wait = self._last.get(host, 0.0) + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(3):
            self._pace(url)
            self.requests += 1
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.TransportError:
                if attempt == 2:
                    raise
                time.sleep(2.0 * (attempt + 1))
                continue
            if response.status_code == 429:
                raise RateLimited(url)
            if response.status_code >= 500 and attempt < 2:
                time.sleep(2.0 * (attempt + 1))
                continue
            return response
        raise AssertionError("unreachable")

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def get_json(self, url: str, **kwargs: Any) -> Any | None:
        return _json(self.get(url, **kwargs))

    def post_json(self, url: str, payload: dict[str, Any]) -> Any | None:
        return _json(self.request("POST", url, json=payload))

    def close(self) -> None:
        self._client.close()


def _json(response: httpx.Response) -> Any | None:
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None
