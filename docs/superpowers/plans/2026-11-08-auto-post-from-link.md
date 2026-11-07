# Paste a Link, Get Clips Posted — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pasted YouTube link in a new Claude session produces up to 5 clips and posts every clip that passes to Instagram, unless the user names a count or asks to schedule.

**Architecture:** A new `clipper post-now` command drains the existing posting queue by running the live `post-next` workflow once per pending entry (via `gh`), waiting for each run and verifying the entry reached `queue/posted/`. The `clipper` skill is extended with the defaults (5 clips, post now), campaign-from-video selection, and a queue-and-post step. No change to the posting workflow, the queue format or the Instagram client.

**Tech Stack:** Python 3.12, stdlib `subprocess`/`json`/`time`, pytest, `gh` and `git` CLIs, the existing `clipper.publish` package.

Spec: `docs/superpowers/specs/2026-11-08-auto-post-from-link-design.md`

## Global Constraints

- Python is 3.12. Run tests with `uv run pytest`.
- `clipper/publish/post_now.py` may import only the standard library, `clipper.env`, `clipper.publish` (`PublishError`, `queue`) and `clipper.publish.config`. It must NOT import `clipper.cli` or anything heavy (opencv/mediapipe/parakeet/yt_dlp/numpy).
- All `gh`/`git` calls go through an injectable `run(args: list[str])` returning an object with `.returncode`, `.stdout`, `.stderr`. Tests never call real `gh`, `git`, GitHub or Instagram.
- Typed errors only: failures raise or return as `PostNowError(PublishError)` with one-line messages. Messages never contain tokens; OS errors report the class name only.
- The command refuses to run unless the current branch equals `queue_branch` from `config/publish.yaml` (`master`), with the message `refusing to run: you are on '<current>' but the queue lives on '<branch>'; switch with \`git checkout <branch>\``.
- Workflow file is `post-next.yml`; the live run is triggered with `gh workflow run post-next.yml -f dry_run=false`.
- New-run polling: every 5 s, up to 90 s. Queue order is oldest `queued_at` first, ties by id (`queue.next_pending`).
- Default clip count is 5 (`max_clips: 5` in `config/style.yaml`); the quality bar `min_score: 7.0` is unchanged.
- End every commit message with a second `-m` argument exactly `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Do not stage the untracked `config/campaigns/gta6-t2-ceo.yaml`, `health.yaml` or `iced-coffee-hour-greg-lav.yaml`. Always `git add` explicit paths.
- Work on branch `master` (that is where the queue and cron live). Do not push; the owner decides when.

## File Structure

| File | Responsibility |
|---|---|
| `clipper/publish/post_now.py` | The `post-now` logic: guards, trigger, wait, verify, summary |
| `clipper/cli.py` | `post-now` subcommand wiring |
| `config/style.yaml` | `max_clips: 5` |
| `.claude/skills/clipper/SKILL.md` | Defaults, campaign-from-video, queue-and-post step, final report |
| `README.md` | Describe the one-link flow |
| `docs/superpowers/specs/2026-11-08-auto-post-from-link-design.md` | Small alignment edit (permalink may be absent; summary counts from the queue) |
| `tests/test_publish_post_now.py`, `tests/test_cli.py`, `tests/test_config.py` | Tests |

---

### Task 1: The `post-now` module

**Files:**
- Create: `clipper/publish/post_now.py`
- Test: `tests/test_publish_post_now.py`
- Modify: `docs/superpowers/specs/2026-11-08-auto-post-from-link-design.md` (§2 steps 5 and 7)

**Interfaces:**
- Consumes: `queue.load_all(root, state) -> list[dict]`, `queue.next_pending(root) -> dict | None`, `queue.path_for(root, state, entry_id) -> Path`, `queue.QUEUE_ROOT`, `queue.save`, `queue.move`, `queue.new_entry` (tests); `config.load_publish_config() -> dict` with key `queue_branch`; `PublishError`.
- Produces: `PostNowError(PublishError)`; `POLL_INTERVAL_S = 5`, `POLL_TIMEOUT_S = 90`; `default_run(args) -> CompletedProcess` (raises `PostNowError` for OS errors and timeouts); `post_now(root, branch, run, *, sleep=time.sleep, clock=time.monotonic, log=print) -> int` (0 = all pending posted or nothing to post; 1 = stopped on a `PostNowError` or an unreadable queue); `main() -> int` (loads config, calls `post_now(queue.QUEUE_ROOT, cfg["queue_branch"], default_run)`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_publish_post_now.py`:

