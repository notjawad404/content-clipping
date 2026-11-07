"""Thin Instagram Graph API client (Instagram API with Unified Login). Knows nothing about GitHub or the queue."""
from __future__ import annotations

import http.client
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
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise ApiError(f"network error: {type(exc).__name__}") from None


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
