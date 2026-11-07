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
