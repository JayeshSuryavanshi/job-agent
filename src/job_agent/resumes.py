from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import ResumeRegistry
from .models import Job


@dataclass
class Pick:
    variant: str
    scores: dict[str, int]


def _score(patterns: dict[str, int], title: str, body: str) -> int:
    total = 0
    for pattern, weight in patterns.items():
        in_title = len(re.findall(pattern, title, re.IGNORECASE))
        in_body = min(len(re.findall(pattern, body, re.IGNORECASE)), 4)
        total += weight * (4 * in_title + in_body)
    return total


def pick(job: Job, registry: ResumeRegistry) -> Pick:
    scores = {v.name: _score(v.keywords, job.title, job.description) for v in registry.variants}
    special = sorted(
        (name for name in scores if name != registry.default),
        key=lambda name: scores[name],
        reverse=True,
    )
    if special:
        lead = special[0]
        other = scores[special[1]] if len(special) > 1 else 0
        if (
            scores[lead] >= 8
            and scores[lead] >= 1.3 * other
            and scores[lead] > scores.get(registry.default, 0)
        ):
            return Pick(lead, scores)
    return Pick(registry.default, scores)


def path_for(registry: ResumeRegistry, data_dir: Path, name: str) -> Path:
    variant = next(v for v in registry.variants if v.name == name)
    path = Path(variant.file).expanduser()
    return path if path.is_absolute() else data_dir / path


def sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def status(registry: ResumeRegistry, data_dir: Path) -> list[str]:
    lines = []
    for v in registry.variants:
        copy = path_for(registry, data_dir, v.name)
        if not copy.exists():
            lines.append(f"{v.name}: MISSING {copy} (run sync-resumes)")
            continue
        line = f"{v.name}: {copy.name} sha1 {sha1(copy)[:8]} ({v.use_for})"
        if v.source:
            source = Path(v.source).expanduser()
            if not source.exists():
                line += " | source not found"
            elif sha1(source) != sha1(copy):
                line += " | SOURCE CHANGED, run sync-resumes"
        lines.append(line)
    return lines


def sync(registry: ResumeRegistry, data_dir: Path) -> list[str]:
    done = []
    for v in registry.variants:
        if not v.source:
            continue
        source, copy = Path(v.source).expanduser(), path_for(registry, data_dir, v.name)
        if source.exists() and (not copy.exists() or sha1(source) != sha1(copy)):
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, copy)
            done.append(f"{v.name}: copied {source} (sha1 {sha1(copy)[:8]})")
    return done