```python
import json
import subprocess
from types import SimpleNamespace

import pytest

from clipper.publish import post_now as post_now_mod
from clipper.publish import queue
from clipper.publish.post_now import PostNowError, default_run, post_now


def proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def add_pending(root, clip, queued_at="2026-11-08T10:00:00Z"):
    queue.save(root, "pending", queue.new_entry(
        video_id="vid", clip_id=clip, campaign=None, caption="caption", asset_url="https://x/a.mp4",
        asset_id=1, queued_at=queued_at))


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


class Fake:
    """Stands in for git and gh. A triggered run finishes at once according to its behavior:
    ok -> posts the oldest pending entry; fail -> posts nothing and `gh run watch` exits 1;
    green-no-post -> posts nothing but exits 0; cron-first -> posts the two oldest entries."""

    def __init__(self, root, branch="master", auth_ok=True, existing_runs=(100,), appear_after=0, plan=()):
        self.root, self.branch, self.auth_ok = root, branch, auth_ok
        self.runs = list(existing_runs)
        self.appear_after = appear_after  # run-list polls that must pass before the new run is listed
        self.plan = list(plan)
        self.behavior = {}
        self.calls = []
        self._hidden = None
        self._next_id = 200

    def triggered(self):
        return [c for c in self.calls if c[:3] == ["gh", "workflow", "run"]]

    def _post_oldest(self):
        entry = queue.next_pending(self.root)
        if entry is not None:
            entry.update(media_id=f"m-{entry['id']}", permalink=f"https://instagram.com/reel/{entry['id']}/")
            queue.move(self.root, entry, "pending", "posted")

    def __call__(self, args):
        self.calls.append(args)
        if args[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return proc(0, self.branch + "\n")
        if args[:3] == ["gh", "auth", "status"]:
            return proc(0 if self.auth_ok else 1, "", "not logged in")
        if args[:3] == ["git", "pull", "--rebase"]:
            return proc(0)
        if args[:3] == ["gh", "workflow", "run"]:
            behavior = self.plan.pop(0) if self.plan else "ok"
            run_id = self._next_id
            self._next_id += 1
            self.behavior[str(run_id)] = behavior
            if behavior in ("ok", "cron-first"):
                self._post_oldest()
            if behavior == "cron-first":
                self._post_oldest()
            self._hidden = [run_id, self.appear_after]
            return proc(0)
        if args[:3] == ["gh", "run", "list"]:
            ids = list(self.runs)
            if self._hidden is not None:
                run_id, left = self._hidden
                if left <= 0:
                    self.runs.append(run_id)
                    ids.append(run_id)
                    self._hidden = None
                else:
                    self._hidden[1] -= 1
            return proc(0, json.dumps([{"databaseId": i} for i in ids]))
        if args[:3] == ["gh", "run", "watch"]:
            return proc(1 if self.behavior.get(args[3]) == "fail" else 0)
        if args[:3] == ["gh", "run", "view"]:
            return proc(0, f"https://github.com/o/r/actions/runs/{args[3]}\n")
        return proc(1, "", f"unexpected command {args}")


def go(root, run, clock=None):
    clock = clock or Clock()
    logs = []
    code = post_now(root, "master", run, sleep=clock.sleep, clock=clock, log=logs.append)
    return code, logs, clock


def test_refuses_to_run_off_the_queue_branch(tmp_path):
    add_pending(tmp_path, "clip_01")
    fake = Fake(tmp_path, branch="feature/x")
    code, logs, _ = go(tmp_path, fake)
    assert code == 1
    assert "'feature/x'" in logs[0] and "git checkout master" in logs[0]
    assert fake.triggered() == []


def test_stops_when_gh_is_not_logged_in(tmp_path):
    add_pending(tmp_path, "clip_01")
    fake = Fake(tmp_path, auth_ok=False)
    code, logs, _ = go(tmp_path, fake)
    assert code == 1 and "gh auth login" in logs[0]
    assert fake.triggered() == []


def test_stops_when_the_pull_fails(tmp_path):
    add_pending(tmp_path, "clip_01")
    fake = Fake(tmp_path)

    def run(args):
        if args[:3] == ["git", "pull", "--rebase"]:
            return proc(1, "", "conflict")
        return fake(args)

    code, logs, _ = go(tmp_path, run)
    assert code == 1 and "git pull --rebase failed: conflict" in logs[0]
    assert fake.triggered() == []


def test_empty_queue_posts_nothing(tmp_path):
    fake = Fake(tmp_path)
    code, logs, _ = go(tmp_path, fake)
    assert code == 0 and logs == ["nothing to post: the queue is empty"]
    assert fake.triggered() == []


def test_posts_every_pending_entry_in_order(tmp_path):
    for clip in ("clip_03", "clip_01", "clip_02"):
        add_pending(tmp_path, clip)
    fake = Fake(tmp_path)
    code, logs, _ = go(tmp_path, fake)
    assert code == 0
    posted_lines = [line for line in logs if line.startswith("posted ")]
    assert posted_lines == [
        "posted vid_clip_01: https://instagram.com/reel/vid_clip_01/",
        "posted vid_clip_02: https://instagram.com/reel/vid_clip_02/",
        "posted vid_clip_03: https://instagram.com/reel/vid_clip_03/",
    ]
    assert logs[-1] == "done: 3 posted"
    assert len(fake.triggered()) == 3
    assert fake.triggered()[0] == ["gh", "workflow", "run", "post-next.yml", "-f", "dry_run=false"]
    assert queue.load_all(tmp_path, "pending") == []


def test_stops_at_the_first_failed_run_and_does_not_trigger_the_next(tmp_path):
    for clip in ("clip_01", "clip_02", "clip_03"):
        add_pending(tmp_path, clip)
    fake = Fake(tmp_path, plan=["ok", "fail"])
    code, logs, _ = go(tmp_path, fake)
    assert code == 1
    assert logs[-1] == "error: workflow run 201 did not succeed: https://github.com/o/r/actions/runs/201"
    assert len(fake.triggered()) == 2
    assert [e["id"] for e in queue.load_all(tmp_path, "posted")] == ["vid_clip_01"]
    assert [e["id"] for e in queue.load_all(tmp_path, "pending")] == ["vid_clip_02", "vid_clip_03"]


def test_a_green_run_that_posted_nothing_is_not_reported_as_posted(tmp_path):
    add_pending(tmp_path, "clip_01")
    fake = Fake(tmp_path, plan=["green-no-post"])
    code, logs, _ = go(tmp_path, fake)
    assert code == 1
    assert "vid_clip_01" in logs[-1] and "still queued" in logs[-1]
    assert not any(line.startswith("posted ") for line in logs)
    assert [e["id"] for e in queue.load_all(tmp_path, "pending")] == ["vid_clip_01"]


def test_the_new_run_is_found_among_existing_runs_after_a_delay(tmp_path):
    add_pending(tmp_path, "clip_01")
    fake = Fake(tmp_path, existing_runs=(5, 100), appear_after=2)
    code, logs, clock = go(tmp_path, fake)
    assert code == 0
    assert clock.sleeps == [5, 5]
    assert ["gh", "run", "watch", "200", "--exit-status"] in fake.calls


def test_a_run_that_never_appears_times_out_cleanly(tmp_path):
    add_pending(tmp_path, "clip_01")
    fake = Fake(tmp_path, appear_after=10**6)
    code, logs, clock = go(tmp_path, fake)
    assert code == 1 and "timed out after 90s" in logs[-1]
    assert len(clock.sleeps) == 18
    assert not any(c[:3] == ["gh", "run", "watch"] for c in fake.calls)


def test_an_entry_posted_by_a_concurrent_run_still_counts(tmp_path):
    add_pending(tmp_path, "clip_01")
    add_pending(tmp_path, "clip_02")
    fake = Fake(tmp_path, plan=["cron-first"])
    code, logs, _ = go(tmp_path, fake)
    assert code == 0 and logs[-1] == "done: 2 posted"
    assert len(fake.triggered()) == 1


def test_unparseable_run_list_output_stops(tmp_path):
    add_pending(tmp_path, "clip_01")
    fake = Fake(tmp_path)

    def run(args):
        if args[:3] == ["gh", "run", "list"]:
            return proc(0, "not json")
        return fake(args)

    code, logs, _ = go(tmp_path, run)
    assert code == 1 and "unexpected output from gh run list" in logs[-1]
    assert fake.triggered() == []


def test_a_corrupt_queue_file_stops_with_a_clear_message(tmp_path):
    (tmp_path / "pending").mkdir()
    (tmp_path / "pending" / "bad.json").write_text("{not json")
    code, logs, _ = go(tmp_path, Fake(tmp_path))
    assert code == 1 and "could not read the queue" in logs[-1]


def test_default_run_reports_a_missing_program_by_class_name(monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError("gh: no such file")

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(PostNowError) as caught:
        default_run(["gh", "auth", "status"])
    assert str(caught.value) == "could not run gh: FileNotFoundError"


def test_main_passes_the_configured_branch_and_real_runner(monkeypatch):
    seen = []
    monkeypatch.setattr(post_now_mod, "load_publish_config", lambda: {"queue_branch": "master"})
    monkeypatch.setattr(post_now_mod, "post_now", lambda root, branch, run, **kw: seen.append((root, branch, run)) or 0)
    assert post_now_mod.main() == 0
    assert seen == [(queue.QUEUE_ROOT, "master", default_run)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish_post_now.py -v`
