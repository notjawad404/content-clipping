# Instagram Auto-Posting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After clips are rendered locally, `clipper queue` publishes them to a queue and a GitHub Actions workflow posts one queued clip at a time to Instagram as a Reel.

**Architecture:** A new `clipper/publish/` package of small modules (file queue, Graph API client, `gh`-based release-asset storage, orchestrator, local enqueue). The posting path imports only the standard library plus pyyaml so it runs on a bare GitHub runner (no `uv sync`: the project's ML dependencies are macOS-only). Clips are uploaded as Release assets in a separate public repo; Instagram fetches them by URL.

**Tech Stack:** Python 3.12, stdlib `urllib`/`subprocess`/`json`, pyyaml, pytest, `gh` CLI, GitHub Actions.

Spec: `docs/superpowers/specs/2026-11-07-instagram-posting-design.md`

## Global Constraints

- Python is 3.12 (`requires-python = ">=3.12,<3.13"`). Run tests with `uv run pytest`.
- `clipper/publish/` may import only the standard library, `yaml` (pyyaml) and other `clipper` modules that are light to import (`clipper.env`). It must NOT import `clipper.cli`, `clipper.fetch`, `clipper.transcribe`, `clipper.reframe` or anything pulling opencv/mediapipe/parakeet.
- Graph API host is `https://graph.facebook.com`, version `v26.0`. Instagram account ID is `17841438716134897` (not a secret, lives in `config/publish.yaml`).
- Queue directories are `queue/pending/`, `queue/posted/`, `queue/failed/`, one JSON file per clip named `<video_id>_<clip_id>.json`. Order is oldest `queued_at` first, ties broken by id.
- `max_attempts` is 3, `poll_interval_s` is 10, `poll_timeout_s` is 300.
- Secrets are `IG_ACCESS_TOKEN` and `CLIPS_REPO_TOKEN` only. Never print, log or put a token in an exception message. Log at most the first 40 characters of a caption.
- A failed publish step increments `attempts`. `TokenInvalid` and quota errors do NOT increment `attempts`.
- The clips repo is `hammadalive7/content-clips` (public); the main repo is `hammadalive7/content-clipping` (private). One release per video, tag `v-<video_id>`.
- Default cron (added only in the last task) is `0 9,13,19 * * *` (UTC), one clip per run.
- End every commit message with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (pass it as a second `-m`).
- Do not stage the untracked `config/campaigns/gta6-t2-ceo.yaml`, `health.yaml` or `iced-coffee-hour-greg-lav.yaml`. Always `git add` explicit paths.

## File Structure

| File | Responsibility |
|---|---|
| `clipper/publish/__init__.py` | `PublishError` base class only |
| `clipper/publish/queue.py` | Queue files and state moves; no network |
| `clipper/publish/instagram.py` | Graph API client, typed errors, default HTTP function |
| `clipper/publish/clips_repo.py` | Upload/delete Release assets via `gh` |
| `clipper/publish/config.py` | Load and validate `config/publish.yaml` |
| `clipper/publish/gitops.py` | Commit and push `queue/` changes safely |
| `clipper/publish/post_next.py` | Orchestrator and `python -m` entry point used by the workflow |
| `clipper/publish/enqueue.py` | Local: upload a job's clips and write queue entries |
| `clipper/cli.py` | New `queue` and `post-next` subcommands |
| `config/publish.yaml` | Posting settings |
| `.github/workflows/post-next.yml` | The posting workflow |
| `tests/test_publish_*.py`, `tests/test_workflows.py` | Tests |

Deviations from the spec, chosen deliberately: no `queue/.gitkeep` files (directories are created on demand and git does not track empty directories); the workflow runs `python -m clipper.publish.post_next` instead of `uv run clipper post-next` (the full CLI imports heavy modules); HTTP uses `urllib` instead of adding a dependency; the cron schedule is added last, after a verified manual post.

---

### Task 1: Queue storage

**Files:**
- Create: `clipper/publish/__init__.py`
- Create: `clipper/publish/queue.py`
- Test: `tests/test_publish_queue.py`

**Interfaces:**
- Produces: `PublishError(Exception)`; in `queue.py`: `STATES = ("pending", "posted", "failed")`, `QUEUE_ROOT: Path`, `QueueError(PublishError)`, `new_entry(*, video_id, clip_id, campaign, caption, asset_url, asset_id, queued_at) -> dict`, `path_for(root, state, entry_id) -> Path`, `save(root, state, entry) -> None`, `load_all(root, state) -> list[dict]`, `exists_anywhere(root, entry_id) -> bool`, `next_pending(root) -> dict | None`, `move(root, entry, from_state, to_state) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_publish_queue.py`:

```python
import pytest

from clipper.publish import queue
from clipper.publish.queue import QueueError


def entry(video="vid", clip="clip_01", queued_at="2026-11-07T10:00:00Z"):
    return queue.new_entry(video_id=video, clip_id=clip, campaign="health", caption="cap",
                           asset_url="https://example.invalid/a.mp4", asset_id=7, queued_at=queued_at)


def test_new_entry_defaults():
    e = entry()
    assert e["id"] == "vid_clip_01"
    assert e["attempts"] == 0
    assert e["container_id"] is None and e["media_id"] is None
    assert e["permalink"] is None and e["last_error"] is None


def test_save_and_load_roundtrip(tmp_path):
    queue.save(tmp_path, "pending", entry())
    assert queue.load_all(tmp_path, "pending") == [entry()]
    assert (tmp_path / "pending" / "vid_clip_01.json").exists()


def test_load_all_missing_dir_is_empty(tmp_path):
    assert queue.load_all(tmp_path, "posted") == []


def test_next_pending_is_oldest_first_then_by_id(tmp_path):
    queue.save(tmp_path, "pending", entry(clip="clip_02", queued_at="2026-11-07T10:00:00Z"))
    queue.save(tmp_path, "pending", entry(clip="clip_01", queued_at="2026-11-07T10:00:00Z"))
    queue.save(tmp_path, "pending", entry(clip="clip_03", queued_at="2026-11-07T09:00:00Z"))
    assert queue.next_pending(tmp_path)["id"] == "vid_clip_03"
    queue.move(tmp_path, queue.next_pending(tmp_path), "pending", "posted")
    assert queue.next_pending(tmp_path)["id"] == "vid_clip_01"


def test_next_pending_empty(tmp_path):
    assert queue.next_pending(tmp_path) is None


def test_move_removes_the_source_file(tmp_path):
    e = entry()
    queue.save(tmp_path, "pending", e)
    queue.move(tmp_path, e, "pending", "failed")
    assert not (tmp_path / "pending" / "vid_clip_01.json").exists()
    assert queue.load_all(tmp_path, "failed") == [e]


def test_exists_anywhere(tmp_path):
    assert not queue.exists_anywhere(tmp_path, "vid_clip_01")
    queue.save(tmp_path, "posted", entry())
    assert queue.exists_anywhere(tmp_path, "vid_clip_01")


def test_unknown_state_is_rejected(tmp_path):
    with pytest.raises(QueueError):
        queue.save(tmp_path, "done", entry())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish_queue.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'clipper.publish'`

- [ ] **Step 3: Write minimal implementation**

Create `clipper/publish/__init__.py`:

```python
class PublishError(Exception):
    """Base class for posting errors that should print as a one-line message."""
```

Create `clipper/publish/queue.py`:

```python
"""File-based clip queue: one JSON file per clip in queue/{pending,posted,failed}/."""
from __future__ import annotations

import json
from pathlib import Path

from clipper.env import PROJECT_ROOT
from clipper.publish import PublishError

STATES = ("pending", "posted", "failed")
QUEUE_ROOT = PROJECT_ROOT / "queue"


class QueueError(PublishError):
    pass


def new_entry(*, video_id: str, clip_id: str, campaign: str | None, caption: str, asset_url: str,
              asset_id: int, queued_at: str) -> dict:
    return {"id": f"{video_id}_{clip_id}", "video_id": video_id, "campaign": campaign, "caption": caption,
            "asset_url": asset_url, "asset_id": asset_id, "queued_at": queued_at, "attempts": 0,
            "last_error": None, "container_id": None, "media_id": None, "permalink": None}


def _dir(root: Path, state: str) -> Path:
    if state not in STATES:
        raise QueueError(f"unknown queue state {state!r}; expected one of {STATES}")
    return root / state


def path_for(root: Path, state: str, entry_id: str) -> Path:
    return _dir(root, state) / f"{entry_id}.json"


def save(root: Path, state: str, entry: dict) -> None:
    directory = _dir(root, state)
    directory.mkdir(parents=True, exist_ok=True)
    path_for(root, state, entry["id"]).write_text(json.dumps(entry, indent=2) + "\n")


def load_all(root: Path, state: str) -> list[dict]:
    directory = _dir(root, state)
    if not directory.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(directory.glob("*.json"))]


def exists_anywhere(root: Path, entry_id: str) -> bool:
    return any(path_for(root, state, entry_id).exists() for state in STATES)


def next_pending(root: Path) -> dict | None:
    return min(load_all(root, "pending"), key=lambda e: (e["queued_at"], e["id"]), default=None)


def move(root: Path, entry: dict, from_state: str, to_state: str) -> None:
    save(root, to_state, entry)
    source = path_for(root, from_state, entry["id"])
    if source.exists():
        source.unlink()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publish_queue.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add clipper/publish/__init__.py clipper/publish/queue.py tests/test_publish_queue.py
git commit -m "feat: file-based Instagram posting queue" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Instagram Graph API client

**Files:**
- Create: `clipper/publish/instagram.py`
- Test: `tests/test_publish_instagram.py`

**Interfaces:**
- Consumes: `clipper.publish.PublishError`.
- Produces: exceptions `IgError(PublishError)`, `QuotaExceeded(IgError)`, `TokenInvalid(IgError)`, `ProcessingFailed(IgError)`, `ApiError(IgError)` with `.code` and `.subcode`; `HttpFailure(Exception)` with `.status` and `.payload`; `urllib_http(method, url, params) -> dict`; class `InstagramClient(token, account_id, version="v26.0", http=urllib_http, sleep=time.sleep, clock=time.monotonic)` with methods `publishing_limit() -> tuple[int, int]` (used, total), `create_reel_container(video_url, caption) -> str`, `container_status(container_id) -> str`, `wait_until_finished(container_id, interval, timeout) -> None`, `publish(container_id) -> str` (media id), `permalink(media_id) -> str | None`, `recent_media(limit=5) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_publish_instagram.py`:

```python
import io
import urllib.error
import urllib.request

import pytest

from clipper.publish.instagram import (ApiError, HttpFailure, InstagramClient, ProcessingFailed, QuotaExceeded,
                                       TokenInvalid, urllib_http)

TOKEN = "SECRET-TOKEN"


class FakeHttp:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, params):
        self.calls.append((method, url, params))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def client(http, clock=None):
    clock = clock or Clock()
    return InstagramClient(TOKEN, "1784", "v26.0", http=http, sleep=clock.sleep, clock=clock)


