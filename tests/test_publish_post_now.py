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
    green-no-post -> posts nothing but exits 0; cron-first -> posts the two oldest entries;
    to-failed -> moves the oldest entry to failed/ and exits 0; fail-to-failed -> same but exits 1."""

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

    def _fail_oldest(self):
        entry = queue.next_pending(self.root)
        if entry is not None:
            entry.update(last_error="IG 400: media not ready\nretry later")
            queue.move(self.root, entry, "pending", "failed")

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
            if behavior in ("to-failed", "fail-to-failed"):
                self._fail_oldest()
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
            return proc(1 if self.behavior.get(args[3]) in ("fail", "fail-to-failed") else 0)
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


def test_a_red_run_that_moved_the_entry_to_failed_says_so(tmp_path):
    add_pending(tmp_path, "clip_01")
    fake = Fake(tmp_path, plan=["fail-to-failed"])
    code, logs, _ = go(tmp_path, fake)
    assert code == 1
    last = logs[-1]
    assert "was moved to failed/" in last
    assert "(last_error: IG 400: media not ready retry later)" in last
    assert "https://github.com/o/r/actions/runs/200" in last
    assert "still queued" not in last
    assert [e["id"] for e in queue.load_all(tmp_path, "failed")] == ["vid_clip_01"]


def test_a_green_run_that_moved_the_entry_to_failed_says_so(tmp_path):
    add_pending(tmp_path, "clip_01")
    fake = Fake(tmp_path, plan=["to-failed"])
    code, logs, _ = go(tmp_path, fake)
    assert code == 1
    assert logs[-1] == (
        "error: workflow run 200 finished but vid_clip_01 was moved to failed/ "
        "(last_error: IG 400: media not ready retry later); check the Instagram profile before re-queueing")
    assert "still queued" not in logs[-1]


def test_a_pending_entry_missing_fields_stops_with_a_clear_message(tmp_path):
    (tmp_path / "pending").mkdir()
    (tmp_path / "pending" / "bad.json").write_text(json.dumps({"id": "x"}))
    fake = Fake(tmp_path)
    code, logs, _ = go(tmp_path, fake)
    assert code == 1
    assert logs[-1] == "error: the queue contains an unexpected entry (KeyError)"
    assert fake.triggered() == []


def test_a_posted_file_that_is_not_an_object_stops_with_a_clear_message(tmp_path):
    add_pending(tmp_path, "clip_01")
    fake = Fake(tmp_path, plan=["green-no-post"])

    def run(args):
        result = fake(args)
        if args[:3] == ["gh", "workflow", "run"]:
            (tmp_path / "posted").mkdir(exist_ok=True)
            (tmp_path / "posted" / "vid_clip_01.json").write_text("[]")
        return result

    code, logs, _ = go(tmp_path, run)
    assert code == 1
    assert logs[-1] == "error: the queue contains an unexpected entry (list)"


def test_default_run_reports_a_decode_error_by_class_name(monkeypatch):
    def boom(*args, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(PostNowError) as caught:
        default_run(["gh", "run", "list"])
    assert str(caught.value) == "could not run gh: UnicodeDecodeError"


def test_a_value_error_outside_the_queue_is_not_reported_as_a_queue_error(tmp_path):
    add_pending(tmp_path, "clip_01")
    fake = Fake(tmp_path)

    def run(args):
        if args[:3] == ["gh", "run", "list"]:
            raise ValueError("boom")
        return fake(args)

    with pytest.raises(ValueError, match="boom"):
        go(tmp_path, run)


def test_a_queue_error_from_a_queue_helper_stops_with_one_line(tmp_path, monkeypatch):
    add_pending(tmp_path, "clip_01")

    def bad(root):
        raise queue.QueueError("bad")

    monkeypatch.setattr(queue, "next_pending", bad)
    fake = Fake(tmp_path)
    code, logs, _ = go(tmp_path, fake)
    assert code == 1 and logs[-1] == "error: bad"
    assert fake.triggered() == []