Expected: collection error `ImportError: cannot import name 'post_now' from 'clipper.publish'`

- [ ] **Step 3: Write minimal implementation**

Create `clipper/publish/post_now.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publish_post_now.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Verify the module imports without heavy dependencies**

Run: `uv run python -c "import sys; import clipper.publish.post_now; bad = [m for m in sys.modules if m.split('.')[0] in ('cv2', 'mediapipe', 'parakeet_mlx', 'mlx', 'yt_dlp', 'scenedetect', 'numpy')]; assert not bad, bad; print('light imports only')"`
Expected: `light imports only`

- [ ] **Step 6: Align the spec with two behaviors the plan fixes**

In `docs/superpowers/specs/2026-11-08-auto-post-from-link-design.md` §2:
- Step 5: replace "with a `permalink`. If it did not" with "(the permalink is printed when present; a post without a returned link is still a post and is reported with its media id). If it was not moved". Keep the rest of the sentence.
- Step 7: replace "print a summary line with the count posted and exit 0" with "print `done: <n> posted`, where n is the number of entries that left `pending/` during the run, and exit 0".

- [ ] **Step 7: Run the whole suite, then commit**

Run: `uv run pytest -q`
Expected: all tests pass.

```bash
git add clipper/publish/post_now.py tests/test_publish_post_now.py docs/superpowers/specs/2026-11-08-auto-post-from-link-design.md
git commit -m "feat: clipper post-now drains the queue through the live workflow" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: CLI wiring