def graph_error(status, code, subcode=None, message="boom"):
    return HttpFailure(status, {"error": {"message": message, "type": "OAuthException", "code": code,
                                          "error_subcode": subcode}})


def test_create_reel_container_request():
    http = FakeHttp({"id": "999"})
    assert client(http).create_reel_container("https://x/a.mp4", "hello #tag") == "999"
    method, url, params = http.calls[0]
    assert method == "POST" and url == "https://graph.facebook.com/v26.0/1784/media"
    assert params == {"media_type": "REELS", "video_url": "https://x/a.mp4", "caption": "hello #tag",
                      "share_to_feed": "true", "access_token": TOKEN}


def test_response_without_id_is_an_api_error():
    with pytest.raises(ApiError):
        client(FakeHttp({})).create_reel_container("https://x/a.mp4", "c")


def test_publish_returns_media_id():
    http = FakeHttp({"id": "555"})
    assert client(http).publish("999") == "555"
    method, url, params = http.calls[0]
    assert method == "POST" and url.endswith("/1784/media_publish") and params["creation_id"] == "999"


def test_token_errors_map_to_token_invalid():
    with pytest.raises(TokenInvalid):
        client(FakeHttp(graph_error(400, 190))).publish("999")


def test_quota_error_maps_to_quota_exceeded():
    with pytest.raises(QuotaExceeded):
        client(FakeHttp(graph_error(400, 9, 2207042))).publish("999")


def test_other_errors_keep_code_and_message_but_never_the_token():
    with pytest.raises(ApiError) as caught:
        client(FakeHttp(graph_error(400, 100, None, "bad parameter"))).publish("999")
    assert caught.value.code == 100
    assert "bad parameter" in str(caught.value) and TOKEN not in str(caught.value)


def test_publishing_limit_parses_usage_and_total():
    http = FakeHttp({"data": [{"quota_usage": 3, "config": {"quota_total": 100, "quota_duration": 86400}}]})
    assert client(http).publishing_limit() == (3, 100)
    assert http.calls[0][2]["fields"] == "quota_usage,config"


def test_publishing_limit_unexpected_shape():
    with pytest.raises(ApiError):
        client(FakeHttp({"data": []})).publishing_limit()


def test_wait_until_finished_polls_until_finished():
    http = FakeHttp({"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"})
    client(http).wait_until_finished("999", 10, 300)
    assert len(http.calls) == 2


def test_wait_until_finished_raises_on_error_status():
    with pytest.raises(ProcessingFailed):
        client(FakeHttp({"status_code": "ERROR"})).wait_until_finished("999", 10, 300)


def test_wait_until_finished_times_out():
    http = FakeHttp(*[{"status_code": "IN_PROGRESS"}] * 10)
    with pytest.raises(ProcessingFailed, match="timed out"):
        client(http).wait_until_finished("999", 10, 25)


