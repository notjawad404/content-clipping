import json

import pytest

from clipper.publish import queue
from clipper.publish.post_next import TikTokPoster, post_next, tiktok_drafts
from clipper.publish.youtube import QuotaExceeded as YtQuota, TokenInvalid as YtTokenInvalid, YtError
from clipper.publish.tiktok import (SINGLE_CHUNK_MAX, ApiError, QuotaExceeded, TikTokClient, TokenInvalid,
                                    chunk_plan)
from tests.test_publish_post_next import CFG, NOW, setup

OK = {"error": {"code": "ok", "message": ""}}


class FakeHttp:
    def __init__(self, statuses=("PUBLISH_COMPLETE",), token_status=200, init_error=None):
        self.calls, self.statuses, self.token_status, self.init_error = [], list(statuses), token_status, init_error
        self.inits = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if url.endswith("/oauth/token/"):
            if self.token_status != 200:
                return self.token_status, {}, json.dumps({"error": "invalid_grant"}).encode()
            return 200, {}, json.dumps({"access_token": "at", "refresh_token": "rt"}).encode()
        if url.endswith("/creator_info/query/"):
            return 200, {}, json.dumps({**OK, "data": {"creator_username": "me",
                                                       "privacy_level_options": ["SELF_ONLY"]}}).encode()
        if url.endswith("/video/init/"):
            self.inits.append(url)
            if self.init_error:
                return 403, {}, json.dumps({"error": {"code": self.init_error, "message": "no"}}).encode()
            return 200, {}, json.dumps({**OK, "data": {"publish_id": "p1", "upload_url": "https://up/1"}}).encode()
        if url.endswith("/status/fetch/"):
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return 200, {}, json.dumps({**OK, "data": {"status": status, "fail_reason": "bad"}}).encode()
        if method == "PUT":
            return 201, {}, b""
        raise AssertionError(url)


def client(http):
    return TikTokClient("k", "s", "r", http=http, sleep=lambda _: None)


def test_chunk_plan():
    assert chunk_plan(1000) == (1000, 1)
    assert chunk_plan(SINGLE_CHUNK_MAX) == (SINGLE_CHUNK_MAX, 1)
    size, count = chunk_plan(SINGLE_CHUNK_MAX + 1)
    assert count == (SINGLE_CHUNK_MAX + 1) // size and (SINGLE_CHUNK_MAX + 1) - size * (count - 1) < 2 * size


def test_upload_sends_init_then_one_chunk():
    http = FakeHttp()
    assert client(http).upload(b"x" * 10, "caption #gta6", "SELF_ONLY") == "p1"
    init = json.loads(http.calls[1][3])
    assert init["post_info"]["privacy_level"] == "SELF_ONLY"
    assert init["source_info"] == {"source": "FILE_UPLOAD", "video_size": 10, "chunk_size": 10, "total_chunk_count": 1}
    method, url, headers, body = http.calls[2]
    assert method == "PUT" and headers["Content-Range"] == "bytes 0-9/10" and body == b"x" * 10


def test_token_and_quota_errors_are_mapped():
    with pytest.raises(TokenInvalid):
        client(FakeHttp(token_status=400)).access_token()
    with pytest.raises(QuotaExceeded):
        client(FakeHttp(init_error="spam_risk_too_many_posts")).upload(b"x", "c", "SELF_ONLY")


def test_wait_reports_failure_and_timeout():
    with pytest.raises(ApiError, match="bad"):
        client(FakeHttp(statuses=["PROCESSING_UPLOAD", "FAILED"])).wait("p1", 1, 10)
    with pytest.raises(ApiError) as exc:
        client(FakeHttp(statuses=["PROCESSING_UPLOAD"])).wait("p1", 1, 2)
    assert exc.value.code == "TIMEOUT"


class FakeYouTube:
    key, name, token_hint = "youtube", "YouTube", "regenerate it"
    token_invalid, quota, api_error = YtTokenInvalid, YtQuota, YtError

    def check(self):
        pass

    def post(self, entry):
        return "yt1", "https://www.youtube.com/shorts/yt1"


