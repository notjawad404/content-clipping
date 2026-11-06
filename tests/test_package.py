from clipper.jobs import job_for
from clipper.package import cleanup, frame_times, post_markdown, summary_markdown


def make_clip(cid="clip_01"):
    return {"id": cid, "title": "Why it works", "score": 8.6, "reason": "bold claim", "hook_text": "NOBODY SAYS THIS",
            "start": 75.0, "end": 120.0, "duration": 45.0,
            "post": {"instagram": "IG text", "tiktok": "TT text", "youtube": "YT text", "x": "X text"}}


def test_post_markdown_has_every_platform_block():
    md = post_markdown(make_clip())
    for label in ("Instagram Reels", "TikTok", "YouTube Shorts", "X"):
        assert f"## {label}" in md
    assert "```\nIG text\n```" in md
    assert "0:01:15 to 0:02:00 (45s)" in md


def test_summary_lists_status_rejections_links_and_timings():
    meta = {"title": "Ep 1", "channel": "Pod", "url": "https://www.youtube.com/watch?v=abc"}
    resolved = {"clips": [make_clip("clip_01"), make_clip("clip_02")],
                "rejected": [{"id": "clip_03", "title": "t", "reason": "too short"}]}
    md = summary_markdown(meta, resolved, {"clip_01": None, "clip_02": "RenderError: boom"}, {"transcribe": 120.5})
    assert "| clip_01 | 8.6 | 45s | Why it works | ready |" in md
    assert "FAILED: RenderError: boom" in md
    assert "watch?v=abc&t=75s" in md
    assert "- clip_03 (t): too short" in md
    assert "- transcribe: 120.5" in md


def test_summary_skips_clips_not_produced_yet():
    meta = {"title": "Ep", "channel": "Pod", "url": "https://youtu.be/abc"}
    md = summary_markdown(meta, {"clips": [make_clip()], "rejected": []}, {}, {})
    assert "clip_01" not in md


def test_frame_times():
    assert frame_times(40.0) == [0.5, 10.0, 24.0, 36.0]


def test_cleanup_removes_media_keeps_transcripts(tmp_path):
    job = job_for("v", jobs_dir=tmp_path / "jobs", output_dir=tmp_path / "out")
    job.ensure_dirs()
    (job.root / "audio.m4a").write_bytes(b"a")
    (job.src_dir / "clip_01.mp4").write_bytes(b"v")
    job.write_json(job.words, [])
    removed = cleanup(job)
    assert len(removed) == 2
    assert job.audio() is None and not job.src_dir.exists() and job.words.exists()
