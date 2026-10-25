from __future__ import annotations

import json
from pathlib import Path

from .answers import Answerer
from .models import FormField, Job
from .pipeline import RunResult
from .store import Store


def _cell(text: str | None) -> str:
    return (text or "").replace("|", "/").replace("\n", " ").strip()


def _link(text: str, url: str | None) -> str:
    return f"[{_cell(text)}]({url})" if url else _cell(text)


def _pay(job: Job) -> str:
    return job.pay.label() if job.pay else "?"


def write_run(result: RunResult, data_dir: Path) -> Path:
    local = result.started.astimezone()
    by_status: dict[str, list] = {"ready": [], "needs_answers": [], "blocked": [], "error": []}
    for item in result.plans:
        by_status.setdefault(item[2].status, []).append(item)
    waiting = f", {len(result.unplanned)} wait for the next run" if result.unplanned else ""
    lines = [
        f"# Run {local:%Y-%m-%d %H:%M}",
        "",
        "The tool planned every answer; nothing was submitted.",
        "",
        f"- Company boards: {result.board_jobs} open roles on {result.boards_read} boards",
        f"- Passed every filter: {result.survivors}; planned {len(result.plans)}{waiting}",
        f"- Plans: {len(by_status['ready'])} ready, {len(by_status['needs_answers'])} need your "
        f"answers, {len(by_status['blocked'])} need your decision, "
        f"{len(by_status['error'])} unreadable",
        f"- Requests made: {result.requests}",
        "",
        "## Ready to apply",
        "",
    ]
    if by_status["ready"]:
        lines += [
            "| Company | Role | Base pay | Location | Resume |",
            "|---|---|---|---|---|",
        ]
        for job, _, plan in by_status["ready"]:
            lines.append(
                f"| {_cell(job.company)} | {_link(job.title, job.apply_url)} | {_pay(job)} | "
                f"{_cell(job.location)[:60]} | {plan.resume} |"
            )
    else:
        lines.append("None this run.")
    lines += ["", "## Need your answers", ""]
    if by_status["needs_answers"]:
        lines += [
            "| Company | Role | Base pay | Resume | Missing answers |",
            "|---|---|---|---|---|",
        ]
        for job, _, plan in by_status["needs_answers"]:
            missing = "; ".join(b.removeprefix("answer: ") for b in plan.blockers)
            lines.append(
                f"| {_cell(job.company)} | {_link(job.title, job.apply_url)} | {_pay(job)} | "
                f"{plan.resume} | {_cell(missing)[:400]} |"
            )
    else:
        lines.append("None.")
    lines += ["", "## Need your decision", ""]
    if by_status["blocked"]:
        lines += ["| Company | Role | Base pay | Why |", "|---|---|---|---|"]
        for job, _, plan in by_status["blocked"]:
            why = "; ".join(
                b.removeprefix("decide: ") for b in plan.blockers if b.startswith("decide:")
            )
            lines.append(
                f"| {_cell(job.company)} | {_link(job.title, job.apply_url)} | {_pay(job)} | "
                f"{_cell(why)[:300]} |"
            )
    else:
        lines.append("None.")
    if by_status["error"]:
        lines += ["", "## Forms the agent could not read", ""]
        lines += [
            f"- {_cell(j.company)}: {_link(j.title, j.apply_url)}" for j, _, _ in by_status["error"]
        ]
    lines += ["", "## Skipped", "", "| Reason | Count | Examples |", "|---|---|---|"]
    for reason, jobs in sorted(result.skipped.items(), key=lambda kv: -len(kv[1])):
        examples = "; ".join(f"{j.company}: {j.title}" for j in jobs[:3])
        lines.append(f"| {_cell(reason)} | {len(jobs)} | {_cell(examples)[:240]} |")
    if result.errors:
        lines += ["", "## Errors", ""] + [f"- {_cell(e)[:300]}" for e in result.errors[:50]]
    path = data_dir / "runs" / f"{local:%Y-%m-%d_%H%M}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def write_questions(store: Store, answerer: Answerer, data_dir: Path) -> tuple[Path, int, int]:
    required: list[str] = []
    optional: list[str] = []
    for row in store.unanswered():
        options = json.loads(row["options"] or "[]")
        field = FormField("", row["label"], row["kind"], bool(row["required"]), options)
        company = (row["example"] or "").split(": ", 1)[0]
        probe = Job(source="check", company=company, title="", location="", url="")
        if answerer.resolve(field, probe).status == "answered":
            continue
        shown = "; ".join(options)[:160] if options else ""
        cells = [
            _cell(row["label"])[:200],
            row["kind"],
            _cell(shown),
            str(row["jobs"]),
            _cell(row["example"])[:80],
        ]
        line = "| " + " | ".join(cells) + " |"
        (required if row["required"] else optional).append(line)
    header = ["| Question | Type | Options | Roles | Example |", "|---|---|---|---|---|"]
    lines = [
        "# Questions waiting for your answer",
        "",
        "Add an entry to data/answers.yaml for each one you want the agent to answer;",
        "the next run picks it up. Entries match on phrases, so one entry can cover many wordings.",
        "",
        f"## Required ({len(required)}): these hold applications",
        "",
        *(header + required if required else ["None."]),
        "",
        f"## Optional ({len(optional)}): left blank for now",
        "",
        *(header + optional if optional else ["None."]),
    ]
    path = data_dir / "questions.md"
    path.write_text("\n".join(lines) + "\n")
    return path, len(required), len(optional)