**Files:**
- Modify: `clipper/cli.py` (imports, `cmd_post_now` after `cmd_post_next`, `build_parser`, `HANDLERS`)
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `clipper.publish.post_now.main() -> int`.
- Produces: subcommand `clipper post-now` (no arguments).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_parser_post_now():
    assert build_parser().parse_args(["post-now"]).command == "post-now"


def test_post_now_command_delegates_and_returns_its_exit_code(monkeypatch):
    codes = iter([0, 1])
    monkeypatch.setattr(cli.post_now_mod, "main", lambda: next(codes))
    assert cli.main(["post-now"]) == 0
    assert cli.main(["post-now"]) == 1


def test_post_now_publish_errors_are_one_line_exit_2(monkeypatch, capsys):
    def boom():
        raise cli.PublishError("config is broken")

    monkeypatch.setattr(cli.post_now_mod, "main", boom)
    assert cli.main(["post-now"]) == 2
    assert "error: config is broken" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k post_now -v`
Expected: FAIL (`SystemExit` from argparse for the invalid choice, and `AttributeError: ... post_now_mod`)

- [ ] **Step 3: Write minimal implementation**

In `clipper/cli.py` imports, add after `from clipper.publish import post_next as post_next_mod`:

```python
from clipper.publish import post_now as post_now_mod
```

Add after `cmd_post_next`:

```python
def cmd_post_now(args: argparse.Namespace) -> int:
    return post_now_mod.main()
