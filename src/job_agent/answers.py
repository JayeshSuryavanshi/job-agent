from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .config import AnswerBank, AnswerEntry, History, Persona
from .models import FormField, Job
from .text import company_key, has_phrase, norm

DECLINE = "decline"
RESUME = "<resume>"
AFFIRM = "<affirm>"
_WORK_AUTH_ENTRIES = {"work_authorized", "needs_sponsorship", "authorized_without_sponsorship"}

_SELF_MADE = re.compile(
    r"\b(personally (completed|wrote|written|prepared|filled)|completed (this|the) application"
    r" (myself|personally)|in my own words|without (the )?(use|help|assistance) of)\b"
)
_AI_WORDS = re.compile(
    r"\b(ai|artificial intelligence|chatgpt|claude|gpt|llms?|generative|language models?)\b"
)
_POLICY_WORDS = re.compile(
    r"\b(polic(y|ies)|guidelines?|agree|confirm\w*|certif\w*|acknowledg\w*|attest\w*"
    r"|permitted|prohibit\w*|allowed|disqualif\w*|partnership)\b"
)
_ARBITRATION = re.compile(r"\barbitrat")
_RECORDING = re.compile(
    r"\b(metaview|notetak\w*|note tak\w*|record\w* (your |the |all )?interviews?"
    r"|transcribe\w* (your |the |all )?interviews?)\b"
)
_CONFIDENTIALITY = re.compile(r"\bconfidentiality (acknowledg\w*|notice|agreement)")
_OFFICE = re.compile(
    r"\b(office|offices|onsite|on site|in person|commut\w*|work from|work out of"
    r"|days (a|per) week|monday through friday)\b"
)
_OFFICE_VERB = re.compile(
    r"\b(work|working|come|attend\w*|commut\w*|onsite|on site|in person|willing|able"
    r"|open to|expect\w*|prefer\w*|located|location|reside)\b"
)
_REMOTE_PREF = re.compile(r"\b(remote|work from home|wfh)\b")
_OTHER_CITY = re.compile(
    r"\b(new york|nyc|seattle|bellevue|boston|cambridge|austin|los angeles|chicago|denver"
    r"|toronto|london|washington|raleigh|atlanta|miami|portland|salt lake|berkeley|oakland"
    r"|emeryville|san diego|pittsburgh|philadelphia|dallas|houston)\b"
)
_PREFERRED_FULL = re.compile(
    r"^preferred (first )?(and )?(last name|full name)$|^preferred full name"
)
_DAY_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_KEYS = {
    "first_name": "first",
    "last_name": "last",
    "preferred_name": "preferred",
    "email": "email",
    "phone": "phone",
    "resume": "resume",
    "cover_letter": "cover_letter",
    "_systemfield_name": "full_name",
    "_systemfield_email": "email",
    "_systemfield_phone": "phone",
    "_systemfield_resume": "resume",
    "_systemfield_location": "location",
    "name": "full_name",
    "location": "location",
    "org": "current_company",
    "urls[LinkedIn]": "linkedin",
    "urls[GitHub]": "github",
    "urls[Portfolio]": "website",
    "urls[Other]": "website",
}
_LABELS = [
    (re.compile(p), slot)
    for p, slot in (
        (r"^(legal )?first name\b", "first"),
        (r"^(legal )?(last name|surname|family name)\b", "last"),
        (r"^preferred (first )?name\b", "preferred"),
        (r"^(your |full |legal )*name$|\bfull legal name\b|\blegal name as\b", "full_name"),
        (r"^e ?mail( address)?$", "email"),
        (r"^(phone|mobile|cell)( phone)?( number)?$", "phone"),
        (r"\blinkedin\b", "linkedin"),
        (r"\bgithub\b", "github"),
        (r"^(personal )?(website|portfolio)\b|\bportfolio (url|link|website)\b", "website"),
        (
            r"\bcurrent (or )?(most recent |last |previous )?(company|employer)\b"
            r"|^(company|employer)( name)?$|^current organi[sz]ation\b"
            r"|\bmost recent (company|employer)\b|\bwhere have you most recently worked\b",
            "current_company",
        ),
        (r"^current (job )?title\b|^current (position|role)\b", "current_title"),
        (
            r"^country( of residence)?$"
            r"|^(what|which) country (do you|of) (currently )?(live|reside|residence)\b"
            r"|\bbased in any of these countries\b|\bwhich of the following .*countries\b",
            "country",
        ),
        (
            r"\bstate of residence\b|^state$|\bwhich state do you (currently )?(live|reside)\b",
            "state",
        ),
        (
            r"address from which you plan|where (will|do) you plan to work from"
            r"|^current location\b|^location( city)?$|^city$"
            r"|^where are you (currently )?(located|based)",
            "location",
        ),
        (r"^(resume|cv)\b", "resume"),
        (r"^cover letter\b", "cover_letter"),
    )
]
_EEO = [
    (re.compile(p), slot)
    for p, slot in (
        (r"\btransgender\b", "transgender"),
        (r"\bpronouns?\b", "pronouns"),
        (r"\bsexual orientation\b|\blgbt", "sexual_orientation"),
        (r"\bgender\b|^sex$", "gender"),
        (r"\bhispanic\b|\blatin[oax]\b", "hispanic_latino"),
        (r"\brace\b|\bethnicit(y|ies)\b|\bethnic\b|\bwhich categories describe you\b", "race"),
        (r"\bveteran\b|\bmilitary\b", "veteran"),
        (r"\bdisabilit(y|ies)\b", "disability"),
    )
]
_EEO_OPTIONS = [
    (re.compile(p), slot)
    for p, slot in (
        (r"\b(cisgender|transgender)\b", "transgender"),
        (r"\b(heterosexual|straight|gay|lesbian|bisexual|queer)\b", "sexual_orientation"),
        (r"\b(asian|white|black|african american|pacific islander)\b", "race"),
        (r"\bveteran\b", "veteran"),
        (r"\bdisabilit", "disability"),
        (r"\b(male|female|man|woman|non binary)\b", "gender"),
    )
]
_START = re.compile(
    r"\b(earliest|soonest)\b.*\b(start|begin|available)\b|\bstart date\b"
    r"|\bwhen (can|could|would) you (start|begin)\b|\bavailable to start\b"
)
_NOTICE = re.compile(r"\bnotice period\b")
_HEARD = re.compile(
    r"\bhow did you (first )?(hear|learn|find out) about\b"
    r"|\bwhere did you (first )?(hear|find|learn)\b"
    r"|\bsource of (your )?application\b|\bhow did you (first )?find\b"
)
_ADULT = re.compile(
    r"\b(18|eighteen) years\b|\bat least 18\b|\bover 18\b|\b18 or older\b|\blegal working age\b"
)
_CONSENT = re.compile(
    r"\bprivacy (policy|notice|statement)\b|\bdata (processing|protection|privacy)\b"
    r"|\bprocess(ing)? (of )?my (personal )?(data|information)\b"
    r"|\bconsent to (the )?(processing|collection|storage|use)\b"
    r"|\bconsent to .{0,40}\b(collect\w*|stor(e|ing|age)|process\w*)\b"
)
_CERTIFY = re.compile(
    r"\b(certify|confirm|attest) that (the |all )?(information|answers|statements)\b"
    r".*\b(true|accurate|correct|complete)\b"
    r"|\b(double check|review|verify)\b.*\binformation\b.*\b(accura\w*|correct|complete)\b"
)
_LIVE_IN_STATES = re.compile(
    r"\bdo you (currently )?(live|reside) in (one of )?the following states\b"
)
_WORKED = re.compile(
    r"\b(previously|ever|formerly) (been )?(work(ed)?|employed)\b|\bformer employee\b"
    r"|\bcurrent or former\b|\bhave you worked (at|for)\b"
    r"|\bhave you (ever )?been employed (by|at|with)\b"
)
_APPLIED = re.compile(r"\b(previously|ever) applied\b|\bapplied (to|at|with|for) .{0,40}\bbefore\b")
_THIS_COMPANY = re.compile(
    r"\b(for|with|by|at) us\b|\bour (company|organization|team)\b"
    r"|\bthis (company|organization)\b|\bsubsidiar|\baffiliate"
)
_AFFIRMATIVE = re.compile(
    r"^(yes|i agree|agree|i acknowledge|acknowledge|i consent|i have read|i understand"
    r"|i confirm|confirm|i accept|accept|i have reviewed)\b"
)
_NEGATION = re.compile(r"\b(not|no|don t|do not|without|never)\b")
_SYNONYMS: dict[str, list[str]] = {
    DECLINE: [
        "decline",
        "don t wish",
        "do not wish",
        "prefer not",
        "not to answer",
        "do not want to answer",
        "don t want to answer",
        "choose not",
        "not to disclose",
        "rather not",
    ],
    "male": ["man", "cisgender man"],
    "i am not a protected veteran": [
        "i am not a veteran",
        "not a protected veteran",
        "not a veteran",
        "no military service",
        "no",
    ],
    "linkedin": ["linked in", "job board", "online job board", "other"],
    "company website": [
        "careers page",
        "career site",
        "careers site",
        "company careers page",
        "website",
        "other",
    ],
}


