import json
import urllib.parse

import pytest

from clipper.publish.youtube import ApiError, QuotaExceeded, TokenInvalid, YouTubeClient

SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=abc"


class FakeHttp:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def err(status, reason=None, message="boom"):
    body = {"error": {"message": message, "errors": [{"reason": reason}]}}
    return status, {}, json.dumps(body).encode()


TOKEN_OK = (200, {}, b'{"access_token": "AT"}')
SESSION_OK = (200, {"location": SESSION}, b"")
UPLOAD_OK = (200, {}, b'{"id": "vid123"}')


def client(*responses):
    http = FakeHttp(*responses)
    return YouTubeClient("cid", "csecret", "rtoken", http=http), http


def test_refresh_request_and_token_cached():
    c, http = client(TOKEN_OK)
    assert c.access_token() == "AT" and c.access_token() == "AT"
    assert len(http.calls) == 1
    method, url, _, body = http.calls[0]
    assert method == "POST" and url == "https://oauth2.googleapis.com/token"
    assert urllib.parse.parse_qs(body.decode()) == {"client_id": ["cid"], "client_secret": ["csecret"],
                                                    "refresh_token": ["rtoken"], "grant_type": ["refresh_token"]}


def test_invalid_grant_is_token_invalid():
    body = b'{"error": "invalid_grant", "error_description": "Token has been expired or revoked."}'
    with pytest.raises(TokenInvalid):
        client((400, {}, body))[0].access_token()


def test_upload_flow_and_request_shapes():
    c, http = client(TOKEN_OK, SESSION_OK, UPLOAD_OK)
    assert c.upload(b"VIDEO", "My title #Shorts", "desc", ["a"], privacy="private") == "vid123"
    _, start_url, start_headers, start_body = http.calls[1]
    assert "uploadType=resumable" in start_url and "part=snippet,status" in start_url
    assert start_headers["Authorization"] == "Bearer AT"
    assert start_headers["X-Upload-Content-Length"] == "5"
    meta = json.loads(start_body)
    assert meta["status"]["privacyStatus"] == "private" and meta["snippet"]["title"] == "My title #Shorts"
    method, url, headers, body = http.calls[2]
    assert (method, url, body) == ("PUT", SESSION, b"VIDEO") and headers["Authorization"] == "Bearer AT"


def test_title_truncated_to_100_chars():
    c, http = client(TOKEN_OK, SESSION_OK, UPLOAD_OK)
    c.upload(b"V", "x" * 150, "d")
    assert len(json.loads(http.calls[1][3])["snippet"]["title"]) == 100


def test_quota_error_on_session_start():
    with pytest.raises(QuotaExceeded):
        client(TOKEN_OK, err(403, "quotaExceeded"))[0].upload(b"V", "t", "d")


def test_401_is_token_invalid():
    with pytest.raises(TokenInvalid):
        client(TOKEN_OK, err(401))[0].upload(b"V", "t", "d")


def test_other_error_is_api_error_with_status_and_reason():
    with pytest.raises(ApiError) as info:
        client(TOKEN_OK, SESSION_OK, err(400, "invalidVideo"))[0].upload(b"V", "t", "d")
    assert info.value.status == 400 and info.value.reason == "invalidVideo"


def test_missing_location_header():
    with pytest.raises(ApiError):
        client(TOKEN_OK, (200, {}, b""))[0].upload(b"V", "t", "d")


def test_upload_response_without_id():
    with pytest.raises(ApiError):
        client(TOKEN_OK, SESSION_OK, (200, {}, b"{}"))[0].upload(b"V", "t", "d")