```

In `build_parser`, after the `post-next` parser:

```python
    sub.add_parser("post-now", help="post every queued clip now by running the live workflow once per clip")
```

Add `"post-now": cmd_post_now` to `HANDLERS`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add clipper/cli.py tests/test_cli.py
git commit -m "feat: wire clipper post-now into the CLI" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Defaults, skill and README

**Files:**
- Modify: `config/style.yaml` (line `max_clips: 8`)
- Modify: `.claude/skills/clipper/SKILL.md`
- Modify: `README.md`
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Consumes: the `clipper queue` and `clipper post-now` commands from earlier tasks.
- Produces: the one-link behavior a new Claude session follows.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_shipped_style_defaults_to_five_clips():
    assert load_config(None)["max_clips"] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_shipped_style_defaults_to_five_clips -v`
Expected: FAIL with `assert 8 == 5`

- [ ] **Step 3: Change the default**

In `config/style.yaml` change `max_clips: 8` to `max_clips: 5`.

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 4: Update the skill**

Edit `.claude/skills/clipper/SKILL.md` with these exact changes.

a) Frontmatter `description:` — replace the whole line with:

```
description: Use when the user gives a YouTube podcast or video link and wants short vertical clips (Reels, TikTok, Shorts, X) found, cut, captioned and edited, and by default posted to Instagram. Runs the local clipper pipeline in this repo; Claude chooses and scores the moments and writes the post copy.
```

b) Replace the paragraph that starts `Turns one YouTube link into finished` with:

```
Turns one YouTube link into finished 1080×1920 clips plus ready-to-paste post captions, and by default posts them to Instagram. Code downloads, transcribes, reframes, renders and posts. **You** choose the moments, score them, write the hook text and post copy, and check the result visually.

**Default when the user only pastes a link:** make up to 5 clips, then post every clip that passes to Instagram right away (section 7), with no further questions. Only stop for the cases named below: a YouTube bot check, `review first`, or a failed step.
```

c) In section `## 0. Preflight`, append this after the existing paragraph:

```
Then check, before any download, that posting will work, so a problem shows up in the first minute and not after the render:
- `gh auth status` succeeds. If not, tell the user to run `gh auth login` and stop.
- `git branch --show-current` prints `master` (queueing only works there). If not, run `git checkout master`; if that fails because of local changes, stop and tell the user.
```

d) In section `## 1. Read the request`, replace the `- **Campaign:**` bullet with these bullets:

