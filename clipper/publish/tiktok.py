"""Thin TikTok Content Posting API client: OAuth refresh + direct post by file upload. Stdlib only."""
from __future__ import annotations

import json
import time
import urllib.parse
from typing import Callable

from clipper.publish import PublishError
from clipper.publish.youtube import urllib_http

API = "https://open.tiktokapis.com/v2"
TOKEN_URL = f"{API}/oauth/token/"
PRIVACY_LEVELS = ("SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE")
QUOTA_CODES = ("spam_risk_too_many_posts", "spam_risk_too_many_pending_share", "rate_limit_exceeded",
               "reached_active_user_cap")
TOKEN_CODES = ("access_token_invalid", "scope_not_authorized", "scope_permission_missed", "invalid_grant")
SINGLE_CHUNK_MAX = 64 * 1024 * 1024
CHUNK = 10 * 1024 * 1024


class TtError(PublishError):
    pass


class QuotaExceeded(TtError):
    pass


class TokenInvalid(TtError):
    pass


class ApiError(TtError):
    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


def _json(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _map_error(status: int, payload: dict) -> TtError:
    error = payload.get("error")
    if isinstance(error, dict):
        code, message = error.get("code"), error.get("message") or f"HTTP {status}"
    else:
        code, message = error, payload.get("error_description") or f"HTTP {status}"
    message = f"{code}: {message}" if code else message
    if status == 401 or code in TOKEN_CODES:
        return TokenInvalid(message)
    if status == 429 or code in QUOTA_CODES:
        return QuotaExceeded(message)
    return ApiError(message, status, code)


def chunk_plan(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count); the last chunk absorbs the remainder, as TikTok expects."""
    if size <= SINGLE_CHUNK_MAX:
        return size, 1
    return CHUNK, size // CHUNK


class TikTokClient:
    def __init__(self, client_key: str, client_secret: str, refresh_token: str,
                 http: Callable[[str, str, dict, bytes | None], tuple[int, dict, bytes]] = urllib_http,
                 sleep: Callable[[float], None] = time.sleep):
        self._key = client_key
        self._secret = client_secret
        self._refresh = refresh_token
        self._http = http
        self._sleep = sleep
        self._access: str | None = None

    def access_token(self) -> str:
        if self._access is None:
            body = urllib.parse.urlencode({"client_key": self._key, "client_secret": self._secret,
                                           "grant_type": "refresh_token", "refresh_token": self._refresh}).encode()
            status, _, raw = self._http("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body)
            payload = _json(raw)
            if status != 200 or not payload.get("access_token"):
                raise _map_error(status, payload)
            self._access = str(payload["access_token"])
        return self._access

    def _call(self, path: str, body: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.access_token()}", "Content-Type": "application/json; charset=UTF-8"}
        status, _, raw = self._http("POST", f"{API}{path}", headers, json.dumps(body).encode())
        payload = _json(raw)
        error = payload.get("error") or {}
        if status != 200 or (isinstance(error, dict) and error.get("code") not in (None, "ok")):
            raise _map_error(status, payload)
        return payload.get("data") or {}

    def creator_info(self) -> dict:
        return self._call("/post/publish/creator_info/query/", {})

    def _send(self, path: str, video: bytes, extra: dict) -> str:
        chunk_size, count = chunk_plan(len(video))
        data = self._call(path, {**extra, "source_info": {
            "source": "FILE_UPLOAD", "video_size": len(video), "chunk_size": chunk_size, "total_chunk_count": count}})
        publish_id, upload_url = data.get("publish_id"), data.get("upload_url")
        if not publish_id or not upload_url:
            raise ApiError("init response missing publish_id or upload_url")
        for index in range(count):
            start = index * chunk_size
            end = len(video) if index == count - 1 else start + chunk_size
            status, _, raw = self._http("PUT", upload_url, {
                "Content-Type": "video/mp4", "Content-Length": str(end - start),
                "Content-Range": f"bytes {start}-{end - 1}/{len(video)}"}, video[start:end])
            if status not in (200, 201, 206):
                raise _map_error(status, _json(raw))
        return str(publish_id)

    def upload(self, video: bytes, caption: str, privacy: str, *, allow_comment: bool = True,
               allow_duet: bool = True, allow_stitch: bool = True, brand_organic: bool = False,
               brand_content: bool = False) -> str:
        """Direct post; returns the publish id once every chunk is uploaded."""
        if brand_content and privacy == "SELF_ONLY":
            raise ApiError("branded content cannot be posted as SELF_ONLY", code="invalid_params")
        return self._send("/post/publish/video/init/", video, {"post_info": {
            "title": caption[:2200], "privacy_level": privacy, "disable_comment": not allow_comment,
            "disable_duet": not allow_duet, "disable_stitch": not allow_stitch,
            "brand_organic_toggle": brand_organic, "brand_content_toggle": brand_content,
            "video_cover_timestamp_ms": 1000}})

    def upload_draft(self, video: bytes) -> str:
        """Sends the video to the creator's TikTok inbox as a draft; the caption is added in the app."""
        return self._send("/post/publish/inbox/video/init/", video, {})

    def status(self, publish_id: str) -> dict:
        return self._call("/post/publish/status/fetch/", {"publish_id": publish_id})

    def wait(self, publish_id: str, interval_s: float, timeout_s: float,
             done: tuple[str, ...] = ("PUBLISH_COMPLETE",)) -> dict:
        """Poll until a `done` status (returns the status data); ApiError on FAILED or timeout."""
        waited = 0.0
        while True:
            data = self.status(publish_id)
            status = data.get("status")
            if status in done:
                return data
            if status == "FAILED":
                raise ApiError(f"post failed: {data.get('fail_reason') or 'no reason given'}", code="FAILED")
            if waited >= timeout_s:
                raise ApiError(f"still {status} after {int(waited)}s", code="TIMEOUT")
            self._sleep(interval_s)
            waited += interval_s
