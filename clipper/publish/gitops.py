"""Commit and push changes under queue/ without sweeping in unrelated files."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from clipper.env import PROJECT_ROOT
from clipper.publish import PublishError


class GitError(PublishError):
    pass


def default_run(args: list[str], cwd: Path):
    try:
        return subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=120,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"could not run git: {type(exc).__name__}") from None


def commit_queue(message: str, *, cwd: Path = PROJECT_ROOT, run=default_run) -> bool:
    probe = run(["git", "diff", "--cached", "--name-only"], cwd)
    if probe.returncode != 0:
        raise GitError("git diff failed: " + probe.stderr.strip())
    unrelated = [p for p in probe.stdout.split() if not p.startswith("queue/")]
    if unrelated:
        raise GitError("refusing to commit: unrelated files are staged: " + ", ".join(unrelated))
    added = run(["git", "add", "queue"], cwd)
    if added.returncode != 0:
        raise GitError("git add failed: " + added.stderr.strip())
    quiet = run(["git", "diff", "--cached", "--quiet", "--", "queue"], cwd)
    if quiet.returncode == 0:
        return False
    if quiet.returncode != 1:
        raise GitError("git diff failed: " + quiet.stderr.strip())
    committed = run(["git", "commit", "-m", message], cwd)
    if committed.returncode != 0:
        raise GitError(f"git commit failed: {committed.stderr.strip()}")
    first = run(["git", "push"], cwd)
    if first.returncode == 0:
        return True
    pulled = run(["git", "pull", "--rebase"], cwd)
    if pulled.returncode != 0:
        run(["git", "rebase", "--abort"], cwd)
        raise GitError("git pull --rebase failed: " + pulled.stderr.strip())
    second = run(["git", "push"], cwd)
    if second.returncode == 0:
        return True
    raise GitError("git push failed: " + second.stderr.strip())
