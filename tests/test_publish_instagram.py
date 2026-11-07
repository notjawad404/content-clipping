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


def test_container_status_requests_the_status_text_and_returns_the_code():
    http = FakeHttp({"status_code": "ERROR", "status": "Error: could not fetch the video"})
    assert client(http).container_status("999") == "ERROR"
    assert http.calls[0][2]["fields"] == "status_code,status"


def test_processing_failure_includes_the_status_text():
    http = FakeHttp({"status_code": "ERROR", "status": "Error: could not fetch the video"})
    with pytest.raises(ProcessingFailed) as caught:
        client(http).wait_until_finished("999", 10, 300)
    assert str(caught.value) == "container ERROR: Error: could not fetch the video"
    assert TOKEN not in str(caught.value)


def test_processing_failure_without_status_text_is_just_the_code():
    with pytest.raises(ProcessingFailed) as caught:
        client(FakeHttp({"status_code": "EXPIRED"})).wait_until_finished("999", 10, 300)
    assert str(caught.value) == "container EXPIRED"


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


class ReadFailsResponse(FakeResponse):
    def read(self):
        raise TimeoutError("read timed out")


def test_urllib_http_read_timeout_becomes_api_error(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: ReadFailsResponse(b""))
    with pytest.raises(ApiError, match="TimeoutError"):
        urllib_http("GET", "https://x/y", {"a": "1"})


def test_urllib_http_malformed_success_body_becomes_api_error(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: FakeResponse(b"not json"))
    with pytest.raises(ApiError):
        urllib_http("GET", "https://x/y", {"a": "1"})


def test_urllib_http_network_error_hides_its_text(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.URLError("dns failure")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ApiError) as caught:
        urllib_http("GET", "https://x/y", {"a": "1"})
    assert "dns failure" not in str(caught.value)