@dataclass
class Resolution:
    value: Any
    status: str
    source: str


def choose_option(answer: str, options: list[str]) -> str | None:
    if not options:
        return answer
    key = norm(answer)
    targets = _SYNONYMS[DECLINE] if answer == DECLINE else [key, *_SYNONYMS.get(key, [])]
    normed = [(o, norm(o)) for o in options]
    if any(ch.isdigit() for ch in key):
        return next((o for o, n in normed if n == key), None)
    for target in targets:
        for option, n in normed:
            if n == target:
                return option
        starts = [o for o, n in normed if n.startswith(target + " ")]
        if len(starts) == 1:
            return starts[0]
        within = [o for o, n in normed if has_phrase(n, target)]
        if len(within) == 1:
            return within[0]
    return None


def contains(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    if has_phrase(text, phrase):
        return True
    words, target = text.split(), phrase.split()
    size = len(target)
    return any(
        all(_close(a, b) for a, b in zip(words[i : i + size], target, strict=True))
        for i in range(len(words) - size + 1)
    )


def _close(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < 6 or abs(len(a) - len(b)) > 1 or a[:2] != b[:2]:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def _about_company(label: str, job: Job) -> bool:
    words = norm(job.company).split()
    if words and len(words[0]) > 2 and has_phrase(label, words[0]):
        return True
    return _THIS_COMPANY.search(label) is not None


class Answerer:
    def __init__(
        self,
        persona: Persona,
        bank: AnswerBank,
        history: History,
        today: date,
        commute: list[str] | None = None,
    ):
        self.persona = persona
        self._commute = [norm(c) for c in commute or [] if norm(c)]
        self.bank = bank
        self.today = today
        self._employers = {company_key(e) for e in persona.employment.past_employers}
        self._applied = {company_key(a.company) for a in history.applied}

    def resolve(self, f: FormField, job: Job) -> Resolution:
        label = norm(f.label)
        context = f"{label} {norm(f.description)}"
        if self._attestation(label, context):
            entry = self.lookup(label, job, scoped_only=True)
            if entry is not None and entry.answer is not None:
                return self._fit(f, entry.answer, f"bank:{entry.id}")
            if self._arbitration_ok(label, context):
                return self._fit(f, AFFIRM, "consent:arbitration")
            return Resolution(None, "blocked", "attestation")
        slot = "preferred_full" if _PREFERRED_FULL.search(label) else _KEYS.get(f.key)
        if slot is not None:
            return self._fit(f, self._persona(slot), f"persona:{slot}")
        computed = self._computed(label, f, job)
        if computed is not None:
            return self._fit(f, computed[0], computed[1])
        slot = next((s for pattern, s in _LABELS if pattern.search(label)), None)
        if slot is not None:
            return self._fit(f, self._persona(slot), f"persona:{slot}")
        eeo = self._eeo_slot(f, label)
        if eeo is not None:
            return self._fit(f, getattr(self.persona.eeo, eeo), f"eeo:{eeo}")
        entry = self.lookup(label, job)
        if entry is not None and entry.answer is not None:
            result = self._fit(f, entry.answer, f"bank:{entry.id}")
            if result.status != "answered" and entry.id in _WORK_AUTH_ENTRIES:
                option = self._work_auth_option(f.options)
                if option is not None:
                    value = [option] if f.kind == "multiselect" else option
                    return Resolution(value, "answered", f"bank:{entry.id} (descriptive option)")
            return result
        return self._missing(f, "none")

    def lookup(self, label: str, job: Job, scoped_only: bool = False) -> AnswerEntry | None:
        ck = company_key(job.company)
        best: tuple[int, int, int] | None = None
        chosen: AnswerEntry | None = None
        for entry in self.bank.entries:
            scoped = bool(entry.companies)
            if scoped and ck not in {company_key(c) for c in entry.companies}:
                continue
            if scoped_only and not scoped:
                continue
            if entry.require and not all(contains(label, norm(r)) for r in entry.require):
                continue
            if any(contains(label, norm(u)) for u in entry.unless):
                continue
            hits = [len(p) for p in (norm(m) for m in entry.match) if contains(label, p)]
            if not hits:
                continue
            rank = (int(scoped), entry.priority, max(hits))
            if best is None or rank > best:
                best, chosen = rank, entry
        return chosen

    def _arbitration_ok(self, label: str, context: str) -> bool:
        if _SELF_MADE.search(context) or (
            _AI_WORDS.search(label) and _POLICY_WORDS.search(context)
        ):
            return False
        return self.persona.consents.arbitration and bool(_ARBITRATION.search(context))

    def _near(self, text: str) -> bool:
        return any(has_phrase(text, place) for place in self._commute)

    def _office(self, label: str, f: FormField, job: Job) -> str | None:
        if not (self._commute and _OFFICE.search(label) and _OFFICE_VERB.search(label)):
            return None
        if _REMOTE_PREF.search(label) or ("relocat" in label and "commut" not in label):
            return None
        options = [(o, norm(o)) for o in f.options]
        yes_no = any(n.startswith(("yes", "no")) for _, n in options)
        places = [o for o, n in options if self._near(n)]
        if places and not yes_no:
            return places[0]
        days = _office_days(label)
        if days is not None and days > self.persona.office.max_days:
            return None
        if not self._near(label) and (
            _OTHER_CITY.search(label) or not self._near(norm(job.location))
        ):
            return None
        if not options:
            return "Yes"
        yes = [o for o, n in options if n.startswith("yes")]
        if len(yes) > 1:
            yes = [o for o in yes if not re.search(r"\b(not|relocat\w*)\b", norm(o))]
        return yes[0] if len(yes) == 1 else None

    @staticmethod
    def _attestation(label: str, context: str) -> bool:
        if _SELF_MADE.search(context) or _ARBITRATION.search(context):
            return True
        return bool(_AI_WORDS.search(label) and _POLICY_WORDS.search(context))

    def _persona(self, slot: str) -> Any:
        p = self.persona
        return {
            "first": p.name.first,
            "last": p.name.last,
            "preferred": p.name.preferred or p.name.first,
            "full_name": p.name.full,
            "preferred_full": f"{p.name.preferred or p.name.first} {p.name.last}",
            "email": p.contact.email,
            "phone": p.contact.phone,
            "linkedin": p.links.linkedin,
            "github": p.links.github,
            "website": p.links.website,
            "current_company": p.employment.current_company,
            "current_title": p.employment.current_title,
            "country": p.address.country,
            "state": p.address.state,
            "location": p.address.city_state_country,
            "resume": RESUME,
            "cover_letter": None,
        }.get(slot)

    def _computed(self, label: str, f: FormField, job: Job) -> tuple[Any, str] | None:
        if _START.search(label):
            when = self.today + timedelta(days=self.persona.start_notice_days)
            text = when.isoformat() if f.kind == "date" else when.strftime("%m/%d/%Y")
            return text, "computed:start_date"
        if _NOTICE.search(label):
            days = self.persona.start_notice_days
            return (f"{days // 7} weeks" if days % 7 == 0 else f"{days} days"), "computed:notice"
        if _HEARD.search(label):
            return ("LinkedIn" if job.linkedin_id else "Company website"), "computed:source"
        if _ADULT.search(label):
            return "Yes", "computed:adult"
        if f.section == "consent" or _CONSENT.search(label):
            return AFFIRM, "computed:privacy_consent"
        if _CERTIFY.search(label):
            return AFFIRM, "computed:accuracy"
        if _LIVE_IN_STATES.search(label):
            inside = has_phrase(label, norm(self.persona.address.state))
            return ("Yes" if inside else "No"), "computed:state"
        if _WORKED.search(label) and _about_company(label, job):
            worked = company_key(job.company) in self._employers
            return ("Yes" if worked else "No"), "computed:employer_history"
        if _APPLIED.search(label) and _about_company(label, job):
            applied = company_key(job.company) in self._applied
            return ("Yes" if applied else "No"), "computed:application_history"
        consents = self.persona.consents
        if consents.interview_recording and _RECORDING.search(label):
            return "Yes", "consent:interview_recording"
        if consents.confidentiality and _CONFIDENTIALITY.search(label):
            return AFFIRM, "consent:confidentiality"
        office = self._office(label, f, job)
        if office is not None:
            return office, "computed:office"
        return None

    def _eeo_slot(self, f: FormField, label: str) -> str | None:
        if f.section != "eeo" and len(label) > 120:
            return None
        text = f"{norm(f.key)} {label}"
        slot = next((s for pattern, s in _EEO if pattern.search(text)), None)
        if slot is None and (f.section == "eeo" or len(label) < 40) and f.options:
            options = " ".join(norm(o) for o in f.options)
            slot = next((s for pattern, s in _EEO_OPTIONS if pattern.search(options)), None)
        return slot

    def _work_auth_option(self, options: list[str]) -> str | None:
        if not self.persona.work_auth.needs_sponsorship:
            return None
        normed = [(o, norm(o)) for o in options]
        needs = [
            o
            for o, n in normed
            if re.search(r"\b(require|need)\w*\b.*\bsponsor", n) and not _NEGATION.search(n)
        ]
        if len(needs) == 1:
            return needs[0]
        visa = [
            o
            for o, n in normed
            if re.search(r"\b(visa|work permit)\b", n) and not _NEGATION.search(n)
        ]
        return visa[0] if len(visa) == 1 else None

    def _fit(self, f: FormField, value: Any, source: str) -> Resolution:
        if value is None:
            return self._missing(f, source)
        if value == AFFIRM:
            return self._affirm(f, source)
        if f.kind == "file":
            return (
                Resolution(value, "answered", source)
                if value == RESUME
                else self._missing(f, source)
            )
        if f.kind == "boolean":
            v = norm(str(value))
            if v in ("yes", "true"):
                return Resolution(True, "answered", source)
            if v in ("no", "false"):
                return Resolution(False, "answered", source)
            return self._missing(f, source)
        if f.kind in ("select", "multiselect"):
            choice = choose_option(str(value), f.options)
            if choice is None:
                return self._missing(f, f"{source} (no matching option)")
            return Resolution([choice] if f.kind == "multiselect" else choice, "answered", source)
        if value == DECLINE:
            return self._missing(f, source)
        if f.kind == "number":
            first = re.search(r"\d+(\.\d+)?", str(value))
            return (
                Resolution(first.group(), "answered", source) if first else self._missing(f, source)
            )
        return Resolution(str(value), "answered", source)

    def _affirm(self, f: FormField, source: str) -> Resolution:
        if f.kind == "boolean":
            return Resolution(True, "answered", source)
        if f.kind in ("select", "multiselect"):
            picks = (
                f.options
                if len(f.options) == 1
                else [o for o in f.options if _AFFIRMATIVE.search(norm(o))]
            )
            if len(picks) != 1:
                return self._missing(f, f"{source} (no matching option)")
            return Resolution(
                [picks[0]] if f.kind == "multiselect" else picks[0], "answered", source
            )
        return Resolution("Yes", "answered", source)

    @staticmethod
    def _missing(f: FormField, source: str) -> Resolution:
        return Resolution(None, "unknown" if f.required else "blank", source)


def _office_days(label: str) -> int | None:
    if re.search(r"\b(monday (through|to) friday|full time in|fully (onsite|in office))\b", label):
        return 5
    m = re.search(r"\b(one|two|three|four|five|[1-5])\s+days?\s+(a|per|each)\s+week\b", label)
    if m is None:
        return None
    value = m.group(1)
    return int(value) if value.isdigit() else _DAY_WORDS[value]
