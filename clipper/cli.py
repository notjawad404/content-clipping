"""`clipper` command: thin orchestration over the stage modules."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path

from clipper import clips as clips_mod
from clipper import doctor, fetch, package, reframe, render, transcribe
from clipper.clips import ClipError
from clipper.config import ConfigError, load_config
from clipper.env import PROJECT_ROOT, prepend_ffmpeg_to_path
from clipper.fetch import FetchError
from clipper.jobs import Job, is_fresh, job_for, timed
from clipper.publish import PublishError
from clipper.publish import post_next as post_next_mod
from clipper.publish.config import load_publish_config
from clipper.publish.enqueue import enqueue_job
from clipper.publish.gitops import commit_queue
from clipper.publish.queue import QUEUE_ROOT


def _cfg(job: Job) -> dict:
    return load_config(job.read_json(job.job_file).get("campaign"), job.overrides)


def cmd_doctor(args: argparse.Namespace) -> int:
    checks = doctor.run_doctor()
    print(doctor.format_report(checks))
    return 0 if all(c.ok for c in checks) else 1


def cmd_prepare(args: argparse.Namespace) -> int:
    video_id = fetch.extract_video_id(args.url)
    disk = doctor.check_disk(PROJECT_ROOT)
    if not disk.ok:
        print(f"error: not enough disk space: {disk.detail}. {disk.fix}")
        return 1
    if args.campaign:
        load_config(args.campaign)  # fail fast on an unknown campaign
    job = job_for(video_id)
    job.ensure_dirs()
    prev = job.read_json(job.job_file) if job.job_file.exists() else {}
    campaign = args.campaign or prev.get("campaign")  # sticky: a rerun must not drop the campaign's required text/tags
    cookies_browser = args.cookies_from_browser or prev.get("cookies_browser")
    if campaign and not args.campaign:
        load_config(campaign)
    job.write_json(job.job_file, {"url": args.url, "campaign": campaign, "cookies_browser": cookies_browser})
    force = set(args.force or [])
    if "meta" in force or not job.meta.exists():
        with timed(job, "fetch_meta"):
            fetch.fetch_meta(job, args.url, cookies_browser)
    if force & {"audio", "transcribe"} or not job.sentences_txt.exists():
        if "audio" in force or job.audio() is None:
            with timed(job, "fetch_audio"):
                fetch.fetch_audio(job, args.url, cookies_browser)
        with timed(job, "transcribe"):
            transcribe.run(job)
    meta = job.read_json(job.meta)
    print(json.dumps({
        "video_id": video_id, "title": meta["title"], "channel": meta["channel"],
        "duration_min": round(meta["duration"] / 60, 1),
        "sentences": len(job.read_json(job.sentences_json)),
        "transcript": str(job.sentences_txt), "meta": str(job.meta),
        "write_clips_to": str(job.clips), "overrides": str(job.overrides),
    }, indent=2))
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    job = job_for(args.video_id)
    cfg = _cfg(job)
    result = clips_mod.run(job, cfg)
    for c in result["clips"]:
        print(f"OK    {c['id']}  score {c['score']:>4}  {c['duration']:5.1f}s  {c['title']}")
    for r in result["rejected"]:
        print(f"SKIP  {r['id']}  {r['reason']}")
    print(f"review_first: {str(bool(cfg.get('review_first'))).lower()}")
    return 0 if result["clips"] else 1


def _read_fingerprint(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_fingerprint(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data))


def _produce_one(job: Job, clip: dict, cfg: dict, info: dict, meta: dict, words: list[dict], force: set[str]) -> list[str]:
    cid = clip["id"]
    src = job.src_dir / f"{cid}.mp4"
    src_print = job.src_dir / f"{cid}.json"
    window = list(fetch.section_window(clip["start"], clip["end"], meta["duration"]))
    src_fp = {"window": window, "encode": fetch.SECTION_ENCODE}
    if "video" in force or not src.exists() or _read_fingerprint(src_print) != src_fp:
        src.unlink(missing_ok=True)  # yt-dlp skips a download whose file already exists
        src_print.unlink(missing_ok=True)
        with timed(job, f"fetch_{cid}"):
            fetch.fetch_section(job, info["url"], clip, meta["duration"], info.get("cookies_browser"))
        _write_fingerprint(src_print, src_fp)
    crops = job.crops_dir / f"{cid}.json"
    if "reframe" in force or not is_fresh(crops, [src]):
        with timed(job, f"reframe_{cid}"):
            reframe.run(job, clip, words, meta["duration"])
    out = job.out / f"{cid}.mp4"
    out_print = job.render_dir / f"{cid}.json"
    cfg_hash = hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()
    render_print = {"fast": bool(cfg["render"]["fast"]), "start": clip["start"], "end": clip["end"], "cfg": cfg_hash,
                    "hook_text": clip.get("hook_text"), "emphasis_words": clip.get("emphasis_words", [])}
    if ("render" in force or not is_fresh(out, [crops]) or _read_fingerprint(out_print) != render_print):
        with timed(job, f"render_{cid}"):
            render.render_clip(job, clip, cfg, words, meta["duration"])
        _write_fingerprint(out_print, render_print)
    (job.out / f"{cid}_post.md").write_text(package.post_markdown(clip))
    return [str(p) for p in package.extract_frames(out, clip["duration"], job.frames_dir)]


def cmd_produce(args: argparse.Namespace) -> int:
    job = job_for(args.video_id)
    job.ensure_dirs()
    cfg = _cfg(job)
    if args.fast:
        cfg["render"]["fast"] = True
    info, meta = job.read_json(job.job_file), job.read_json(job.meta)
    words, resolved = job.read_json(job.words), job.read_json(job.clips_resolved)
    results: dict[str, str | None] = job.read_json(job.results) if job.results.exists() else {}
    frames: dict[str, list[str]] = {}
    attempted_ok = False
    force = set(args.force or [])
    bot_check = False
    for clip in resolved["clips"]:
        if args.only and clip["id"] not in args.only:
            continue
        if bot_check:  # stop hammering YouTube; the user must decide on cookies first
            results[clip["id"]] = "skipped: YouTube bot check"
            continue
        try:
            frames[clip["id"]] = _produce_one(job, clip, cfg, info, meta, words, force)
            results[clip["id"]] = None
            attempted_ok = True
        except Exception as exc:  # one broken clip must never stop the rest
            (job.logs_dir / f"{clip['id']}_error.log").write_text(traceback.format_exc())
            lines = str(exc).splitlines()
            first_line = lines[0] if lines else ""
            if isinstance(exc, FetchError) and "bot check" in str(exc).lower():
                bot_check = True
                hint = lines[-1] if len(lines) > 1 else first_line
                results[clip["id"]] = f"{type(exc).__name__}: {first_line} | {hint}"
                print(hint, file=sys.stderr)
            else:
                results[clip["id"]] = f"{type(exc).__name__}: {first_line}"
    job.write_json(job.results, results)
    timings = job.read_json(job.timings) if job.timings.exists() else {}
    (job.out / "summary.md").write_text(package.summary_markdown(meta, resolved, results, timings))
    print(json.dumps({"output": str(job.out), "results": results, "qa_frames": frames}, indent=2))
    return 0 if attempted_ok else 1


def cmd_finish(args: argparse.Namespace) -> int:
    job = job_for(args.video_id)
    removed = package.cleanup(job)
    print(json.dumps({"removed": [str(p) for p in removed], "output": str(job.out)}, indent=2))
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    cfg = load_publish_config()
    rows = enqueue_job(job_for(args.video_id), QUEUE_ROOT, cfg["clips_repo"], only=args.only)
    for cid, title, status in rows:
        print(f"{cid}  {status}  {title}")
    if any(status == "queued" for _, _, status in rows):
        commit_queue(f"queue: add {args.video_id}")
        print("queued entries committed and pushed")
    return 1 if any(status.startswith("failed") for _, _, status in rows) else 0


def cmd_post_next(args: argparse.Namespace) -> int:
    return post_next_mod.main(["--dry-run"] if args.dry_run else [])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clipper", description="Local podcast clipper")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check tools, models, assets and disk space")
    p = sub.add_parser("prepare", help="download metadata + audio and transcribe")
    p.add_argument("url")
    p.add_argument("--campaign")
    p.add_argument("--cookies-from-browser", dest="cookies_from_browser")
    p.add_argument("--force", nargs="+", choices=["meta", "audio", "transcribe"])
    r = sub.add_parser("resolve", help="validate clips.json and compute exact cut times")
    r.add_argument("video_id")
    d = sub.add_parser("produce", help="download sections, reframe, render, write post files")
    d.add_argument("video_id")
    d.add_argument("--only", nargs="+")
    d.add_argument("--fast", action="store_true")
    d.add_argument("--force", nargs="+", choices=["video", "reframe", "render"])
    f = sub.add_parser("finish", help="delete downloaded media, keep transcripts and outputs")
    f.add_argument("video_id")
    q = sub.add_parser("queue", help="upload rendered clips and queue them for Instagram posting")
    q.add_argument("video_id")
    q.add_argument("--only", nargs="+")
    n = sub.add_parser("post-next", help="post the oldest queued clip to Instagram (normally run by GitHub Actions)")
    n.add_argument("--dry-run", action="store_true")
    return parser


HANDLERS = {"doctor": cmd_doctor, "prepare": cmd_prepare, "resolve": cmd_resolve,
            "produce": cmd_produce, "finish": cmd_finish, "queue": cmd_queue, "post-next": cmd_post_next}


def main(argv: list[str] | None = None) -> int:
    prepend_ffmpeg_to_path()
    args = build_parser().parse_args(argv)
    try:
        return HANDLERS[args.command](args)
    except (ConfigError, FetchError, ClipError, PublishError, FileNotFoundError) as exc:
        print(f"error: {exc}")
        return 2
