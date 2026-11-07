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
