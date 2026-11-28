import json

import pytest

from clipper.publish import queue
from clipper.publish.post_next import PublerPoster, post_next
from clipper.publish.publer import ApiError, PublerClient, QuotaExceeded, TokenInvalid
from tests.test_publish_post_next import CFG, NOW, setup

ACCOUNTS = [{"id": "ig1", "provider": "instagram", "name": "me"}, {"id": "fb1", "provider": "facebook"},
            {"id": "yt1", "provider": "youtube"}]


class FakeHttp:
    def __init__(self, jobs=({"status": "complete", "payload": {"failures": {}}},), post_status=200):
        self.calls, self.jobs, self.post_status = [], list(jobs), post_status
        self.posts = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if url.endswith("/accounts"):
            return 200, {}, json.dumps(ACCOUNTS).encode()
        if url.endswith("/media"):
            return 200, {}, json.dumps({"id": "m1", "type": "video"}).encode()
        if "/posts/schedule" in url:
            self.posts.append((url, json.loads(body)))
            return self.post_status, {}, json.dumps({"job_id": "j1"} if self.post_status == 200 else
                                                    {"error": "nope"}).encode()
        if "/job_status/" in url:
            job = self.jobs.pop(0) if len(self.jobs) > 1 else self.jobs[0]
            return 200, {}, json.dumps({"success": True, "data": job}).encode()
        raise AssertionError(url)


def poster(http, accounts=("ig1", "yt1"), **kw):
    client = PublerClient("key", "ws", http=http, sleep=lambda _: None)
    return PublerPoster(client, list(accounts), fetch=lambda e: b"video", **kw)


def entry():
    return {"id": "v_clip_01", "caption": "caption #gta6", "title": "Title", "youtube_description": "desc",
            "publer": queue.new_platform_state()}


def test_headers_use_bearer_api_and_workspace():
    http = FakeHttp()
    PublerClient("key", "ws", http=http).accounts()
    headers = http.calls[0][2]
    assert headers["Authorization"] == "Bearer-API key" and headers["Publer-Workspace-Id"] == "ws"


def test_post_uploads_once_and_groups_accounts_by_network():
    http = FakeHttp()
    e = entry()
    assert poster(http).post(e) == ("j1", None)
    upload = [c for c in http.calls if c[1].endswith("/media")]
    assert len(upload) == 1 and b'filename="v_clip_01.mp4"' in upload[0][3]
    url, body = http.posts[0]
    assert url.endswith("/posts/schedule/publish") and body["bulk"]["state"] == "scheduled"
    nets = {next(iter(p["networks"])): p for p in body["bulk"]["posts"]}
    assert nets["instagram"]["networks"]["instagram"]["type"] == "reel"
    assert nets["instagram"]["accounts"] == [{"id": "ig1"}]
    yt = nets["youtube"]["networks"]["youtube"]
    assert yt["type"] == "short" and yt["title"] == "Title" and yt["text"] == "desc"
    assert yt["media"] == [{"id": "m1", "type": "video"}]
    assert e["publer"]["done"] == ["ig1", "yt1"]


def test_draft_mode_uses_schedule_endpoint():
    http = FakeHttp()
    poster(http, draft=True).post(entry())
    url, body = http.posts[0]
    assert url.endswith("/posts/schedule") and body["bulk"]["state"] == "draft"


def test_partial_failure_keeps_successes_and_retries_only_failed():
    http = FakeHttp(jobs=[{"status": "complete", "payload": {"failures": {"yt1": "quota"}}},
                          {"status": "complete", "payload": {"failures": {}}}])
    p, e = poster(http), entry()
    with pytest.raises(ApiError, match="yt1"):
        p.post(e)
    assert e["publer"]["done"] == ["ig1"]
    p.post(e)
    assert [a["id"] for post in http.posts[1][1]["bulk"]["posts"] for a in post["accounts"]] == ["yt1"]
    assert e["publer"]["done"] == ["ig1", "yt1"]


def test_unattributed_failure_fails_every_account():
    http = FakeHttp(jobs=[{"status": "complete", "payload": {"failures": {"error": "boom"}}}])
    e = entry()
    with pytest.raises(ApiError):
        poster(http).post(e)
    assert e["publer"]["done"] == []


def test_job_polls_until_complete_and_failed_job_raises():
    http = FakeHttp(jobs=[{"status": "working"}, {"status": "complete", "payload": {}}])
    poster(http).post(entry())
    assert sum("/job_status/" in c[1] for c in http.calls) == 2
    with pytest.raises(ApiError, match="job failed"):
        poster(FakeHttp(jobs=[{"status": "failed", "payload": {"error": "x"}}])).post(entry())


def test_error_mapping():
    with pytest.raises(TokenInvalid):
        poster(FakeHttp(post_status=401)).post(entry())
    with pytest.raises(QuotaExceeded):
        poster(FakeHttp(post_status=429)).post(entry())


def test_unknown_account_fails_check():
    with pytest.raises(ApiError, match="nope1"):
        poster(FakeHttp(), accounts=("ig1", "nope1")).check()


def test_post_next_posts_through_publer_and_finalizes(tmp_path):
    setup(tmp_path)
    deleted, commits = [], []
    code = post_next(tmp_path, None, CFG, deleted.append, commit=commits.append, now=NOW, log=lambda _: None,
                     publer=poster(FakeHttp()))
    assert code == 0
    posted = queue.load_all(tmp_path, "posted")
    assert len(posted) == 1 and posted[0]["publer"]["done"] == ["ig1", "yt1"]
    assert deleted == [7] and commits[-1] == "queue: posted vid_clip_01"
