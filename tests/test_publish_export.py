from clipper.publish.export import export_entry

ENTRY = {"id": "vid_clip_01", "video_id": "vid", "title": "Mandy is NOT okay 💀 #GTA6", "caption": "ig caption #GTA6",
         "youtube_description": "yt desc", "tiktok_caption": "tt caption", "asset_url": "https://x/a.mp4",
         "asset_id": 7, "youtube": {"url": "https://www.youtube.com/shorts/yt1"}}


def test_copies_the_local_render_and_writes_captions(tmp_path):
    video = tmp_path / "in.mp4"
    video.write_bytes(b"video")
    out = export_entry(ENTRY, video, root=tmp_path / "uploads")
    assert out.name == "clip_01 - Mandy is NOT okay.mp4" and out.read_bytes() == b"video"
    text = out.with_suffix(".txt").read_text(encoding="utf-8")
    assert "tt caption" in text and "yt desc" in text and "ig caption #GTA6" in text and "shorts/yt1" in text


def test_downloads_when_no_local_render_and_renames_on_new_title(tmp_path):
    root = tmp_path / "uploads"
    export_entry(ENTRY, tmp_path / "missing.mp4", root=root, fetch=lambda url: b"dl")
    out = export_entry({**ENTRY, "title": "New title"}, tmp_path / "missing.mp4", root=root, fetch=lambda url: b"dl")
    assert sorted(p.name for p in (root / "vid").iterdir()) == ["clip_01 - New title.mp4", "clip_01 - New title.txt"]
    assert out.read_bytes() == b"dl"


def test_no_video_anywhere_leaves_nothing(tmp_path):
    root = tmp_path / "uploads"
    assert export_entry({**ENTRY, "asset_id": None}, tmp_path / "missing.mp4", root=root) is None
    assert list((root / "vid").iterdir()) == []
