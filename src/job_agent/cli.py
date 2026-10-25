from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path

from . import pipeline, report, resumes, roles
from .answers import Answerer
from .config import DEFAULT_DATA, load
from .store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="job-agent",
        description="Find roles, plan every application answer and track what you sent.",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("JOB_AGENT_DATA", DEFAULT_DATA)),
        help="data directory (default: ./data)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="find roles, filter them, plan each form (submits nothing)")
    show_cmd = sub.add_parser("show", help="one role: may it be sent, and its planned answers")
    show_cmd.add_argument("ref", help="job link (form or posting) or job key")
    show_cmd.add_argument("--company", help="for a role the tool has not seen")
    show_cmd.add_argument("--title", help="for a role the tool has not seen")
    show_cmd.add_argument("--location", help="for a role the tool has not seen")
    show_cmd.add_argument("--posting", type=Path, help="file with the posting text (pay check)")
    record_cmd = sub.add_parser(
        "record", help="log an application you sent so it is never offered again"
    )
    record_cmd.add_argument("ref", help="job link or job key")
    record_cmd.add_argument("--company", help="for a role the tool has not seen")
    record_cmd.add_argument("--title", help="for a role the tool has not seen")
    record_cmd.add_argument("--resume", help="resume variant used (a name from resumes.yaml)")
    record_cmd.add_argument(
        "--status",
        choices=["submitted", "unknown"],
        default="submitted",
        help="unknown = Submit clicked but no confirmation seen",
    )
    sub.add_parser("questions", help="list form questions waiting for your answer")
    sub.add_parser("check", help="validate config files and resume copies")
    sub.add_parser("sync-resumes", help="copy your current resume PDFs into the data folder")
    args = parser.parse_args(argv)
    cfg = load(args.data)
    today = datetime.now(UTC).date()

    if args.command == "check":
        p = cfg.persona
        print(f"data dir: {cfg.data_dir}")
        print(f"persona: {p.name.full} | {p.contact.email} | {p.address.city_state_country}")
        print(
            f"answer bank: {len(cfg.answers.entries)} entries | watchlist: "
            f"{len(cfg.watchlist.companies)} companies | blocked: "
            f"{', '.join(b.company for b in cfg.history.blocked) or 'none'}"
        )
        f = cfg.search.filters
        print(f"pay floor: ${f.pay_floor:,} (posted pay required: {f.require_pay})")
        for line in resumes.status(cfg.resumes, cfg.data_dir):
            print(f"resume {line}")
        return 0

    if args.command == "sync-resumes":
        done = resumes.sync(cfg.resumes, cfg.data_dir)
        print("\n".join(done) if done else "resume copies already current")
        return 0

    if args.command in ("show", "record"):
        store = Store(cfg.data_dir / "jobagent.db")
        try:
            if args.command == "show":
                lines = roles.show(
                    cfg,
                    store,
                    args.ref,
                    datetime.now().date(),
                    args.company,
                    args.title,
                    args.location,
                    args.posting,
                )
                print("\n".join(lines))
                return 0
            ok, message = roles.record(
                cfg, store, args.ref, args.status, args.company, args.title, args.resume
            )
            print(message)
            return 0 if ok else 1
        finally:
            store.close()

    answerer = Answerer(
        cfg.persona, cfg.answers, cfg.history, today, cfg.search.filters.commute_area
    )
    if args.command == "questions":
        store = Store(cfg.data_dir / "jobagent.db")
        path, required, optional = report.write_questions(store, answerer, cfg.data_dir)
        store.close()
        print(f"{required} required and {optional} optional questions: {path}")
        return 0

    result = pipeline.run(cfg)
    run_path = report.write_run(result, cfg.data_dir)
    store = Store(cfg.data_dir / "jobagent.db")
    questions, required, optional = report.write_questions(store, answerer, cfg.data_dir)
    store.close()
    print(f"report: {run_path}")
    print(f"questions: {questions} ({required} required, {optional} optional)")
    return 0
