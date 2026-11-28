"""Thin Publer API client: media upload + publish/draft posts + job polling. Stdlib only."""
from __future__ import annotations

import json
import time
import uuid
from typing import Callable

from clipper.publish import PublishError
from clipper.publish.youtube import urllib_http

API = "https://app.publer.com/api/v1"


class PbError(PublishError):
    pass


class QuotaExceeded(PbError):
    pass


class TokenInvalid(PbError):
    pass


class ApiError(PbError):
    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


def _json(raw: bytes):
    try:
        return json.loads(raw.decode() or "{}")
    except ValueError:
        return {}


def _unwrap(payload):
    if isinstance(payload, dict) and isinstance(payload.get("data"), (dict, list)) and "id" not in payload:
        return payload["data"]
    return payload


def _map_error(status: int, payload) -> PbError:
    message = f"HTTP {status}"
    if isinstance(payload, dict):
        error = payload.get("error") or payload.get("errors") or payload.get("message")
        if error:
            message = f"HTTP {status}: {json.dumps(error) if not isinstance(error, str) else error}"
    if status in (401, 403):
        return TokenInvalid(message)
    if status == 429:
        return QuotaExceeded(message)
    return ApiError(message, status)


def multipart(fields: dict[str, str], name: str, filename: str, data: bytes) -> tuple[str, bytes]:
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
             for k, v in fields.items()]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                 f"Content-Type: video/mp4\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", b"".join(parts)


class PublerClient:
    def __init__(self, api_key: str, workspace_id: str | None,
                 http: Callable[[str, str, dict, bytes | None], tuple[int, dict, bytes]] = urllib_http,
                 sleep: Callable[[float], None] = time.sleep):
        self._key = api_key
        self._workspace = workspace_id
        self._http = http
        self._sleep = sleep

    def _headers(self, content_type: str | None = "application/json") -> dict:
        headers = {"Authorization": f"Bearer-API {self._key}", "Accept": "application/json"}
        if self._workspace:
            headers["Publer-Workspace-Id"] = self._workspace
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _call(self, method: str, path: str, body: dict | None = None, *, raw_body: bytes | None = None,
              content_type: str | None = "application/json"):
        data = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
        status, _, raw = self._http(method, f"{API}{path}", self._headers(content_type if data else None), data)
        payload = _json(raw)
        if status not in (200, 201, 202):
            raise _map_error(status, payload)
        return _unwrap(payload)

    def workspaces(self) -> list[dict]:
        return self._call("GET", "/workspaces") or []

    def accounts(self) -> list[dict]:
        return self._call("GET", "/accounts") or []

    def upload_video(self, video: bytes, filename: str) -> str:
        content_type, body = multipart({"direct_upload": "false", "in_library": "false"}, "file", filename, video)
        media = self._call("POST", "/media", raw_body=body, content_type=content_type)
        media_id = media.get("id") if isinstance(media, dict) else None
        if not media_id:
            raise ApiError("media upload response has no id")
        return str(media_id)

    def create_posts(self, posts: list[dict], *, draft: bool = False) -> str:
        """Returns the job id. Publish now unless `draft`."""
        path = "/posts/schedule" if draft else "/posts/schedule/publish"
        payload = self._call("POST", path, {"bulk": {"state": "draft" if draft else "scheduled", "posts": posts}})
        job_id = payload.get("job_id") if isinstance(payload, dict) else None
        if not job_id:
            raise ApiError("post response has no job_id")
        return str(job_id)

    def wait(self, job_id: str, interval_s: float, timeout_s: float) -> dict:
        """Poll until the job completes; returns its payload ({"failures": ...}). ApiError on failed or timeout."""
        waited = 0.0
        while True:
            job = self._call("GET", f"/job_status/{job_id}")
            job = job if isinstance(job, dict) else {}
            status = job.get("status")
            result = job.get("result") if isinstance(job.get("result"), dict) else job
            if status == "complete":
                return result.get("payload") or {}
            if status == "failed":
                raise ApiError(f"job failed: {json.dumps(result.get('payload') or result)[:300]}", code="FAILED")
            if waited >= timeout_s:
                raise ApiError(f"job still {status} after {int(waited)}s", code="TIMEOUT")
            self._sleep(interval_s)
            waited += interval_s
