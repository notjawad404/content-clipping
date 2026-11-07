"""Post every queued clip now: run the live post-next workflow once per pending entry and wait for each."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Callable

from clipper.env import PROJECT_ROOT
from clipper.publish import PublishError, queue
from clipper.publish.config import load_publish_config

WORKFLOW = "post-next.yml"
POLL_INTERVAL_S = 5
POLL_TIMEOUT_S = 90
COMMAND_TIMEOUT_S = 1800  # `gh run watch` blocks until the run ends (about two minutes per clip)


class PostNowError(PublishError):
    pass


def default_run(args: list[str]):
    try:
        return subprocess.run(args, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PostNowError(f"could not run {args[0]}: {type(exc).__name__}") from None


def _ok(proc, what: str) -> str:
    if proc.returncode != 0:
        raise PostNowError(f"{what} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout


def _check_branch(run, branch: str) -> None:
    current = _ok(run(["git", "rev-parse", "--abbrev-ref", "HEAD"]), "git rev-parse").strip()
    if current != branch:
        raise PostNowError(f"refusing to run: you are on {current!r} but the queue lives on {branch!r}; "
                           f"switch with `git checkout {branch}`")


def _check_gh(run) -> None:
    if run(["gh", "auth", "status"]).returncode != 0:
        raise PostNowError("gh is not logged in; run `gh auth login` and try again")


def _pull(run) -> None:
    _ok(run(["git", "pull", "--rebase", "--autostash"]), "git pull --rebase")


def _run_ids(run) -> set[int]:
    out = _ok(run(["gh", "run", "list", "--workflow", WORKFLOW, "--event", "workflow_dispatch",
                   "--limit", "20", "--json", "databaseId"]), "gh run list")
    try:
        return {int(row["databaseId"]) for row in json.loads(out)}
    except (ValueError, KeyError, TypeError):
        raise PostNowError("unexpected output from gh run list") from None


def _start_run(run, known: set[int], sleep: Callable[[float], None], clock: Callable[[], float]) -> int:
    _ok(run(["gh", "workflow", "run", WORKFLOW, "-f", "dry_run=false"]), "gh workflow run")
    deadline = clock() + POLL_TIMEOUT_S
    while True:
        new = _run_ids(run) - known
        if new:
            return max(new)
        if clock() >= deadline:
            raise PostNowError(f"timed out after {POLL_TIMEOUT_S}s waiting for the workflow run to appear")
        sleep(POLL_INTERVAL_S)


def _watch(run, run_id: int) -> None:
    if run(["gh", "run", "watch", str(run_id), "--exit-status"]).returncode == 0:
        return
    url = run(["gh", "run", "view", str(run_id), "--json", "url", "--jq", ".url"]).stdout.strip() or f"run {run_id}"
    raise PostNowError(f"workflow run {run_id} did not succeed: {url}")


def _posted(root: Path, entry_id: str) -> dict | None:
    path = queue.path_for(root, "posted", entry_id)
    return json.loads(path.read_text()) if path.exists() else None


def post_now(root: Path, branch: str, run, *, sleep: Callable[[float], None] = time.sleep,
             clock: Callable[[], float] = time.monotonic, log: Callable[[str], None] = print) -> int:
    try:
        _check_branch(run, branch)
        _check_gh(run)
        _pull(run)
        pending = queue.load_all(root, "pending")
        if not pending:
            log("nothing to post: the queue is empty")
            return 0
        for _ in range(len(pending)):
            entry = queue.next_pending(root)
            if entry is None:
                break
            run_id = _start_run(run, _run_ids(run), sleep, clock)
            log(f"started workflow run {run_id} for {entry['id']}")
            _watch(run, run_id)
            _pull(run)
            posted = _posted(root, entry["id"])
            if posted is None:
                raise PostNowError(
                    f"workflow run {run_id} finished green but {entry['id']} is still queued (the daily "
                    f"quota may have been reached, or the run found nothing to post); check the run log")
            link = posted.get("permalink") or f"media id {posted.get('media_id')} (no link returned)"
            log(f"posted {entry['id']}: {link}")
        log(f"done: {len(pending) - len(queue.load_all(root, 'pending'))} posted")
        return 0
    except PostNowError as exc:
        log(f"error: {exc}")
        return 1
    except (ValueError, OSError) as exc:
        log(f"error: could not read the queue ({type(exc).__name__})")
        return 1


def main() -> int:
    cfg = load_publish_config()
    return post_now(queue.QUEUE_ROOT, cfg["queue_branch"], default_run)
