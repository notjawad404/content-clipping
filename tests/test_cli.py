from clipper import cli
from clipper.cli import build_parser
from clipper.jobs import job_for


def test_parser_produce_options():
    args = build_parser().parse_args(["produce", "abc", "--only", "clip_01", "clip_03", "--force", "render", "--fast"])
    assert args.only == ["clip_01", "clip_03"] and args.force == ["render"] and args.fast


def make_clip(cid):
    return {"id": cid, "title": cid, "score": 8.0, "reason": "r", "hook_text": "HOOK", "start": 0.0, "end": 30.0,
            "duration": 30.0, "post": {p: "x" for p in ("instagram", "tiktok", "youtube", "x")}}


def test_produce_isolates_a_failing_clip(tmp_path, monkeypatch):
    job = job_for("vid", jobs_dir=tmp_path / "jobs", output_dir=tmp_path / "out")
    job.ensure_dirs()
    job.write_json(job.job_file, {"url": "https://www.youtube.com/watch?v=vid", "campaign": None})
    job.write_json(job.meta, {"title": "T", "channel": "C", "duration": 100.0, "url": "https://www.youtube.com/watch?v=vid"})
    job.write_json(job.words, [])
    job.write_json(job.clips_resolved, {"video_id": "vid", "clips": [make_clip("clip_01"), make_clip("clip_02")],
                                        "rejected": []})

    def fake_fetch(job_, url, clip, duration, cookies=None):
        if clip["id"] == "clip_02":
            raise RuntimeError("boom")
        (job_.src_dir / f"{clip['id']}.mp4").write_bytes(b"x")

    monkeypatch.setattr(cli, "job_for", lambda video_id: job)
    monkeypatch.setattr(cli.fetch, "fetch_section", fake_fetch)
    monkeypatch.setattr(cli.reframe, "run", lambda j, c, w, d: (j.crops_dir / f"{c['id']}.json").write_text("{}"))
    monkeypatch.setattr(cli.render, "render_clip", lambda j, c, cfg, w, d: (j.out / f"{c['id']}.mp4").write_bytes(b"v"))
    monkeypatch.setattr(cli.package, "extract_frames", lambda video, duration, out_dir: [])

    assert cli.main(["produce", "vid"]) == 0
    summary = (job.out / "summary.md").read_text()
    assert "| clip_01 |" in summary and "ready" in summary
    assert "FAILED: RuntimeError: boom" in summary
    assert (job.out / "clip_01_post.md").exists() and not (job.out / "clip_02_post.md").exists()
    assert (job.logs_dir / "clip_02_error.log").exists()
    assert job.read_json(job.results) == {"clip_01": None, "clip_02": "RuntimeError: boom"}


def test_known_errors_return_exit_code_2(capsys):
    assert cli.main(["prepare", "https://example.com/not-youtube"]) == 2
    assert "error:" in capsys.readouterr().out
