from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime

from bs4 import BeautifulSoup

_COUNTRY = re.compile(r"\bu s a\b|\bu s\b|\busa\b|\bunited states of america\b|\bunited states\b")
_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|company|technologies|technology|holdings|group|plc|gmbh|pbc)\b"
)
_TITLE_WORDS = {
    "sr": "senior",
    "snr": "senior",
    "jr": "junior",
    "ml": "machine learning",
    "mle": "machine learning engineer",
    "swe": "software engineer",
    "eng": "engineer",
    "engr": "engineer",
    "ii": "2",
    "iii": "3",
    "iv": "4",
}


def norm(text: str | None) -> str:
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return _COUNTRY.sub("us", t)


def company_key(name: str | None) -> str:
    t = unicodedata.normalize("NFKC", name or "").lower()
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = _SUFFIX.sub(" ", t)
    return re.sub(r"[^a-z0-9]", "", t)


def title_key(title: str | None) -> str:
    return " ".join(_TITLE_WORDS.get(w, w) for w in norm(title).split())


def titles_match(a: str | None, b: str | None) -> bool:
    ka, kb = title_key(a), title_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    sa, sb = set(ka.split()), set(kb.split())
    return len(sa & sb) / len(sa | sb) >= 0.8


def html_to_text(markup: str | None) -> str:
    if not markup:
        return ""
    soup = BeautifulSoup(html.unescape(markup), "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def has_phrase(text_norm: str, phrase_norm: str) -> bool:
    if not phrase_norm:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(phrase_norm)}(?![a-z0-9])"
    return re.search(pattern, text_norm) is not None


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def url_key(url: str | None) -> str:
    if not url:
        return ""
    base = re.split(r"[?#]", url.strip(), maxsplit=1)[0].rstrip("/").lower()
    base = re.sub(r"^https?://(www\.)?", "", base)
    return re.sub(r"/(apply|application)$", "", base)


def linkedin_job_id(url: str) -> str | None:
    m = re.search(r"linkedin\.com/jobs/view/(?:[^/?#]*-)?(\d{6,})", url) or re.search(
        r"linkedin\.com/.*[?&]currentJobId=(\d{6,})", url
    )
    return m.group(1) if m else None
