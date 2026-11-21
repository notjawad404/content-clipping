from datetime import datetime, timezone

import pytest

from clipper.publish import queue
from clipper.publish.instagram import ProcessingFailed, TokenInvalid as IgTokenInvalid
from clipper.publish.post_next import DownloadError, YouTubePoster, post_next
from clipper.publish.youtube import ApiError, QuotaExceeded, TokenInvalid, YtError
from tests.test_publish_post_next import CFG, FakeClient, NOW, setup

LOG = []


class FakePoster:
    key, name, token_hint = "youtube", "YouTube", "regenerate it"
    token_invalid, quota, api_error = TokenInvalid, QuotaExceeded, YtError

    def __init__(self):
        self.posted, self.checked, self.error = [], 0, None

    def check(self):
        self.checked += 1
        if self.error:
            raise self.error

    def post(self, entry):
        if self.error:
            raise self.error
        self.posted.append(entry["id"])
        return "yt1", "https://www.youtube.com/shorts/yt1"


def run(tmp_path, client, poster, **kwargs):
    deleted, commits, logs = [], [], []
    code = post_next(tmp_path, client, CFG, deleted.append, commit=commits.append, now=NOW,
                     log=logs.append, youtube=poster, **kwargs)
    return code, deleted, commits, logs


def test_both_platforms_succeed_then_cleanup_once(tmp_path):
    setup(tmp_path)
    poster = FakePoster()
    code, deleted, commits, logs = run(tmp_path, FakeClient(), poster)
    assert code == 0 and poster.posted == ["vid_clip_01"]
    assert queue.load_all(tmp_path, "pending") == []
    posted = queue.load_all(tmp_path, "posted")[0]
    assert posted["media_id"] == "m-1" and posted["youtube"]["video_id"] == "yt1"
    assert deleted == [7]
    assert any("YouTube: https://www.youtube.com/shorts/yt1" in line for line in logs)
    assert "queue: youtube published vid_clip_01" in commits


def test_youtube_failure_keeps_instagram_result_and_asset(tmp_path):
    setup(tmp_path)
    poster = FakePoster()
    poster.error = ApiError("bad video", 400, "invalidVideo")
    code, deleted, _, _ = run(tmp_path, FakeClient(), poster)
    pending = queue.load_all(tmp_path, "pending")[0]
    assert code == 1 and deleted == []
    assert pending["media_id"] == "m-1" and pending["attempts"] == 0
    assert pending["youtube"]["attempts"] == 1 and pending["youtube"]["last_error"] == "bad video"


def test_next_run_retries_only_youtube(tmp_path):
    setup(tmp_path, media_id="m-1", permalink="https://instagram.com/reel/abc/",
          youtube={"video_id": None, "url": None, "attempts": 1, "last_error": "x"})
    client, poster = FakeClient(), FakePoster()
    code, deleted, _, _ = run(tmp_path, client, poster)
    assert code == 0 and client.calls == [] and poster.posted == ["vid_clip_01"]
    assert deleted == [7] and queue.load_all(tmp_path, "posted")[0]["youtube"]["video_id"] == "yt1"


def test_instagram_failure_does_not_block_youtube(tmp_path):
    setup(tmp_path)
    client, poster = FakeClient(), FakePoster()
    client.errors["wait"] = ProcessingFailed("container ERROR")
    code, deleted, _, _ = run(tmp_path, client, poster)
    pending = queue.load_all(tmp_path, "pending")[0]
    assert code == 1 and deleted == []
    assert pending["attempts"] == 1 and pending["youtube"]["video_id"] == "yt1"


def test_instagram_token_error_still_posts_to_youtube(tmp_path):
    setup(tmp_path)
    client, poster = FakeClient(), FakePoster()
    client.errors["limit"] = IgTokenInvalid("bad")
    code, _, _, _ = run(tmp_path, client, poster)
    assert code == 1 and poster.posted == ["vid_clip_01"]
    assert queue.load_all(tmp_path, "pending")[0]["youtube"]["video_id"] == "yt1"


def test_instagram_exhausted_stays_open_for_youtube_then_posts(tmp_path):
    setup(tmp_path, attempts=2)
    client, poster = FakeClient(), FakePoster()
    client.errors["wait"] = ProcessingFailed("container ERROR")
    poster.error = QuotaExceeded("quota")
    assert run(tmp_path, client, poster)[0] == 1
    assert queue.load_all(tmp_path, "failed") == []
    assert queue.load_all(tmp_path, "pending")[0]["attempts"] == 3
    poster.error = None
    code, deleted, _, _ = run(tmp_path, FakeClient(), poster)
    assert code == 0 and deleted == [7]
    posted = queue.load_all(tmp_path, "posted")[0]
    assert posted["media_id"] is None and posted["youtube"]["video_id"] == "yt1"


def test_both_exhausted_moves_to_failed_and_keeps_asset(tmp_path):
    setup(tmp_path, attempts=2, youtube={"video_id": None, "url": None, "attempts": 2, "last_error": None})
    client, poster = FakeClient(), FakePoster()
    client.errors["wait"] = ProcessingFailed("container ERROR")
    poster.error = ApiError("nope", 400, "x")
    code, deleted, _, _ = run(tmp_path, client, poster)
    assert code == 1 and deleted == []
    assert queue.load_all(tmp_path, "pending") == []
    assert queue.load_all(tmp_path, "failed")[0]["youtube"]["attempts"] == 3


