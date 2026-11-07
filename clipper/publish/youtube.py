"""Thin YouTube Data API v3 client: OAuth refresh + resumable video upload. Stdlib only; knows nothing about the queue."""
from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from clipper.publish import PublishError

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
QUOTA_REASONS = ("quotaExceeded", "uploadLimitExceeded", "dailyLimitExceeded", "rateLimitExceeded")


class YtError(PublishError):
    pass


class QuotaExceeded(YtError):
    pass


class TokenInvalid(YtError):
    pass


class ApiError(YtError):
    def __init__(self, message: str, status: int | None = None, reason: str | None = None):
        super().__init__(message)
        self.status = status
        self.reason = reason


def urllib_http(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, dict, bytes]:
    """One HTTP request. Returns (status, lower-cased headers, body) for any HTTP status; ApiError on network errors."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()
    except (OSError, http.client.HTTPException) as exc:
        raise ApiError(f"network error: {type(exc).__name__}") from None


def _json(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _map_error(status: int, raw: bytes) -> YtError:
    payload = _json(raw)
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message") or f"HTTP {status}"
        errors = error.get("errors") or [{}]
        reason = errors[0].get("reason") if isinstance(errors[0], dict) else None
    else:
        message, reason = payload.get("error_description") or str(error or f"HTTP {status}"), None
    if status == 401 or error == "invalid_grant":
        return TokenInvalid(message)
    if reason in QUOTA_REASONS:
        return QuotaExceeded(message)
    return ApiError(message, status, reason)


class YouTubeClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 http: Callable[[str, str, dict, bytes | None], tuple[int, dict, bytes]] = urllib_http):
        self._id = client_id
        self._secret = client_secret
        self._refresh = refresh_token
        self._http = http
        self._access: str | None = None

    def access_token(self) -> str:
        if self._access is None:
            body = urllib.parse.urlencode({"client_id": self._id, "client_secret": self._secret,
                                           "refresh_token": self._refresh, "grant_type": "refresh_token"}).encode()
            status, _, raw = self._http("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body)
            if status != 200:
                raise _map_error(status, raw)
            token = _json(raw).get("access_token")
            if not token:
                raise ApiError("token response missing access_token")
            self._access = str(token)
        return self._access

    def upload(self, video: bytes, title: str, description: str, tags: list[str] | None = None,
               privacy: str = "private", category_id: str = "22") -> str:
        """Resumable upload; returns the video id. `privacy` is private, unlisted or public."""
        auth = {"Authorization": f"Bearer {self.access_token()}"}
        metadata = {"snippet": {"title": title[:100], "description": description, "tags": tags or [],
                                "categoryId": category_id},
                    "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
        status, headers, raw = self._http(
            "POST", f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status",
            {**auth, "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "video/mp4",
             "X-Upload-Content-Length": str(len(video))},
            json.dumps(metadata).encode())
        if status != 200:
            raise _map_error(status, raw)
        session = headers.get("location")
        if not session:
            raise ApiError("upload session response missing Location header")
        status, _, raw = self._http("PUT", session, {**auth, "Content-Type": "video/mp4"}, video)
        if status not in (200, 201):
            raise _map_error(status, raw)
        video_id = _json(raw).get("id")
        if not video_id:
            raise ApiError("upload response missing video id")
        return str(video_id)
