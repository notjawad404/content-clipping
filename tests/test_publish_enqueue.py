from datetime import datetime, timezone

import pytest

from clipper.jobs import job_for
from clipper.publish import PublishError, queue
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


def test_a_clip_without_an_instagram_caption_fails_before_any_upload(tmp_path):
    job = make_job(tmp_path, ["clip_01", "clip_02"], ["clip_01", "clip_02"])
    resolved = job.read_json(job.clips_resolved)
    del resolved["clips"][0]["post"]["instagram"]
    job.write_json(job.clips_resolved, resolved)
    root, upload = tmp_path / "queue", Uploader()
    rows = enqueue_job(job, root, "o/clips", upload=upload, now=NOW)
    assert rows[0][0] == "clip_01" and rows[0][2].startswith("failed:") and "post.instagram" in rows[0][2]
    assert rows[1] == ("clip_02", "title clip_02", "queued")
    assert upload.calls == [("o/clips", "v-vid", "clip_02.mp4")]
    assert [e["id"] for e in queue.load_all(root, "pending")] == ["vid_clip_02"]


def test_a_missing_clips_resolved_raises_file_not_found(tmp_path):
    job = make_job(tmp_path, [], [])
    job.clips_resolved.unlink()
    with pytest.raises(FileNotFoundError):
        enqueue_job(job, tmp_path / "queue", "o/clips", upload=Uploader(), now=NOW)


def test_an_unparseable_clips_resolved_raises_publish_error(tmp_path):
    job = make_job(tmp_path, [], [])
    job.clips_resolved.write_text("{not json")
    with pytest.raises(PublishError, match="clips.resolved.json"):
        enqueue_job(job, tmp_path / "queue", "o/clips", upload=Uploader(), now=NOW)
