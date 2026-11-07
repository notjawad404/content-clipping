from datetime import datetime, timezone

from clipper.publish import post_next as post_next_module, queue
from clipper.publish.clips_repo import RepoError
from clipper.publish.config import PublishConfigError
from clipper.publish.gitops import GitError
from clipper.publish.instagram import ProcessingFailed, QuotaExceeded, TokenInvalid
from clipper.publish.post_next import post_next

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
CFG = {"max_attempts": 3, "poll_interval_s": 0, "poll_timeout_s": 1}
CAPTION = "Great clip #podcast"


class FakeClient:
    def __init__(self, usage=(0, 100), recent=None, status="IN_PROGRESS"):
        self.usage, self.recent, self.status = usage, recent or [], status
        self.calls = []
        self.errors = {}

    def _step(self, name):
        self.calls.append(name)
        if name in self.errors:
            raise self.errors[name]

    def publishing_limit(self):
        self._step("limit")
        return self.usage

    def create_reel_container(self, video_url, caption):
        self._step("create")
        return "c-new"

    def container_status(self, container_id):
        self._step("status")
        return self.status

    def wait_until_finished(self, container_id, interval, timeout):
        self._step("wait")

    def publish(self, container_id):
        self._step("publish")
        return "m-1"

    def permalink(self, media_id):
        self._step("permalink")
        return "https://instagram.com/reel/abc/"

    def recent_media(self, limit=5):
        self._step("recent")
        return self.recent


def setup(tmp_path, **fields):
    e = queue.new_entry(video_id="vid", clip_id="clip_01", campaign="health", caption=CAPTION,
                        asset_url="https://example.invalid/a.mp4", asset_id=7, queued_at="2026-11-07T10:00:00Z")
    e.update(fields)
    queue.save(tmp_path, "pending", e)
    return e


def run(tmp_path, client, **kwargs):
    deleted, commits = [], []
    code = post_next(tmp_path, client, CFG, deleted.append, commit=commits.append, now=NOW,
                     log=lambda message: None, **kwargs)
    return code, deleted, commits


def test_empty_queue_does_nothing(tmp_path):
    client = FakeClient()
    assert run(tmp_path, client)[0] == 0
    assert client.calls == []


def test_happy_path_posts_and_cleans_up(tmp_path):
    setup(tmp_path)
    client = FakeClient()
    code, deleted, commits = run(tmp_path, client)
    assert code == 0
    assert client.calls == ["limit", "create", "wait", "publish", "permalink"]
    assert queue.load_all(tmp_path, "pending") == []
    posted = queue.load_all(tmp_path, "posted")[0]
    assert posted["media_id"] == "m-1" and posted["permalink"] == "https://instagram.com/reel/abc/"
    assert deleted == [7]
    assert len(commits) == 3


def test_quota_reached_waits_without_an_attempt(tmp_path):
    setup(tmp_path)
    client = FakeClient(usage=(100, 100))
    assert run(tmp_path, client)[0] == 0
    assert client.calls == ["limit"]
    assert queue.load_all(tmp_path, "pending")[0]["attempts"] == 0


def test_processing_failure_counts_an_attempt_and_keeps_the_container(tmp_path):
    setup(tmp_path)
    client = FakeClient()
    client.errors["wait"] = ProcessingFailed("container ERROR")
    code, deleted, _ = run(tmp_path, client)
    pending = queue.load_all(tmp_path, "pending")[0]
    assert code == 1 and deleted == []
    assert pending["attempts"] == 1 and pending["last_error"] == "container ERROR"
    assert pending["container_id"] == "c-new"


def test_third_failure_moves_the_entry_to_failed(tmp_path):
    setup(tmp_path, attempts=2)
    client = FakeClient()
    client.errors["wait"] = ProcessingFailed("container ERROR")
    assert run(tmp_path, client)[0] == 1
    assert queue.load_all(tmp_path, "pending") == []
    assert queue.load_all(tmp_path, "failed")[0]["attempts"] == 3


def test_invalid_token_fails_without_an_attempt(tmp_path):
    setup(tmp_path)
    client = FakeClient()
    client.errors["limit"] = TokenInvalid("bad token")
    assert run(tmp_path, client)[0] == 1
    assert queue.load_all(tmp_path, "pending")[0]["attempts"] == 0


def test_quota_error_on_publish_waits_without_an_attempt(tmp_path):
    setup(tmp_path)
    client = FakeClient()
    client.errors["publish"] = QuotaExceeded("quota")
    assert run(tmp_path, client)[0] == 0
    assert queue.load_all(tmp_path, "pending")[0]["attempts"] == 0


def test_entry_already_published_only_finishes_cleanup(tmp_path):
    setup(tmp_path, media_id="m-7")
    client = FakeClient()
    code, deleted, _ = run(tmp_path, client)
    assert code == 0 and client.calls == [] and deleted == [7]
    assert queue.load_all(tmp_path, "posted")[0]["media_id"] == "m-7"


def test_asset_delete_failure_does_not_fail_the_run(tmp_path):
    setup(tmp_path)

    def broken_delete(asset_id):
        raise RepoError("nope")

    code = post_next(tmp_path, FakeClient(), CFG, broken_delete, now=NOW, log=lambda message: None)
    assert code == 0 and queue.load_all(tmp_path, "posted")