```
- **Count:** if the user names one ("only 3", "10 clips", "just the best clip"), use it (`max_clips: N` in overrides.yaml). Otherwise 5.
- **Mode:** if the user says "schedule them", "spread them out" or "through the day", only queue the clips; the cron posts one clip per run at 09:00, 13:00 and 19:00 UTC (3 a day). Anything else means post now.
- **Campaign:** if the user names one, it must exist as `config/campaigns/<name>.yaml`. If it doesn't, ask for the brief's rules (creator tag, required caption text, required hashtags, length limits, banned topics) and create the file by copying `config/campaigns/example.yaml`. If the user names none, choose from the video after `prepare` has written `meta.json`: read every `config/campaigns/*.yaml` except `example.yaml` and compare each file's creator tag, required text, name and comments with the video's channel, title and description. Pick a campaign only on a clear match (the creator or show is named, or the campaign is plainly about the video's topic); otherwise use none. If one applies, run `uv run clipper prepare "<url>" --campaign <name>` again (everything is cached, so it takes seconds) before selecting clips. Remember which campaign you used, or that you used none, and why; you report it at the end.
```

e) In section `## 6. QA`, append this sentence to the end of the last paragraph (the one that ends `Never hide a failure.`):

```
A clip that still fails the visual check after that one fix attempt is not posted; note it so it can be reported.
```

f) Insert this new section between `## 6. QA (your job)` and `## 7. Finish`, and rename `## 7. Finish` to `## 8. Finish`:

```
## 7. Queue and post

Only clips that passed QA go forward.

1. `uv run clipper queue <video_id> --only <passing clip ids>` uploads each clip and commits the queue entries. It only works on `master`.
2. **Post now (default):** run `uv run clipper post-now` with `run_in_background: true` (each post takes about two minutes, so five clips take about ten) and wait for it to finish. It prints `posted <id>: <link>` for each clip and stops at the first failure. **Schedule mode:** stop after step 1 and tell the user the cron posts one clip at 09:00, 13:00 and 19:00 UTC.
3. If `post-now` stops with an error, report it with the run link it printed. Do not retry in a loop. Clips already posted stay posted and the rest stay queued; running `uv run clipper post-now` again continues from the queue.
4. If `post-now` also posted clips from older videos (their ids appear in its output), say so.
```

g) In the renamed `## 8. Finish`, replace the bullet list under `Then tell the user:` with:

```
- each posted Reel link, one per clip with its title and score; in schedule mode, which clips are queued and when the cron will post them;
- the campaign used (or "none") and why;
- how many clips cleared the quality bar if that is fewer than requested, and any clip that was skipped or failed and why (see `summary.md`);
- the folder `output/<video_id>/`, where each `clip_XX_post.md` holds the ready-to-paste caption for every platform;
- Content Rewards reminder: submit the post links within 30 minutes, and don't edit the posts after submitting.
```

- [ ] **Step 5: Update the README**

In `README.md`, replace the paragraph that starts `In Claude Code, in this folder:` through the sentence `Clips have no sound effects.` with:

````markdown
In Claude Code, in this folder, paste a YouTube link:

> https://www.youtube.com/watch?v=…

By default Claude makes up to 5 clips and posts every clip that passes to Instagram, then lists the Reel links. Add plain-word changes: a count ("only 3", "10 clips"), "schedule them" or "spread them through the day" (queue only; the cron posts 3 a day at 09:00, 13:00 and 19:00 UTC), "campaign `<name>`" (otherwise Claude picks one from the video only on a clear match), "under 30 seconds", "no zooms", "blue captions", "review first". Clips have no sound effects.

Posting needs `gh auth login` and the `master` branch checked out. If posting stops with an error, run `uv run clipper post-now` to continue from the queue.
````

- [ ] **Step 6: Verify the edits landed**

Run: `grep -n "Default when the user only pastes\|## 7. Queue and post\|## 8. Finish\|gh auth status\|post-now" .claude/skills/clipper/SKILL.md`
Expected: each phrase appears at least once and `## 7. Finish` no longer exists.

Run: `grep -c "post-now" README.md`
Expected: `1` or more.

- [ ] **Step 7: Run the whole suite, then commit**

Run: `uv run pytest -q`
Expected: all tests pass.

```bash
git add config/style.yaml .claude/skills/clipper/SKILL.md README.md tests/test_config.py
git commit -m "feat: five clips by default and a queue-and-post step in the clipper skill" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Acceptance run (manual, with the owner; posts publicly)

**Files:** none.

This is run by the controller together with the owner, not by a subagent, because it posts real Reels. Do not start it until the owner has given a YouTube link and said to go.

- [ ] **Step 1: Push the new code so a new session sees it**

Run `git push origin master` only after the owner confirms. The posting workflow is unchanged, so this does not affect the cron.

- [ ] **Step 2: Fresh-session test**

The owner opens a NEW Claude Code session in this folder and pastes a link with no other words. Expected: Claude runs preflight (doctor, `gh auth status`, branch check), prepares, picks a campaign or none and says why, makes up to 5 clips, checks the frames, queues the passing ones, runs `post-now`, and ends with the Reel links and the Content Rewards reminder.

- [ ] **Step 3: Variant checks (owner's choice)**

Optionally repeat with "only 2 clips" and with "schedule them" to confirm the count override and queue-only mode (the cron then posts at the next 09:00, 13:00 or 19:00 UTC slot).

- [ ] **Step 4: Report**

Tell the owner what posted, what was skipped and why, and anything that needed manual help.