def post_then_draft(tmp_path, http, mode="draft", privacy="SELF_ONLY", **kwargs):
    deleted, commits, logs, notes = [], [], [], []
    post_next(tmp_path, None, CFG, deleted.append, commit=commits.append, now=NOW, log=logs.append,
              youtube=FakeYouTube(), tiktok_later=True)
    poster = TikTokPoster(client(http), privacy, 0, 1, fetch=lambda entry: b"video", mode=mode)
    code = tiktok_drafts(tmp_path, CFG, poster, deleted.append, commit=commits.append, log=logs.append,
                         summary=notes.append, **kwargs)
    return code, deleted, commits, notes


def test_youtube_keeps_the_asset_until_the_tiktok_draft_is_sent(tmp_path):
    setup(tmp_path, tiktok_caption="Mandy is NOT okay #GTA6")
    http = FakeHttp(statuses=["SEND_TO_USER_INBOX"])
    deleted, commits, logs = [], [], []
    post_next(tmp_path, None, CFG, deleted.append, commit=commits.append, now=NOW, log=logs.append,
              youtube=FakeYouTube(), tiktok_later=True)
    posted = queue.load_all(tmp_path, "posted")[0]
    assert deleted == [] and posted["tiktok"]["video_id"] is None
    code, deleted, commits, notes = post_then_draft(tmp_path, http)
    posted = queue.load_all(tmp_path, "posted")[0]
    assert code == 0 and deleted == [7] and posted["tiktok"]["video_id"] == "p1"
    assert http.inits[0].endswith("/inbox/video/init/") and "Mandy is NOT okay #GTA6" in notes[0]
    assert "queue: tiktok published vid_clip_01" in commits


def test_draft_limit_stops_and_keeps_the_asset(tmp_path):
    setup(tmp_path)
    code, deleted, _, notes = post_then_draft(tmp_path, FakeHttp(init_error="spam_risk_too_many_pending_share"))
    posted = queue.load_all(tmp_path, "posted")[0]
    assert code == 0 and deleted == [] and notes == [] and posted["tiktok"]["attempts"] == 0


def test_tiktok_off_deletes_the_asset_right_away(tmp_path):
    setup(tmp_path)
    deleted = []
    post_next(tmp_path, None, CFG, deleted.append, now=NOW, log=lambda m: None, youtube=FakeYouTube())
    assert deleted == [7] and "tiktok" not in queue.load_all(tmp_path, "posted")[0]


def test_ids_backfill_unmarked_posted_clips(tmp_path):
    setup(tmp_path)
    post_next(tmp_path, None, CFG, lambda _: None, now=NOW, log=lambda m: None, youtube=FakeYouTube())
    poster = TikTokPoster(client(FakeHttp(statuses=["SEND_TO_USER_INBOX"])), "SELF_ONLY", 0, 1,
                          fetch=lambda entry: b"video", mode="draft")
    assert tiktok_drafts(tmp_path, CFG, poster, lambda _: None, log=lambda m: None) == 0
    assert "tiktok" not in queue.load_all(tmp_path, "posted")[0]
    tiktok_drafts(tmp_path, CFG, poster, lambda _: None, log=lambda m: None, summary=lambda m: None,
                  ids=["vid_clip_01"])
    assert queue.load_all(tmp_path, "posted")[0]["tiktok"]["video_id"] == "p1"


def test_direct_mode_disallowed_privacy_counts_an_attempt(tmp_path):
    setup(tmp_path)
    http = FakeHttp()
    code, deleted, _, _ = post_then_draft(tmp_path, http, mode="direct", privacy="PUBLIC_TO_EVERYONE")
    assert code == 1 and deleted == [] and http.inits == []
    assert queue.load_all(tmp_path, "posted")[0]["tiktok"]["attempts"] == 1


def test_dry_run_checks_credentials_only(tmp_path):
    setup(tmp_path)
    http = FakeHttp()
    code, deleted, commits, _ = post_then_draft(tmp_path, http, dry_run=True)
    assert code == 0 and deleted == [] and http.inits == []
    assert [c for c in commits if "tiktok" in c] == []
