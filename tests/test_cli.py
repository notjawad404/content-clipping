import yaml

from clipper import cli
from clipper.cli import build_parser
from clipper.fetch import FetchError
from clipper.jobs import job_for
from clipper.publish.gitops import GitError


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
    assert st.job.read_json(st.job.src_dir / "clip_01.json") == {"window": [38.0, 72.0], "encode": cli.fetch.SECTION_ENCODE}


def test_section_fetched_with_old_encode_settings_is_refetched(tmp_path, monkeypatch):
    st = Stages(tmp_path, monkeypatch)
    assert cli.main(["produce", "vid"]) == 0
    fp = st.job.src_dir / "clip_01.json"
    window = list(cli.fetch.section_window(0.0, 30.0, 100.0))
    st.job.write_json(fp, {"window": window})  # old fingerprint: window only, same clip times
    assert cli.main(["produce", "vid"]) == 0
    assert st.fetches == ["clip_01", "clip_01"]
    assert st.job.read_json(fp) == {"window": window, "encode": cli.fetch.SECTION_ENCODE}


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


def test_prepare_keeps_campaign_and_cookies_when_rerun_without_flags(tmp_path, monkeypatch, capsys):
    job = job_for("abcdefghijk", jobs_dir=tmp_path / "jobs", output_dir=tmp_path / "out")
    url = "https://www.youtube.com/watch?v=abcdefghijk"

    def fake_meta(job_, url_, cookies=None):
        job_.write_json(job_.meta, {"title": "T", "channel": "C", "duration": 100.0, "url": url})

    def fake_transcribe(job_):
        job_.write_json(job_.sentences_json, [])
        job_.sentences_txt.write_text("")

    monkeypatch.setattr(cli, "job_for", lambda video_id: job)
    monkeypatch.setattr(cli.doctor, "check_disk", lambda root: type("D", (), {"ok": True})())
    monkeypatch.setattr(cli.fetch, "fetch_meta", fake_meta)
    monkeypatch.setattr(cli.fetch, "fetch_audio", lambda j, u, c=None: (j.root / "audio.m4a").write_bytes(b"a"))
    monkeypatch.setattr(cli.transcribe, "run", fake_transcribe)

    assert cli.main(["prepare", url, "--campaign", "example", "--cookies-from-browser", "chrome"]) == 0
    assert cli.main(["prepare", url]) == 0
    saved = job.read_json(job.job_file)
    assert saved["campaign"] == "example" and saved["cookies_browser"] == "chrome"
    assert cli.main(["prepare", url, "--cookies-from-browser", "firefox"]) == 0
    assert job.read_json(job.job_file)["cookies_browser"] == "firefox"
    assert job.read_json(job.job_file)["campaign"] == "example"
    capsys.readouterr()


def test_resolve_alone_does_not_rerender_but_content_changes_do(tmp_path, monkeypatch):
    st = Stages(tmp_path, monkeypatch, clip_ids=("clip_01", "clip_02"))
    assert cli.main(["produce", "vid"]) == 0
    assert st.renders == ["clip_01", "clip_02"]
    st.write_clips([make_clip("clip_01"), make_clip("clip_02")])  # what `resolve` does: rewrite the same content
    st.job.overrides.write_text("review_first: false\n")          # touching overrides alone must not matter
    assert cli.main(["produce", "vid"]) == 0
    assert st.renders == ["clip_01", "clip_02"]
    changed = make_clip("clip_02")
    changed["hook_text"] = "NEW HOOK"
    st.write_clips([make_clip("clip_01"), changed])
    assert cli.main(["produce", "vid"]) == 0
    assert st.renders == ["clip_01", "clip_02", "clip_02"]
    st.job.overrides.write_text(yaml.safe_dump({"captions": {"size": 99}}))
    assert cli.main(["produce", "vid"]) == 0
    assert st.renders == ["clip_01", "clip_02", "clip_02", "clip_01", "clip_02"]
    assert cli.main(["produce", "vid"]) == 0
    assert len(st.renders) == 5
    assert len(st.fetches) == 2


