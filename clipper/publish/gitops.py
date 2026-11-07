"""Commit and push changes under queue/ without sweeping in unrelated files."""
from __future__ import annotations

import subprocess
from pathlib import Path

from clipper.env import PROJECT_ROOT
from clipper.publish import PublishError


class GitError(PublishError):
    pass


def default_run(args: list[str], cwd: Path):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def commit_queue(message: str, *, cwd: Path = PROJECT_ROOT, run=default_run) -> bool:
    staged = run(["git", "diff", "--cached", "--name-only"], cwd).stdout.split()
    unrelated = [p for p in staged if not p.startswith("queue/")]
    if unrelated:
        raise GitError("refusing to commit: unrelated files are staged: " + ", ".join(unrelated))
    run(["git", "add", "queue"], cwd)
    if run(["git", "diff", "--cached", "--quiet", "--", "queue"], cwd).returncode == 0:
        return False
    committed = run(["git", "commit", "-m", message], cwd)
    if committed.returncode != 0:
        raise GitError(f"git commit failed: {committed.stderr.strip()}")
    for _ in range(2):
        if run(["git", "push"], cwd).returncode == 0:
            return True
        run(["git", "pull", "--rebase"], cwd)
    raise GitError("git push failed after a rebase retry")