def test_dry_run_creates_and_waits_but_changes_nothing(tmp_path):
    setup(tmp_path)
    client = FakeClient()
    code, deleted, commits = run(tmp_path, client, dry_run=True)
    pending = queue.load_all(tmp_path, "pending")[0]
    assert code == 0 and client.calls == ["limit", "create", "wait"]
    assert pending["container_id"] is None and pending["attempts"] == 0
    assert deleted == [] and commits == [] and queue.load_all(tmp_path, "posted") == []


def test_existing_usable_container_is_reused(tmp_path):
    setup(tmp_path, container_id="c-old")
    client = FakeClient(status="IN_PROGRESS")
    run(tmp_path, client)
    assert "create" not in client.calls and client.calls[:3] == ["limit", "status", "wait"]


def test_retry_finds_a_recent_identical_post_and_does_not_publish_again(tmp_path):
    setup(tmp_path, container_id="c-old")
    recent = [{"id": "m-9", "caption": CAPTION, "timestamp": "2026-11-07T11:00:00+0000",
               "permalink": "https://instagram.com/reel/dup/"}]
    client = FakeClient(status="FINISHED", recent=recent)
    assert run(tmp_path, client)[0] == 0
    assert "publish" not in client.calls
    assert queue.load_all(tmp_path, "posted")[0]["media_id"] == "m-9"


def test_retry_ignores_an_identical_post_older_than_24_hours(tmp_path):
    setup(tmp_path, container_id="c-old")
    recent = [{"id": "m-9", "caption": CAPTION, "timestamp": "2026-11-05T11:00:00+0000"}]
    client = FakeClient(status="FINISHED", recent=recent)
    run(tmp_path, client)
    assert "publish" in client.calls


def test_first_attempt_never_treats_an_identical_caption_as_a_duplicate(tmp_path):
    setup(tmp_path)
    recent = [{"id": "m-9", "caption": CAPTION, "timestamp": "2026-11-07T11:00:00+0000"}]
    client = FakeClient(recent=recent)
    run(tmp_path, client)
    assert "recent" not in client.calls and "publish" in client.calls


def failing_commit(fail_on):
    """A commit callable that raises GitError once the message contains `fail_on`."""
    def commit(message):
        if fail_on in message:
            raise GitError("git push failed: rejected")
    return commit


def run_logged(tmp_path, client, deleted=None, **kwargs):
    logs = []
    deleted = [] if deleted is None else deleted
    code = post_next(tmp_path, client, CFG, deleted.append, now=NOW, log=logs.append, **kwargs)
    return code, deleted, logs


def test_commit_failure_after_publish_is_reported_and_keeps_the_media_id(tmp_path):
    setup(tmp_path, container_id="c-old")
    client = FakeClient(status="FINISHED")
    code, deleted, logs = run_logged(tmp_path, client, commit=failing_commit("published"))
    pending = queue.load_all(tmp_path, "pending")[0]
    assert code == 1 and deleted == []
    assert pending["media_id"] == "m-1" and pending["attempts"] == 0
    assert any("m-1" in line and "git push failed" in line for line in logs)


def test_commit_failure_when_saving_the_container_does_not_count_an_attempt(tmp_path):
    setup(tmp_path)
    client = FakeClient()
    code, _, logs = run_logged(tmp_path, client, commit=failing_commit("container"))
    pending = queue.load_all(tmp_path, "pending")[0]
    assert code == 1 and "publish" not in client.calls
    assert pending["attempts"] == 0
    assert any("git push failed" in line for line in logs)


def test_commit_failure_while_recording_a_failure_still_exits_nonzero(tmp_path):
    setup(tmp_path)
    client = FakeClient()
    client.errors["wait"] = ProcessingFailed("container ERROR")
    code, _, logs = run_logged(tmp_path, client, commit=failing_commit("failed for"))
    assert code == 1
    assert queue.load_all(tmp_path, "pending")[0]["attempts"] == 1
    assert any("git push failed" in line for line in logs)


def test_commit_failure_after_cleanup_is_reported(tmp_path):
    setup(tmp_path, media_id="m-7")
    code, deleted, logs = run_logged(tmp_path, FakeClient(), commit=failing_commit("posted"))
    assert code == 1 and deleted == [7]
    assert any("m-7" in line and "git push failed" in line for line in logs)


def test_unreadable_queue_entry_is_reported_not_raised(tmp_path):
    (tmp_path / "pending").mkdir()
    (tmp_path / "pending" / "bad.json").write_text("{not json")
    client = FakeClient()
    code, _, logs = run_logged(tmp_path, client)
    assert code == 1 and client.calls == []
    assert any(line.startswith("error: could not read the queue") for line in logs)


def test_unexpected_publish_error_is_reported_without_an_attempt(tmp_path):
    setup(tmp_path)
    client = FakeClient()
    client.errors["limit"] = GitError("boom")
    code, _, logs = run_logged(tmp_path, client)
    assert code == 1 and queue.load_all(tmp_path, "pending")[0]["attempts"] == 0
    assert logs[-1] == "error: boom"


def test_main_requires_the_token(monkeypatch, capsys):
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    assert post_next_module.main([]) == 2
    assert "IG_ACCESS_TOKEN" in capsys.readouterr().out


def test_main_reports_a_config_error_without_leaking_the_token(monkeypatch, capsys):
    monkeypatch.setenv("IG_ACCESS_TOKEN", "super-secret-token")

    def broken():
        raise PublishConfigError("missing posting config: publish.yaml")

    monkeypatch.setattr(post_next_module, "load_publish_config", broken)
    assert post_next_module.main([]) == 2
    out = capsys.readouterr().out
    assert "missing posting config" in out and "super-secret-token" not in out