def test_bot_check_stops_fetching_and_records_hint(tmp_path, monkeypatch, capsys):
    st = Stages(tmp_path, monkeypatch, clip_ids=("clip_01", "clip_02", "clip_03"))
    calls = []

    def blocked(job_, url_, clip, duration, cookies=None):
        calls.append(clip["id"])
        raise FetchError("yt-dlp failed (exit 1), log: x\nSign in to confirm you're not a bot\n"
                         "YouTube bot check: ask the user before retrying with --cookies-from-browser.")

    monkeypatch.setattr(cli.fetch, "fetch_section", blocked)
    assert cli.main(["produce", "vid"]) == 1
    assert calls == ["clip_01"]
    results = st.job.read_json(st.job.results)
    assert "bot check" in results["clip_01"].lower() and "--cookies-from-browser" in results["clip_01"]
    assert results["clip_02"] == results["clip_03"] == "skipped: YouTube bot check"
    assert (st.job.out / "summary.md").exists()
    captured = capsys.readouterr()
    assert "YouTube bot check" in captured.out + captured.err


def test_parser_queue_and_post_next():
    args = build_parser().parse_args(["queue", "abc", "--only", "clip_01"])
    assert args.video_id == "abc" and args.only == ["clip_01"]
    assert build_parser().parse_args(["post-next", "--dry-run"]).dry_run


PUBLISH_CFG = {"clips_repo": "o/clips", "queue_branch": "master"}


def queue_cli(monkeypatch, rows, commit=lambda message: True):
    commits = []
    monkeypatch.setattr(cli, "load_publish_config", lambda: PUBLISH_CFG)
    monkeypatch.setattr(cli, "commit_queue", lambda message, branch=None: commits.append(message) or commit(message))
    monkeypatch.setattr(cli, "enqueue_job", lambda job, root, repo, only=None: rows)
    return commits


def test_queue_command_passes_the_configured_branch_to_commit_queue(monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "load_publish_config", lambda: {**PUBLISH_CFG, "queue_branch": "trunk"})
    monkeypatch.setattr(cli, "commit_queue", lambda message, branch=None: seen.append((message, branch)) or True)
    monkeypatch.setattr(cli, "enqueue_job", lambda job, root, repo, only=None: [("clip_01", "T", "queued")])
    assert cli.main(["queue", "vid"]) == 0
    assert seen == [("queue: add vid", "trunk")]


def test_queue_command_reports_a_wrong_branch_refusal_as_one_line_error(monkeypatch, capsys):
    def refuse(message, branch=None):
        raise GitError(f"refusing to commit: you are on 'feature/x' but the queue lives on {branch!r}; "
                       f"switch with `git checkout {branch}`")

    monkeypatch.setattr(cli, "load_publish_config", lambda: PUBLISH_CFG)
    monkeypatch.setattr(cli, "commit_queue", refuse)
    monkeypatch.setattr(cli, "enqueue_job", lambda job, root, repo, only=None: [("clip_01", "T", "queued")])
    assert cli.main(["queue", "vid"]) == 2
    assert "git checkout master" in capsys.readouterr().out


def test_queue_command_commits_when_something_was_queued(monkeypatch, capsys):
    commits = queue_cli(monkeypatch, [("clip_01", "T", "queued")])
    assert cli.main(["queue", "vid"]) == 0
    assert commits == ["queue: add vid"]
    out = capsys.readouterr().out
    assert "clip_01" in out and "queued entries committed and pushed" in out


def test_queue_command_retries_the_commit_when_every_clip_is_already_queued(monkeypatch):
    commits = queue_cli(monkeypatch, [("clip_01", "T", "skipped: already queued")])
    assert cli.main(["queue", "vid"]) == 0
    assert commits == ["queue: add vid"]


def test_queue_command_does_not_commit_when_no_clip_was_queued_or_retryable(monkeypatch):
    commits = queue_cli(monkeypatch, [("clip_01", "T", "skipped: no rendered mp4"), ("clip_02", "T", "failed: x")])
    assert cli.main(["queue", "vid"]) == 1
    commits_skipped = queue_cli(monkeypatch, [("clip_01", "T", "skipped: no rendered mp4")])
    assert cli.main(["queue", "vid"]) == 0
    assert commits == [] and commits_skipped == []
    empty = queue_cli(monkeypatch, [])
    assert cli.main(["queue", "vid"]) == 0 and empty == []