def test_quota_and_token_errors_do_not_count_attempts(tmp_path):
    setup(tmp_path)
    poster = FakePoster()
    poster.error = QuotaExceeded("quota")
    assert run(tmp_path, FakeClient(), poster)[0] == 0
    assert queue.load_all(tmp_path, "pending")[0]["youtube"]["attempts"] == 0
    poster.error = TokenInvalid("revoked")
    assert run(tmp_path, FakeClient(), poster)[0] == 1
    assert queue.load_all(tmp_path, "pending")[0]["youtube"]["attempts"] == 0


def test_download_failure_is_not_counted(tmp_path):
    setup(tmp_path)
    poster = FakePoster()
    poster.error = DownloadError("could not download the clip: URLError")
    assert run(tmp_path, FakeClient(), poster)[0] == 1
    assert queue.load_all(tmp_path, "pending")[0]["youtube"]["attempts"] == 0


def test_old_entry_without_youtube_object_is_handled(tmp_path):
    entry = setup(tmp_path)
    del entry["youtube"]
    queue.save(tmp_path, "pending", entry)
    code, _, _, _ = run(tmp_path, FakeClient(), FakePoster())
    assert code == 0 and queue.load_all(tmp_path, "posted")[0]["youtube"]["video_id"] == "yt1"


def test_dry_run_checks_the_token_and_uploads_nothing(tmp_path):
    setup(tmp_path)
    poster = FakePoster()
    code, deleted, commits, _ = run(tmp_path, FakeClient(), poster, dry_run=True)
    assert code == 0 and poster.checked == 1 and poster.posted == []
    assert deleted == [] and commits == []
    assert len(queue.load_all(tmp_path, "pending")) == 1


def test_commit_failure_after_upload_is_reported_with_the_url(tmp_path):
    from clipper.publish.gitops import GitError
    setup(tmp_path, media_id="m-1")

    def commit(message):
        if "youtube" in message:
            raise GitError("git push failed")

    logs = []
    code = post_next(tmp_path, FakeClient(), CFG, lambda _: None, commit=commit, now=NOW, log=logs.append,
                     youtube=FakePoster())
    assert code == 1 and any("youtube.com/shorts/yt1" in line and "git push failed" in line for line in logs)


def poster_with(fetch, privacy="private"):
    class Client:
        uploads = []

        def upload(self, video, title, description, tags=None, privacy="private", category_id="22"):
            self.uploads.append((video, title, description, privacy))
            return "abc"

        def access_token(self):
            return "t"

    client = Client()
    return YouTubePoster(client, privacy, fetch=fetch), client


def test_poster_builds_title_and_description_with_shorts_tag():
    poster, client = poster_with(lambda url: b"BYTES", "unlisted")
    entry = {"caption": "cap", "title": "A title", "youtube_description": "About it", "asset_url": "u"}
    assert poster.post(entry) == ("abc", "https://www.youtube.com/shorts/abc")
    assert client.uploads == [(b"BYTES", "A title #Shorts", "About it\n\n#Shorts", "unlisted")]


def test_poster_falls_back_to_the_caption_and_respects_the_title_limit():
    poster, client = poster_with(lambda url: b"B")
    poster.post({"caption": "First line #x\nsecond", "asset_url": "u"})
    poster.post({"caption": "c", "title": "t" * 98, "youtube_description": "has #shorts already", "asset_url": "u"})
    assert client.uploads[0][1:3] == ("First line #x #Shorts", "First line #x\nsecond\n\n#Shorts")
    assert client.uploads[1][1:3] == ("t" * 98, "has #shorts already")


def test_poster_download_error_is_a_download_error():
    def boom(url):
        raise DownloadError("x")

    poster, _ = poster_with(boom)
    with pytest.raises(DownloadError):
        poster.post({"caption": "c", "asset_url": "u"})


def test_youtube_only_posts_and_finalizes_without_instagram(tmp_path):
    setup(tmp_path)
    poster = FakePoster()
    code, deleted, commits, logs = run(tmp_path, None, poster)
    assert code == 0 and poster.posted == ["vid_clip_01"]
    posted = queue.load_all(tmp_path, "posted")[0]
    assert posted["media_id"] is None and posted["youtube"]["video_id"] == "yt1"
    assert deleted == [7] and "queue: posted vid_clip_01" in commits


def test_youtube_only_moves_to_failed_after_the_last_attempt(tmp_path):
    setup(tmp_path, youtube={"video_id": None, "url": None, "attempts": 2, "last_error": None})
    poster = FakePoster()
    poster.error = ApiError("boom")
    code, deleted, _, _ = run(tmp_path, None, poster)
    assert code == 1 and deleted == []
    assert queue.load_all(tmp_path, "pending") == []
    assert queue.load_all(tmp_path, "failed")[0]["youtube"]["attempts"] == 3


def test_youtube_only_dry_run_changes_nothing(tmp_path):
    setup(tmp_path)
    poster = FakePoster()
    code, deleted, commits, _ = run(tmp_path, None, poster, dry_run=True)
    assert code == 0 and poster.checked == 1 and poster.posted == []
    assert deleted == [] and commits == [] and len(queue.load_all(tmp_path, "pending")) == 1
