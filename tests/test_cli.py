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


class Stages:
    """Counting fake stages so resume behaviour can be observed without ffmpeg, network or models."""

    def __init__(self, tmp_path, monkeypatch, clip_ids=("clip_01",)):
        self.job = job_for("vid", jobs_dir=tmp_path / "jobs", output_dir=tmp_path / "out")
        job = self.job
        job.ensure_dirs()
        url = "https://www.youtube.com/watch?v=vid"
        job.write_json(job.job_file, {"url": url, "campaign": None})
        job.write_json(job.meta, {"title": "T", "channel": "C", "duration": 100.0, "url": url})
        job.write_json(job.words, [])
        self.write_clips([make_clip(c) for c in clip_ids])
        self.fetches, self.renders, self.fast_flags = [], [], []
        self.fail = set()

        def fake_fetch(job_, url_, clip, duration, cookies=None):
            src = job_.src_dir / f"{clip['id']}.mp4"
            assert not src.exists(), "stale section must be deleted before re-fetching (yt-dlp skips existing files)"
            self.fetches.append(clip["id"])
            if clip["id"] in self.fail:
                raise RuntimeError("boom")
            src.write_bytes(b"x")

        def fake_render(j, c, cfg, w, d):
            self.renders.append(c["id"])
            self.fast_flags.append(cfg["render"]["fast"])
            (j.out / f"{c['id']}.mp4").write_bytes(b"v")

        monkeypatch.setattr(cli, "job_for", lambda video_id: job)
        monkeypatch.setattr(cli.fetch, "fetch_section", fake_fetch)
        monkeypatch.setattr(cli.reframe, "run", lambda j, c, w, d: (j.crops_dir / f"{c['id']}.json").write_text("{}"))
        monkeypatch.setattr(cli.render, "render_clip", fake_render)
        monkeypatch.setattr(cli.package, "extract_frames", lambda video, duration, out_dir: [])

    def write_clips(self, clips):
        self.job.write_json(self.job.clips_resolved, {"video_id": "vid", "clips": clips, "rejected": []})


def test_unchanged_second_produce_does_not_refetch_or_rerender(tmp_path, monkeypatch):
    st = Stages(tmp_path, monkeypatch)
    assert cli.main(["produce", "vid"]) == 0
    assert cli.main(["produce", "vid"]) == 0
    assert st.fetches == ["clip_01"] and st.renders == ["clip_01"]


def test_changed_clip_times_refetch_the_section(tmp_path, monkeypatch):
    st = Stages(tmp_path, monkeypatch)
    assert cli.main(["produce", "vid"]) == 0
    moved = make_clip("clip_01")
    moved.update(start=40.0, end=70.0)
    st.write_clips([moved])
    assert cli.main(["produce", "vid"]) == 0
    assert st.fetches == ["clip_01", "clip_01"]
    assert st.renders == ["clip_01", "clip_01"]
    assert st.job.read_json(st.job.src_dir / "clip_01.json") == {"window": [38.0, 72.0]}


def test_fast_and_normal_renders_are_not_interchangeable(tmp_path, monkeypatch):
    st = Stages(tmp_path, monkeypatch)
    assert cli.main(["produce", "vid"]) == 0
    assert cli.main(["produce", "vid", "--fast"]) == 0
    assert st.renders == ["clip_01", "clip_01"] and st.fast_flags == [False, True]
    assert cli.main(["produce", "vid", "--fast"]) == 0
    assert len(st.renders) == 2  # same mode again: still fresh
    assert cli.main(["produce", "vid"]) == 0
    assert st.renders == ["clip_01"] * 3 and st.fast_flags[-1] is False
    assert len(st.fetches) == 1


def test_exit_code_reflects_only_clips_attempted_in_this_run(tmp_path, monkeypatch, capsys):
    st = Stages(tmp_path, monkeypatch, clip_ids=("clip_01", "clip_02"))
    assert cli.main(["produce", "vid", "--only", "clip_01"]) == 0
    st.fail.add("clip_02")
    assert cli.main(["produce", "vid", "--only", "clip_02"]) == 1
    assert st.job.read_json(st.job.results) == {"clip_01": None, "clip_02": "RuntimeError: boom"}
    assert cli.main(["produce", "vid", "--only", "clip_99"]) == 1  # nothing attempted
    capsys.readouterr()
