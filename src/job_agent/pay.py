from __future__ import annotations

import re
from typing import Any

from .models import Pay

_AMT = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?\s?[kK]\b|\d{5,7}(?:\.\d+)?"
_CUR = r"US\$|USD\s?\$?|CA\$|C\$|AU\$|A\$|\$|£|€"
_RANGE = re.compile(
    rf"(?P<c1>{_CUR})?\s?(?P<lo>{_AMT})\s*(?:USD|/\s?(?:yr|year|annually))?\s*"
    rf"(?:-|–|—|to)\s*(?P<c2>{_CUR})?\s?(?P<hi>{_AMT})(?P<tail>[^\n;.]{{0,30}})"
)
_FOREIGN = ("CA$", "C$", "AU$", "A$", "£", "€")
_HOURLY = re.compile(r"/\s?h(?:ou)?r\b|per hour|hourly|an hour")
_NOT_PAY = re.compile(r"employees|users|customers|people|members|requests|transactions")
_LOW, _HIGH = 30_000, 2_000_000


def _amount(raw: str) -> float | None:
    s = raw.replace(",", "").replace(" ", "").lower()
    mult = 1000.0 if s.endswith("k") else 1.0
    try:
        return float(s.rstrip("k")) * mult
    except ValueError:
        return None


def _plausible(pay: Pay) -> Pay | None:
    return pay if pay.high is not None and _LOW <= pay.high <= _HIGH else None


def _better(a: Pay | None, b: Pay | None) -> Pay | None:
    b = _plausible(b) if b is not None else None
    if a is None:
        return b
    if b is None:
        return a
    return b if (b.high or 0) > (a.high or 0) else a


def from_text(text: str | None) -> Pay | None:
    best: Pay | None = None
    for m in _RANGE.finditer(text or ""):
        cur = (m.group("c1") or m.group("c2") or "").replace(" ", "").upper()
        tail = m.group("tail").lower()
        if not cur and "usd" not in tail:
            continue
        if cur.startswith(_FOREIGN) or _HOURLY.search(tail) or _NOT_PAY.search(tail[:15]):
            continue
        lo, hi = _amount(m.group("lo")), _amount(m.group("hi"))
        if lo is None or hi is None or hi < lo:
            continue
        if not (_LOW <= lo <= _HIGH and _LOW <= hi <= _HIGH):
            continue
        best = _better(best, Pay(lo, hi, "USD", "text"))
    return best


def from_greenhouse(ranges: list[dict[str, Any]] | None) -> Pay | None:
    best: Pay | None = None
    for r in ranges or []:
        if (r.get("currency_type") or "USD").upper() != "USD":
            continue
        lo, hi = r.get("min_cents"), r.get("max_cents")
        if lo is None or hi is None:
            continue
        best = _better(best, Pay(lo / 100, hi / 100, "USD", "greenhouse"))
    return best


def from_ashby(comp: dict[str, Any] | None) -> Pay | None:
    best: Pay | None = None
    for tier in (comp or {}).get("compensationTiers") or []:
        for c in tier.get("components") or []:
            if c.get("compensationType") != "Salary":
                continue
            if (c.get("currencyCode") or "").upper() != "USD":
                continue
            if "YEAR" not in (c.get("interval") or "").upper():
                continue
            lo, hi = c.get("minValue"), c.get("maxValue")
            if hi is None:
                continue
            best = _better(
                best, Pay(float(lo if lo is not None else hi), float(hi), "USD", "ashby")
            )
    return best


def from_lever(salary: dict[str, Any] | None) -> Pay | None:
    if not salary or (salary.get("currency") or "USD").upper() != "USD":
        return None
    if "year" not in (salary.get("interval") or "per-year-salary"):
        return None
    lo, hi = salary.get("min"), salary.get("max")
    if hi is None:
        return None
    return _plausible(Pay(float(lo if lo is not None else hi), float(hi), "USD", "lever"))