def test_queue_command_says_nothing_new_when_commit_queue_returns_false(monkeypatch, capsys):
    queue_cli(monkeypatch, [("clip_01", "T", "skipped: already queued")], commit=lambda message: False)
    assert cli.main(["queue", "vid"]) == 0
    out = capsys.readouterr().out
    assert "nothing new to commit" in out and "committed and pushed" not in out


def test_queue_command_second_run_retries_after_a_failed_commit(monkeypatch, capsys):
    results = iter([GitError("git push failed: rejected"), True])

    def commit(message):
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result

    commits = queue_cli(monkeypatch, [("clip_01", "T", "queued")], commit=commit)
    assert cli.main(["queue", "vid"]) == 2
    assert "error: git push failed: rejected" in capsys.readouterr().out
    queue_cli_rows = [("clip_01", "T", "skipped: already queued")]
    monkeypatch.setattr(cli, "enqueue_job", lambda job, root, repo, only=None: queue_cli_rows)
    assert cli.main(["queue", "vid"]) == 0
    assert commits == ["queue: add vid", "queue: add vid"]
    assert "queued entries committed and pushed" in capsys.readouterr().out


def test_queue_command_commits_the_queued_clips_but_exits_nonzero_when_any_failed(monkeypatch, capsys):
    commits = []
    monkeypatch.setattr(cli, "load_publish_config", lambda: PUBLISH_CFG)
    monkeypatch.setattr(cli, "commit_queue", lambda message, branch=None: commits.append(message))
    monkeypatch.setattr(cli, "enqueue_job", lambda job, root, repo, only=None: [
        ("clip_01", "A", "failed: upload asset failed: denied"), ("clip_02", "B", "queued")])
    assert cli.main(["queue", "vid"]) == 1
    assert commits == ["queue: add vid"]
    assert "failed: upload asset failed: denied" in capsys.readouterr().out


def test_queue_command_does_not_commit_when_every_clip_failed(monkeypatch):
    commits = []
    monkeypatch.setattr(cli, "load_publish_config", lambda: PUBLISH_CFG)
    monkeypatch.setattr(cli, "commit_queue", lambda message, branch=None: commits.append(message))
    monkeypatch.setattr(cli, "enqueue_job", lambda job, root, repo, only=None: [("clip_01", "A", "failed: x")])
    assert cli.main(["queue", "vid"]) == 1
    assert commits == []


def test_queue_command_reports_a_commit_failure_as_one_line_error(monkeypatch, capsys):
    def boom(message, branch=None):
        raise GitError("git push failed: rejected")

    monkeypatch.setattr(cli, "load_publish_config", lambda: PUBLISH_CFG)
    monkeypatch.setattr(cli, "commit_queue", boom)
    monkeypatch.setattr(cli, "enqueue_job", lambda job, root, repo, only=None: [("clip_01", "T", "queued")])
    assert cli.main(["queue", "vid"]) == 2
    out = capsys.readouterr().out
    assert "error: git push failed: rejected" in out and "Traceback" not in out


def test_queue_command_reports_a_missing_clips_resolved_as_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_publish_config", lambda: PUBLISH_CFG)
    monkeypatch.setattr(cli, "job_for", lambda video_id: job_for(video_id, jobs_dir=tmp_path / "jobs",
                                                                  output_dir=tmp_path / "out"))
    assert cli.main(["queue", "vid"]) == 2
    assert capsys.readouterr().out.startswith("error: ")


def test_post_next_command_delegates_to_the_module(monkeypatch):
    seen = []
    monkeypatch.setattr(cli.post_next_mod, "main", lambda argv: seen.append(argv) or 0)
    assert cli.main(["post-next", "--dry-run"]) == 0 and cli.main(["post-next"]) == 0
    assert seen == [["--dry-run"], []]