def test_permalink_and_recent_media():
    http = FakeHttp({"permalink": "https://instagram.com/reel/abc/"},
                    {"data": [{"id": "1", "caption": "c", "timestamp": "2026-11-07T10:00:00+0000"}]})
    c = client(http)
    assert c.permalink("555") == "https://instagram.com/reel/abc/"
    assert c.recent_media(5)[0]["id"] == "1"
    assert http.calls[1][2]["limit"] == 5


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_urllib_http_get_puts_params_in_the_query(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"], seen["method"] = req.full_url, req.get_method()
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert urllib_http("GET", "https://x/y", {"a": "1"}) == {"ok": True}
    assert seen == {"url": "https://x/y?a=1", "method": "GET"}


def test_urllib_http_post_sends_a_form_body(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["data"], seen["method"] = req.data, req.get_method()
        return FakeResponse(b'{"id": "1"}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert urllib_http("POST", "https://x/y", {"a": "1"}) == {"id": "1"}
    assert seen == {"data": b"a=1", "method": "POST"}


def test_urllib_http_maps_http_errors(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b'{"error": {"code": 190}}'))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(HttpFailure) as caught:
        urllib_http("GET", "https://x/y", {"a": "1"})
    assert caught.value.status == 400 and caught.value.payload["error"]["code"] == 190
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish_instagram.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'clipper.publish.instagram'`

- [ ] **Step 3: Write minimal implementation**

Create `clipper/publish/instagram.py`:

```python
"""Thin Instagram Graph API client (Instagram API with Unified Login). Knows nothing about GitHub or the queue."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from clipper.publish import PublishError

API_HOST = "https://graph.facebook.com"
QUOTA_SUBCODE = 2207042
TOKEN_ERROR_CODES = (102, 190)


class IgError(PublishError):
    pass


class QuotaExceeded(IgError):
    pass


class TokenInvalid(IgError):
    pass


class ProcessingFailed(IgError):
    pass


class ApiError(IgError):
    def __init__(self, message: str, code: int | None = None, subcode: int | None = None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode


class HttpFailure(Exception):
    def __init__(self, status: int, payload: dict):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.payload = payload


def urllib_http(method: str, url: str, params: dict) -> dict:
    """One Graph API request. Raises HttpFailure for HTTP errors and ApiError for network errors."""
    encoded = urllib.parse.urlencode(params)
    if method == "GET":
        request = urllib.request.Request(f"{url}?{encoded}", method="GET")
    else:
        request = urllib.request.Request(url, data=encoded.encode(), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode())
        except ValueError:
            payload = {}
        raise HttpFailure(exc.code, payload) from None
    except urllib.error.URLError as exc:
        raise ApiError(f"network error: {exc.reason}") from None


def _map_error(payload: dict, status: int) -> IgError:
    error = payload.get("error") or {}
    code, subcode = error.get("code"), error.get("error_subcode")
    message = error.get("message") or f"HTTP {status}"
    if code in TOKEN_ERROR_CODES:
        return TokenInvalid(message)
    if code == 9 and subcode == QUOTA_SUBCODE:
        return QuotaExceeded(message)
    return ApiError(message, code, subcode)


def _field(data: dict, key: str) -> str:
    try:
        return str(data[key])
    except (KeyError, TypeError):
        raise ApiError(f"response missing {key!r}") from None


class InstagramClient:
    def __init__(self, token: str, account_id: str, version: str = "v26.0",
                 http: Callable[[str, str, dict], dict] = urllib_http,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self._token = token
        self._account = account_id
        self._version = version
        self._http = http
        self._sleep = sleep
        self._clock = clock

    def _call(self, method: str, path: str, params: dict | None = None) -> dict:
        full = {**(params or {}), "access_token": self._token}
        try:
            return self._http(method, f"{API_HOST}/{self._version}/{path}", full)
        except HttpFailure as exc:
            raise _map_error(exc.payload, exc.status) from None

    def publishing_limit(self) -> tuple[int, int]:
        data = self._call("GET", f"{self._account}/content_publishing_limit", {"fields": "quota_usage,config"})
        try:
            row = data["data"][0]
            return int(row["quota_usage"]), int(row["config"]["quota_total"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise ApiError("unexpected content_publishing_limit response") from None

    def create_reel_container(self, video_url: str, caption: str) -> str:
        data = self._call("POST", f"{self._account}/media",
                          {"media_type": "REELS", "video_url": video_url, "caption": caption,
                           "share_to_feed": "true"})
        return _field(data, "id")

    def container_status(self, container_id: str) -> str:
        return _field(self._call("GET", container_id, {"fields": "status_code"}), "status_code")

    def wait_until_finished(self, container_id: str, interval: float, timeout: float) -> None:
        deadline = self._clock() + timeout
        while True:
            status = self.container_status(container_id)
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise ProcessingFailed(f"container {status}")
            if self._clock() >= deadline:
                raise ProcessingFailed(f"timed out after {timeout:g}s (last status {status})")
            self._sleep(interval)

    def publish(self, container_id: str) -> str:
        return _field(self._call("POST", f"{self._account}/media_publish", {"creation_id": container_id}), "id")

    def permalink(self, media_id: str) -> str | None:
        return self._call("GET", media_id, {"fields": "permalink"}).get("permalink")

    def recent_media(self, limit: int = 5) -> list[dict]:
        data = self._call("GET", f"{self._account}/media",
                          {"fields": "id,caption,timestamp,permalink", "limit": limit})
        return list(data.get("data", []))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publish_instagram.py -v`
Expected: PASS (16 passed)

- [ ] **Step 5: Commit**

```bash
git add clipper/publish/instagram.py tests/test_publish_instagram.py
git commit -m "feat: Instagram Graph API client for Reels publishing" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Release-asset storage via `gh`

**Files:**
- Create: `clipper/publish/clips_repo.py`
- Test: `tests/test_publish_clips_repo.py`

**Interfaces:**
- Consumes: `clipper.publish.PublishError`.
- Produces: `RepoError(PublishError)`; `default_run(args: list[str])` returning an object with `.returncode`, `.stdout`, `.stderr`; `ensure_release(repo, tag, run=default_run) -> None`; `upload_asset(repo, tag, path, run=default_run) -> tuple[str, int]` (download URL, asset id); `delete_asset(repo, asset_id, run=default_run) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_publish_clips_repo.py`:

```python
import json
from types import SimpleNamespace

import pytest

from clipper.publish import clips_repo
from clipper.publish.clips_repo import RepoError

ASSET = {"name": "clip_01.mp4", "id": 42,
         "browser_download_url": "https://github.com/o/r/releases/download/v-vid/clip_01.mp4"}


def proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def make_run(release_exists=True, assets=(ASSET,), fail_upload=False):
    calls = []

    def run(args):
        calls.append(args)
        if args[:3] == ["gh", "release", "view"]:
            return proc(0 if release_exists else 1)
        if args[:3] == ["gh", "release", "create"]:
            return proc(0)
        if args[:3] == ["gh", "release", "upload"]:
            return proc(1, "", "permission denied") if fail_upload else proc(0)
        if args[:2] == ["gh", "api"] and "-X" not in args:
            return proc(0, json.dumps({"assets": list(assets)}))
        if args[:2] == ["gh", "api"]:
            return proc(0)
        return proc(1, "", "unexpected command")

    return run, calls


def test_upload_returns_url_and_asset_id():
    run, calls = make_run()
    url, asset_id = clips_repo.upload_asset("o/r", "v-vid", "/tmp/clip_01.mp4", run)
    assert url == ASSET["browser_download_url"] and asset_id == 42
    assert ["gh", "release", "upload", "v-vid", "/tmp/clip_01.mp4", "-R", "o/r", "--clobber"] in calls


def test_upload_creates_the_release_when_missing():
    run, calls = make_run(release_exists=False)
    clips_repo.upload_asset("o/r", "v-vid", "/tmp/clip_01.mp4", run)
    assert any(c[:3] == ["gh", "release", "create"] and "v-vid" in c for c in calls)


def test_upload_failure_raises_with_gh_message():
    run, _ = make_run(fail_upload=True)
    with pytest.raises(RepoError, match="permission denied"):
        clips_repo.upload_asset("o/r", "v-vid", "/tmp/clip_01.mp4", run)


def test_upload_raises_when_asset_is_not_listed():
    run, _ = make_run(assets=())
    with pytest.raises(RepoError, match="not found"):
        clips_repo.upload_asset("o/r", "v-vid", "/tmp/clip_01.mp4", run)


def test_delete_asset_calls_the_delete_endpoint():
    run, calls = make_run()
    clips_repo.delete_asset("o/r", 42, run)
    assert calls == [["gh", "api", "-X", "DELETE", "repos/o/r/releases/assets/42"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish_clips_repo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'clipper.publish.clips_repo'`

- [ ] **Step 3: Write minimal implementation**

Create `clipper/publish/clips_repo.py`:

```python
"""Store rendered clips as Release assets in the public clips repo, using the `gh` CLI.

Locally `gh` uses your login; in GitHub Actions it uses the GH_TOKEN environment variable.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from clipper.publish import PublishError


class RepoError(PublishError):
    pass


def default_run(args: list[str]):
    return subprocess.run(args, capture_output=True, text=True)


def _check(proc, what: str) -> str:
    if proc.returncode != 0:
        raise RepoError(f"{what} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout


def ensure_release(repo: str, tag: str, run=default_run) -> None:
    if run(["gh", "release", "view", tag, "-R", repo]).returncode == 0:
        return
    _check(run(["gh", "release", "create", tag, "-R", repo, "--title", tag,
                "--notes", "Clips queued for Instagram posting"]), "create release")


def upload_asset(repo: str, tag: str, path: str | Path, run=default_run) -> tuple[str, int]:
    ensure_release(repo, tag, run)
    _check(run(["gh", "release", "upload", tag, str(path), "-R", repo, "--clobber"]), "upload asset")
    release = json.loads(_check(run(["gh", "api", f"repos/{repo}/releases/tags/{tag}"]), "read release"))
    name = Path(path).name
    for asset in release.get("assets", []):
        if asset["name"] == name:
            return asset["browser_download_url"], int(asset["id"])
    raise RepoError(f"uploaded asset {name} not found in release {tag}")


def delete_asset(repo: str, asset_id: int, run=default_run) -> None:
    _check(run(["gh", "api", "-X", "DELETE", f"repos/{repo}/releases/assets/{asset_id}"]), "delete asset")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publish_clips_repo.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add clipper/publish/clips_repo.py tests/test_publish_clips_repo.py
git commit -m "feat: upload and delete clip release assets via gh" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Publish config and git helper

**Files:**
- Create: `clipper/publish/config.py`
- Create: `clipper/publish/gitops.py`
- Create: `config/publish.yaml`
- Test: `tests/test_publish_config.py`
- Test: `tests/test_publish_gitops.py`

**Interfaces:**
- Consumes: `clipper.publish.PublishError`, `clipper.env.PROJECT_ROOT`.
- Produces: `PublishConfigError(PublishError)`; `load_publish_config(path=DEFAULT_PATH) -> dict` with keys `clips_repo`, `ig_account_id` (str), `graph_version`, `max_attempts`, `poll_interval_s`, `poll_timeout_s`; `GitError(PublishError)`; `commit_queue(message, *, cwd=PROJECT_ROOT, run=default_run) -> bool` (True if a commit was pushed, False if nothing changed).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_publish_config.py`:

```python
import pytest

from clipper.publish.config import PublishConfigError, load_publish_config


def write(tmp_path, text):
    path = tmp_path / "publish.yaml"
    path.write_text(text)
    return path


def test_defaults_are_applied(tmp_path):
    cfg = load_publish_config(write(tmp_path, 'clips_repo: me/clips\nig_account_id: "123"\n'))
    assert cfg == {"clips_repo": "me/clips", "ig_account_id": "123", "graph_version": "v26.0",
                   "max_attempts": 3, "poll_interval_s": 10, "poll_timeout_s": 300}


def test_account_id_written_as_a_number_becomes_a_string(tmp_path):
    cfg = load_publish_config(write(tmp_path, "clips_repo: me/clips\nig_account_id: 123\n"))
    assert cfg["ig_account_id"] == "123"


def test_missing_required_key_names_the_key(tmp_path):
    with pytest.raises(PublishConfigError, match="ig_account_id"):
        load_publish_config(write(tmp_path, "clips_repo: me/clips\n"))


def test_the_shipped_config_is_valid():
    cfg = load_publish_config()
    assert cfg["clips_repo"] == "hammadalive7/content-clips"
    assert cfg["ig_account_id"] == "17841438716134897"
```

Create `tests/test_publish_gitops.py`:

```python
from types import SimpleNamespace

import pytest

from clipper.publish.gitops import GitError, commit_queue


def make_run(staged=(), has_changes=True, push_codes=(0,), commit_code=0):
    calls = []
    pushes = list(push_codes)

    def run(args, cwd):
        calls.append(args[1:])
        verb = args[1:3]
        if verb == ["diff", "--cached"] and "--name-only" in args:
            return SimpleNamespace(returncode=0, stdout="\n".join(staged), stderr="")
        if verb == ["diff", "--cached"] and "--quiet" in args:
            return SimpleNamespace(returncode=1 if has_changes else 0, stdout="", stderr="")
        if args[1] == "commit":
            return SimpleNamespace(returncode=commit_code, stdout="", stderr="commit failed")
        if args[1] == "push":
            return SimpleNamespace(returncode=pushes.pop(0) if pushes else 0, stdout="", stderr="rejected")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return run, calls


def test_commits_and_pushes_queue_changes(tmp_path):
    run, calls = make_run()
    assert commit_queue("queue: add vid", cwd=tmp_path, run=run) is True
    assert ["add", "queue"] in calls
    assert ["commit", "-m", "queue: add vid"] in calls
    assert ["push"] in calls


def test_nothing_to_commit_returns_false(tmp_path):
    run, calls = make_run(has_changes=False)
    assert commit_queue("queue: nothing", cwd=tmp_path, run=run) is False
    assert not any(c[0] in ("commit", "push") for c in calls)


def test_refuses_when_unrelated_files_are_staged(tmp_path):
    run, calls = make_run(staged=("queue/pending/a.json", "README.md"))
    with pytest.raises(GitError, match="README.md"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run)
    assert not any(c[0] == "commit" for c in calls)


def test_push_rejection_pulls_with_rebase_and_retries(tmp_path):
    run, calls = make_run(push_codes=(1, 0))
    assert commit_queue("queue: add vid", cwd=tmp_path, run=run) is True
    assert ["pull", "--rebase"] in calls


def test_push_that_keeps_failing_raises(tmp_path):
    run, _ = make_run(push_codes=(1, 1))
    with pytest.raises(GitError, match="push"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_publish_config.py tests/test_publish_gitops.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'clipper.publish.config'`

- [ ] **Step 3: Write minimal implementation**

Create `config/publish.yaml`:

```yaml
# Instagram posting settings. None of these are secrets (the token is the IG_ACCESS_TOKEN Actions secret).
clips_repo: hammadalive7/content-clips      # public repo whose Release assets Instagram fetches
ig_account_id: "17841438716134897"          # vanguardvisionhub
graph_version: v26.0
max_attempts: 3
poll_interval_s: 10
poll_timeout_s: 300
```

Create `clipper/publish/config.py`:

```python
"""Load and validate config/publish.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

from clipper.env import CONFIG_DIR
from clipper.publish import PublishError

DEFAULT_PATH = CONFIG_DIR / "publish.yaml"
REQUIRED = ("clips_repo", "ig_account_id")
DEFAULTS = {"graph_version": "v26.0", "max_attempts": 3, "poll_interval_s": 10, "poll_timeout_s": 300}


class PublishConfigError(PublishError):
    pass


def load_publish_config(path: Path = DEFAULT_PATH) -> dict:
    if not Path(path).exists():
        raise PublishConfigError(f"missing posting config: {path}")
    raw = yaml.safe_load(Path(path).read_text()) or {}
    for key in REQUIRED:
        if not raw.get(key):
            raise PublishConfigError(f"{path.name}: missing required key {key!r}")
    cfg = {**DEFAULTS, **raw}
    cfg["ig_account_id"] = str(cfg["ig_account_id"])
    return cfg
```

Create `clipper/publish/gitops.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_publish_config.py tests/test_publish_gitops.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add clipper/publish/config.py clipper/publish/gitops.py config/publish.yaml tests/test_publish_config.py tests/test_publish_gitops.py
git commit -m "feat: posting config and safe queue commit helper" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `post-next` orchestrator

**Files:**
- Create: `clipper/publish/post_next.py`
- Test: `tests/test_publish_post_next.py`

**Interfaces:**
- Consumes: `queue.next_pending/save/move`, `queue.QUEUE_ROOT`; `InstagramClient` methods from Task 2 and exceptions `IgError`, `QuotaExceeded`, `TokenInvalid`; `clips_repo.delete_asset(repo, asset_id)`; `load_publish_config()`; `gitops.commit_queue(message)`; `PublishError`.
- Produces: `post_next(root, client, cfg, delete_asset, *, dry_run=False, commit=None, now=None, log=print) -> int` (exit code: 0 posted/nothing to do/quota wait, 1 failure); `main(argv=None) -> int` (reads `IG_ACCESS_TOKEN` from the environment; flag `--dry-run`); module is runnable with `python -m clipper.publish.post_next`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_publish_post_next.py`:

```python
from datetime import datetime, timezone

from clipper.publish import queue
from clipper.publish.clips_repo import RepoError
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish_post_next.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'clipper.publish.post_next'`

- [ ] **Step 3: Write minimal implementation**

Create `clipper/publish/post_next.py`:

```python
"""Post the oldest queued clip as an Instagram Reel. Runs in GitHub Actions: stdlib + pyyaml only."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from clipper.publish import PublishError, clips_repo, gitops, queue
from clipper.publish.config import load_publish_config
from clipper.publish.instagram import IgError, InstagramClient, QuotaExceeded, TokenInvalid

DUPLICATE_WINDOW = timedelta(hours=24)


def _short(caption: str) -> str:
    return caption[:40] + ("…" if len(caption) > 40 else "")


def _container_usable(client, container_id: str) -> bool:
    try:
        return client.container_status(container_id) in ("IN_PROGRESS", "FINISHED")
    except TokenInvalid:
        raise
    except IgError:
        return False


def _recent_duplicate(client, caption: str, now: datetime) -> dict | None:
    for item in client.recent_media(5):
        if item.get("caption") != caption:
            continue
        try:
            created = datetime.strptime(item["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        except (KeyError, TypeError, ValueError):
            continue
        if now - created <= DUPLICATE_WINDOW:
            return item
    return None


def _publish(root: Path, client, cfg: dict, entry: dict, dry_run: bool, commit: Callable[[str], object],
             now: datetime, log: Callable[[str], None]) -> bool:
    """Create/reuse the container and publish. Returns False for a dry run (nothing published)."""
    is_retry = bool(entry.get("container_id"))
    container = entry.get("container_id")
    if container and not _container_usable(client, container):
        container = None
    if not container:
        container = client.create_reel_container(entry["asset_url"], entry["caption"])
        if not dry_run:
            entry["container_id"] = container
            queue.save(root, "pending", entry)
            commit(f"queue: container for {entry['id']}")
    client.wait_until_finished(container, cfg["poll_interval_s"], cfg["poll_timeout_s"])
    if dry_run:
        log("dry run: container FINISHED; not publishing")
        return False
    duplicate = _recent_duplicate(client, entry["caption"], now) if is_retry else None
    if duplicate:
        log("found an identical recent post; recording it instead of publishing again")
        entry["media_id"] = str(duplicate["id"])
        entry["permalink"] = duplicate.get("permalink")
    else:
        entry["media_id"] = client.publish(container)
        try:
            entry["permalink"] = client.permalink(entry["media_id"])
        except IgError:
            entry["permalink"] = None
    queue.save(root, "pending", entry)
    commit(f"queue: published {entry['id']}")
    return True


def _finalize(root: Path, entry: dict, delete_asset: Callable[[int], object],
              commit: Callable[[str], object], log: Callable[[str], None]) -> None:
    queue.move(root, entry, "pending", "posted")
    if entry.get("asset_id") is not None:
        try:
            delete_asset(entry["asset_id"])
        except PublishError as exc:
            log(f"warning: could not delete the release asset: {exc}")
    commit(f"queue: posted {entry['id']}")
    log(f"posted {entry['id']}: {entry.get('permalink') or entry['media_id']}")


def _record_failure(root: Path, entry: dict, exc: Exception, cfg: dict, commit: Callable[[str], object],
                    log: Callable[[str], None], dry_run: bool) -> int:
    if dry_run:
        log(f"dry run failed: {exc}")
        return 1
    entry["attempts"] += 1
    entry["last_error"] = str(exc)
    state = "pending"
    if entry["attempts"] >= cfg["max_attempts"]:
        queue.move(root, entry, "pending", "failed")
        state = "failed"
    else:
        queue.save(root, "pending", entry)
    commit(f"queue: attempt {entry['attempts']} failed for {entry['id']}")
    log(f"error: {exc} (attempt {entry['attempts']}/{cfg['max_attempts']}; entry is now {state})")
    return 1


def post_next(root: Path, client, cfg: dict, delete_asset: Callable[[int], object], *, dry_run: bool = False,
              commit: Callable[[str], object] | None = None, now: datetime | None = None,
              log: Callable[[str], None] = print) -> int:
    commit = commit or (lambda message: None)
    now = now or datetime.now(timezone.utc)
    entry = queue.next_pending(root)
    if entry is None:
        log("nothing to post: the queue is empty")
        return 0
    log(f"next: {entry['id']} ({_short(entry['caption'])})")
    try:
        if entry.get("media_id"):
            if dry_run:
                log("dry run: entry is already published; nothing to check")
                return 0
            log("already published on an earlier run; finishing cleanup")
        else:
            used, total = client.publishing_limit()
            if used >= total:
                log(f"publishing quota reached ({used}/{total}); will retry on the next run")
                return 0
            if not _publish(root, client, cfg, entry, dry_run, commit, now, log):
                return 0
    except TokenInvalid:
        log("error: Instagram rejected the access token. Generate a new one and update the IG_ACCESS_TOKEN secret.")
        return 1
    except QuotaExceeded:
        log("publishing quota reached; will retry on the next run")
        return 0
    except IgError as exc:
        return _record_failure(root, entry, exc, cfg, commit, log, dry_run)
    _finalize(root, entry, delete_asset, commit, log)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="post-next", description="Post the oldest queued clip to Instagram")
    parser.add_argument("--dry-run", action="store_true", help="create and process the container, do not publish")
    args = parser.parse_args(argv)
    token = os.environ.get("IG_ACCESS_TOKEN")
    if not token:
        print("error: the IG_ACCESS_TOKEN environment variable is not set")
        return 2
    try:
        cfg = load_publish_config()
        client = InstagramClient(token, cfg["ig_account_id"], cfg["graph_version"])
        return post_next(queue.QUEUE_ROOT, client, cfg,
                         lambda asset_id: clips_repo.delete_asset(cfg["clips_repo"], asset_id),
                         dry_run=args.dry_run, commit=None if args.dry_run else gitops.commit_queue)
    except PublishError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publish_post_next.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Verify the module imports without the heavy dependencies**

Run: `uv run python -c "import sys; import clipper.publish.post_next; bad = [m for m in sys.modules if m.split('.')[0] in ('cv2', 'mediapipe', 'parakeet_mlx', 'mlx', 'yt_dlp', 'scenedetect', 'numpy')]; assert not bad, bad; print('light imports only')"`
Expected: `light imports only`

- [ ] **Step 6: Commit**

```bash
git add clipper/publish/post_next.py tests/test_publish_post_next.py
git commit -m "feat: post-next orchestrator with retries and duplicate guard" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Local `queue` command and CLI wiring

**Files:**
- Create: `clipper/publish/enqueue.py`
- Modify: `clipper/cli.py` (imports near line 12-17, new handlers after `cmd_finish`, parser in `build_parser`, `HANDLERS`, and the `except` tuple in `main`)
- Test: `tests/test_publish_enqueue.py`
- Modify: `tests/test_cli.py` (append two tests)

**Interfaces:**
- Consumes: `queue.exists_anywhere/new_entry/save`; `clips_repo.upload_asset(repo, tag, path)`, `RepoError`; `Job` attributes `video_id`, `out`, `job_file`, `clips_resolved`, `read_json`; `load_publish_config`; `gitops.commit_queue`; `post_next.main`.
- Produces: `enqueue_job(job, root, repo, *, upload=clips_repo.upload_asset, now=None, only=None) -> list[tuple[str, str, str]]` (rows of clip id, title, status where status is `queued`, `skipped: already queued`, `skipped: no rendered mp4`, or `failed: <message>`); CLI commands `clipper queue <video_id> [--only clip_01 ...]` and `clipper post-next [--dry-run]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_publish_enqueue.py`:

```python
from datetime import datetime, timezone

from clipper.jobs import job_for
from clipper.publish import queue
from clipper.publish.clips_repo import RepoError
from clipper.publish.enqueue import enqueue_job

NOW = datetime(2026, 11, 7, 21, 30, tzinfo=timezone.utc)


def clip(cid):
    return {"id": cid, "title": f"title {cid}", "post": {"instagram": f"caption {cid} #tag", "tiktok": "x"}}


def make_job(tmp_path, clip_ids, rendered):
    job = job_for("vid", jobs_dir=tmp_path / "jobs", output_dir=tmp_path / "out")
    job.ensure_dirs()
    job.write_json(job.job_file, {"url": "https://www.youtube.com/watch?v=vid", "campaign": "health"})
    job.write_json(job.clips_resolved, {"video_id": "vid", "clips": [clip(c) for c in clip_ids], "rejected": []})
    for cid in rendered:
        (job.out / f"{cid}.mp4").write_bytes(b"x")
    return job


class Uploader:
    def __init__(self):
        self.calls = []

    def __call__(self, repo, tag, path):
        self.calls.append((repo, tag, path.name))
        return f"https://github.com/{repo}/releases/download/{tag}/{path.name}", len(self.calls)


def test_queues_rendered_clips_with_the_instagram_caption(tmp_path):
    job = make_job(tmp_path, ["clip_01", "clip_02"], ["clip_01", "clip_02"])
    root, upload = tmp_path / "queue", Uploader()
    rows = enqueue_job(job, root, "o/clips", upload=upload, now=NOW)
    assert rows == [("clip_01", "title clip_01", "queued"), ("clip_02", "title clip_02", "queued")]
    assert upload.calls == [("o/clips", "v-vid", "clip_01.mp4"), ("o/clips", "v-vid", "clip_02.mp4")]
    entry = queue.load_all(root, "pending")[0]
    assert entry["id"] == "vid_clip_01" and entry["campaign"] == "health"
    assert entry["caption"] == "caption clip_01 #tag" and entry["queued_at"] == "2026-11-07T21:30:00Z"
    assert entry["asset_url"].endswith("/v-vid/clip_01.mp4") and entry["asset_id"] == 1


def test_skips_clips_without_a_rendered_mp4(tmp_path):
    job = make_job(tmp_path, ["clip_01", "clip_02"], ["clip_01"])
    rows = enqueue_job(job, tmp_path / "queue", "o/clips", upload=Uploader(), now=NOW)
    assert rows[1] == ("clip_02", "title clip_02", "skipped: no rendered mp4")


def test_skips_clips_already_in_any_queue_state(tmp_path):
    job = make_job(tmp_path, ["clip_01"], ["clip_01"])
    root, upload = tmp_path / "queue", Uploader()
    enqueue_job(job, root, "o/clips", upload=upload, now=NOW)
    rows = enqueue_job(job, root, "o/clips", upload=upload, now=NOW)
    assert rows == [("clip_01", "title clip_01", "skipped: already queued")]
    assert len(upload.calls) == 1


def test_only_filters_clips(tmp_path):
    job = make_job(tmp_path, ["clip_01", "clip_02"], ["clip_01", "clip_02"])
    rows = enqueue_job(job, tmp_path / "queue", "o/clips", upload=Uploader(), now=NOW, only=["clip_02"])
    assert [r[0] for r in rows] == ["clip_02"]


def test_an_upload_failure_is_isolated_to_its_clip(tmp_path):
    job = make_job(tmp_path, ["clip_01", "clip_02"], ["clip_01", "clip_02"])
    root = tmp_path / "queue"

    def flaky(repo, tag, path):
        if path.name == "clip_01.mp4":
            raise RepoError("upload asset failed: denied")
        return "https://example.invalid/clip_02.mp4", 5

    rows = enqueue_job(job, root, "o/clips", upload=flaky, now=NOW)
    assert rows[0][2].startswith("failed:") and rows[1][2] == "queued"
    assert [e["id"] for e in queue.load_all(root, "pending")] == ["vid_clip_02"]
```

Append to `tests/test_cli.py`:

```python
def test_parser_queue_and_post_next():
    args = build_parser().parse_args(["queue", "abc", "--only", "clip_01"])
    assert args.video_id == "abc" and args.only == ["clip_01"]
    assert build_parser().parse_args(["post-next", "--dry-run"]).dry_run


def test_queue_command_commits_only_when_something_was_queued(monkeypatch, capsys):
    commits = []
    monkeypatch.setattr(cli, "load_publish_config", lambda: {"clips_repo": "o/clips"})
    monkeypatch.setattr(cli, "commit_queue", lambda message: commits.append(message))
    monkeypatch.setattr(cli, "enqueue_job", lambda job, root, repo, only=None: [("clip_01", "T", "queued")])
    assert cli.main(["queue", "vid"]) == 0
    assert commits == ["queue: add vid"]
    monkeypatch.setattr(cli, "enqueue_job", lambda job, root, repo, only=None: [("clip_01", "T", "skipped: already queued")])
    assert cli.main(["queue", "vid"]) == 0
    assert commits == ["queue: add vid"]
    assert "clip_01" in capsys.readouterr().out


def test_post_next_command_delegates_to_the_module(monkeypatch):
    seen = []
    monkeypatch.setattr(cli.post_next_mod, "main", lambda argv: seen.append(argv) or 0)
    assert cli.main(["post-next", "--dry-run"]) == 0 and cli.main(["post-next"]) == 0
    assert seen == [["--dry-run"], []]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_publish_enqueue.py tests/test_cli.py -v`
Expected: FAIL (`No module named 'clipper.publish.enqueue'`, and the new cli tests fail on missing attributes)

- [ ] **Step 3: Write minimal implementation**

Create `clipper/publish/enqueue.py`:

```python
"""Local step: upload a job's rendered clips and write queue entries for the posting workflow."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from clipper.jobs import Job
from clipper.publish import clips_repo, queue
from clipper.publish.clips_repo import RepoError


def enqueue_job(job: Job, root: Path, repo: str, *, upload=clips_repo.upload_asset, now: datetime | None = None,
                only: list[str] | None = None) -> list[tuple[str, str, str]]:
    resolved = job.read_json(job.clips_resolved)
    campaign = job.read_json(job.job_file).get("campaign")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[tuple[str, str, str]] = []
    for clip in resolved["clips"]:
        cid, title = clip["id"], clip["title"]
        if only and cid not in only:
            continue
        video = job.out / f"{cid}.mp4"
        if queue.exists_anywhere(root, f"{job.video_id}_{cid}"):
            rows.append((cid, title, "skipped: already queued"))
        elif not video.exists():
            rows.append((cid, title, "skipped: no rendered mp4"))
        else:
            try:
                url, asset_id = upload(repo, f"v-{job.video_id}", video)
            except RepoError as exc:
                rows.append((cid, title, f"failed: {exc}"))
                continue
            queue.save(root, "pending", queue.new_entry(
                video_id=job.video_id, clip_id=cid, campaign=campaign, caption=clip["post"]["instagram"],
                asset_url=url, asset_id=asset_id, queued_at=stamp))
            rows.append((cid, title, "queued"))
    return rows
```

Modify `clipper/cli.py` imports (add after the `from clipper.jobs import ...` line):

```python
from clipper.publish import PublishError
from clipper.publish import post_next as post_next_mod
from clipper.publish.config import load_publish_config
from clipper.publish.enqueue import enqueue_job
from clipper.publish.gitops import commit_queue
from clipper.publish.queue import QUEUE_ROOT
```

Add handlers after `cmd_finish`:

```python
def cmd_queue(args: argparse.Namespace) -> int:
    cfg = load_publish_config()
    rows = enqueue_job(job_for(args.video_id), QUEUE_ROOT, cfg["clips_repo"], only=args.only)
    for cid, title, status in rows:
        print(f"{cid}  {status}  {title}")
    if any(status == "queued" for _, _, status in rows):
        commit_queue(f"queue: add {args.video_id}")
        print("queued entries committed and pushed")
    return 0


def cmd_post_next(args: argparse.Namespace) -> int:
    return post_next_mod.main(["--dry-run"] if args.dry_run else [])
```

In `build_parser`, before `return parser`:

```python
    q = sub.add_parser("queue", help="upload rendered clips and queue them for Instagram posting")
    q.add_argument("video_id")
    q.add_argument("--only", nargs="+")
    n = sub.add_parser("post-next", help="post the oldest queued clip to Instagram (normally run by GitHub Actions)")
    n.add_argument("--dry-run", action="store_true")
```

Replace `HANDLERS` with:

```python
HANDLERS = {"doctor": cmd_doctor, "prepare": cmd_prepare, "resolve": cmd_resolve,
            "produce": cmd_produce, "finish": cmd_finish, "queue": cmd_queue, "post-next": cmd_post_next}
```

Change the `except` in `main` to:

```python
    except (ConfigError, FetchError, ClipError, PublishError, FileNotFoundError) as exc:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_publish_enqueue.py tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: all tests pass (no regressions)

- [ ] **Step 6: Commit**

```bash
git add clipper/publish/enqueue.py clipper/cli.py tests/test_publish_enqueue.py tests/test_cli.py
git commit -m "feat: clipper queue and post-next commands" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Workflow and README

**Files:**
- Create: `.github/workflows/post-next.yml`
- Test: `tests/test_workflows.py`
- Modify: `README.md` (append a "Posting to Instagram" section)

**Interfaces:**
- Consumes: `python -m clipper.publish.post_next [--dry-run]`; secrets `IG_ACCESS_TOKEN`, `CLIPS_REPO_TOKEN`.
- Produces: workflow `post-next` triggered by `workflow_dispatch` with a boolean `dry_run` input (default true). The schedule is added in Task 9.

- [ ] **Step 1: Write the failing test**

Create `tests/test_workflows.py`:

```python
import yaml

from clipper.env import PROJECT_ROOT

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "post-next.yml"


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def triggers(doc: dict) -> dict:
    return doc.get("on") or doc.get(True)  # PyYAML parses a bare `on:` key as boolean True


def test_post_next_workflow_shape():
    doc = load()
    assert doc["concurrency"] == {"group": "ig-post", "cancel-in-progress": False}
    assert doc["permissions"] == {"contents": "write"}
    assert doc["jobs"]["post"]["runs-on"] == "ubuntu-latest"
    dispatch = triggers(doc)["workflow_dispatch"]
    assert dispatch["inputs"]["dry_run"]["default"] is True


def test_post_next_workflow_uses_the_light_entry_point_and_the_two_secrets():
    text = WORKFLOW.read_text()
    assert "python -m clipper.publish.post_next" in text
    assert "secrets.IG_ACCESS_TOKEN" in text and "secrets.CLIPS_REPO_TOKEN" in text
    assert "uv sync" not in text and "pip install ." not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflows.py -v`
Expected: FAIL with `FileNotFoundError` for `.github/workflows/post-next.yml`

- [ ] **Step 3: Write minimal implementation**

Create `.github/workflows/post-next.yml`:

```yaml
name: post-next

on:
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Create and process the container, but do not publish"
        type: boolean
        default: true

concurrency:
  group: ig-post
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  post:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install the only dependency (pyyaml)
        run: python -m pip install --quiet pyyaml
      - name: Configure git identity
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
      - name: Post the next queued clip
        env:
          IG_ACCESS_TOKEN: ${{ secrets.IG_ACCESS_TOKEN }}
          GH_TOKEN: ${{ secrets.CLIPS_REPO_TOKEN }}
          DRY_RUN: ${{ github.event_name == 'workflow_dispatch' && inputs.dry_run }}
        run: |
          if [ "$DRY_RUN" = "true" ]; then
            python -m clipper.publish.post_next --dry-run
          else
            python -m clipper.publish.post_next
          fi
```

Append to `README.md`:

````markdown

## Posting to Instagram

Clips are posted by GitHub Actions from a queue; rendering stays local. Design: `docs/superpowers/specs/2026-11-07-instagram-posting-design.md`.

```bash
uv run clipper queue <video_id> [--only clip_01]   # upload rendered clips, add them to queue/pending/, commit and push
uv run clipper post-next --dry-run                 # needs IG_ACCESS_TOKEN in the environment; never publishes
```

The `post-next` workflow posts one clip per run (manual run: Actions → post-next → Run workflow; keep **dry run** on to test).
Queue folders: `queue/pending/`, `queue/posted/` (with the Instagram permalink) and `queue/failed/`.
If a run reports that the token was rejected, generate a new one in the Meta App Dashboard (Use cases → Manage messaging & content on Instagram → Customize → API setup with Unified login → Generate token) and update the `IG_ACCESS_TOKEN` secret.
````

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflows.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/post-next.yml tests/test_workflows.py README.md
git commit -m "feat: post-next workflow (manual trigger) and README section" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Create the repos and set the secrets (outward-facing: confirm with the owner first)

**Files:** none (GitHub state only).

**Interfaces:**
- Produces: public repo `hammadalive7/content-clips`, private repo `hammadalive7/content-clipping` with this code pushed, secrets `IG_ACCESS_TOKEN` and `CLIPS_REPO_TOKEN` on the private repo.

Before running anything below, tell the owner exactly what will be created (a **public** repo and a **private** repo) and wait for a yes. The owner types both secret values themselves at hidden prompts; the executor must never see them.

- [ ] **Step 1: Create the public clips repo**

Run: `gh repo create hammadalive7/content-clips --public --description "Release assets that Instagram fetches when posting Reels" --add-readme`
Expected: prints the new repo URL.

- [ ] **Step 2: Create the private project repo and push `main` first so it becomes the default branch**

Run: `gh repo create hammadalive7/content-clipping --private --source . --remote origin && git push -u origin main`
Expected: remote `origin` added and `main` pushed. Then run `git push -u origin feature/clipper-v1`.

- [ ] **Step 3: Owner creates the fine-grained token for `CLIPS_REPO_TOKEN`**

Owner opens https://github.com/settings/personal-access-tokens/new and creates a token with: Repository access = Only select repositories → `content-clips`; Repository permissions → Contents: Read and write; expiration 1 year (put the date in a calendar). The owner keeps it private.

- [ ] **Step 4: Owner sets both secrets (hidden prompts)**

The owner runs these in their own terminal and pastes each value when prompted (nothing is echoed):

```bash
gh secret set IG_ACCESS_TOKEN -R hammadalive7/content-clipping
gh secret set CLIPS_REPO_TOKEN -R hammadalive7/content-clipping
```

- [ ] **Step 5: Verify the secrets exist (names only)**

Run: `gh secret list -R hammadalive7/content-clipping`
Expected: both `IG_ACCESS_TOKEN` and `CLIPS_REPO_TOKEN` are listed.

---

### Task 9: Verify end to end, then enable the schedule

**Files:**
- Modify: `tests/test_workflows.py` (add a schedule test)
- Modify: `.github/workflows/post-next.yml` (add the cron trigger)

**Interfaces:**
- Consumes: everything above, plus an already rendered job in `output/<video_id>/` (see `ls output/`).
- Produces: a verified real post and the scheduled workflow on `main`.

Posting is public. The owner chooses which clip to post and confirms before Step 4.

- [ ] **Step 1: Put the workflow on the default branch**

GitHub only offers `workflow_dispatch` for workflows that exist on the default branch. After owner confirmation run:

```bash
git checkout main && git merge --ff-only feature/clipper-v1 && git push origin main
```
Expected: fast-forward succeeds. If it does not, stop and ask the owner how to integrate (do not force anything).

- [ ] **Step 2: Queue one clip**

Pick a job that has a rendered clip: `ls output/`. Then run `uv run clipper queue <video_id> --only clip_01`.
Expected: `clip_01  queued  <title>` then `queued entries committed and pushed`; a file appears in `queue/pending/` on `origin/main`; a release `v-<video_id>` with `clip_01.mp4` exists in `hammadalive7/content-clips`.

- [ ] **Step 3: Dry run in Actions**

Run: `gh workflow run post-next.yml -R hammadalive7/content-clipping -f dry_run=true && sleep 8 && gh run watch -R hammadalive7/content-clipping $(gh run list -R hammadalive7/content-clipping --workflow post-next.yml --limit 1 --json databaseId --jq '.[0].databaseId')`
Expected log lines: `next: <id> (<caption start>)` then `dry run: container FINISHED; not publishing`.

If it instead fails, stop and report the exact message to the owner. Known possibilities: `container ERROR` (Instagram may not follow GitHub's redirect from the release download URL, which would need a design change such as serving the file from `raw.githubusercontent.com`); `unexpected content_publishing_limit response` (adjust the parsing in `InstagramClient.publishing_limit` to the real response); an error code 10 or 200 (permissions or account type). Do not retry in a loop.

- [ ] **Step 4: Real post (owner confirms the clip first)**

Run the same command with `-f dry_run=false`.
Expected: log line `posted <id>: https://www.instagram.com/...`; the entry moves to `queue/posted/` in a new commit from `github-actions[bot]`; the release asset is deleted; the Reel shows on the profile. Run `git pull` afterwards to fetch that commit.

- [ ] **Step 5: Write the failing schedule test**

Append to `tests/test_workflows.py`:

```python
def test_post_next_is_scheduled_three_times_a_day():
    schedule = triggers(load())["schedule"]
    assert schedule == [{"cron": "0 9,13,19 * * *"}]
```

Run: `uv run pytest tests/test_workflows.py -v`
Expected: FAIL with `KeyError: 'schedule'`

- [ ] **Step 6: Add the schedule**

In `.github/workflows/post-next.yml`, add under `on:` before `workflow_dispatch:`:

```yaml
  schedule:
    - cron: "0 9,13,19 * * *"
```

Run: `uv run pytest tests/test_workflows.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit and push to main**

```bash
git add .github/workflows/post-next.yml tests/test_workflows.py
git commit -m "feat: enable the Instagram posting schedule" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin main
```
Expected: pushed. Tell the owner the schedule is on, that cron times are UTC (edit the cron line to change them), and that GitHub pauses scheduled workflows after 60 days without repository activity.
