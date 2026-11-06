"""Post captions, run summary, QA frames and cleanup."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from clipper.env import ffmpeg_bin
from clipper.jobs import Job
from clipper.transcribe import format_timestamp

PLATFORM_LABELS = {"instagram": "Instagram Reels", "tiktok": "TikTok", "youtube": "YouTube Shorts", "x": "X"}


def frame_times(duration: float) -> list[float]:
    """First frame (hook visible), then 25%, 60% and 90% through the clip."""
    return [min(0.5, duration / 2)] + [round(duration * p, 2) for p in (0.25, 0.6, 0.9)]


def extract_frames(video: Path, duration: float, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for k, t in enumerate(frame_times(duration)):
        path = out_dir / f"{video.stem}_{k}.jpg"
        subprocess.run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=540:-2", str(path)], check=True)
        paths.append(path)
    return paths


def post_markdown(clip: dict) -> str:
    lines = [
        f"# {clip['title']}", "",
        f"- **File:** {clip['id']}.mp4",
        f"- **Score:** {clip['score']}/10 ({clip['reason']})",
        f"- **Hook text:** {clip['hook_text']}",
        f"- **Source:** {format_timestamp(clip['start'])} to {format_timestamp(clip['end'])} ({clip['duration']:.0f}s)",
        "",
    ]
    for key, label in PLATFORM_LABELS.items():
        lines += [f"## {label}", "", "```", clip["post"][key], "```", ""]
    return "\n".join(lines)


def summary_markdown(meta: dict, resolved: dict, results: dict[str, str | None], timings: dict) -> str:
    lines = [f"# {meta['title']}", "", f"Channel: {meta['channel']}  ", f"Source: {meta['url']}", "",
             "## Clips", "", "| Clip | Score | Length | Title | Status | Source time |", "|---|---|---|---|---|---|"]
    for clip in resolved["clips"]:
        if clip["id"] not in results:
            continue
        err = results[clip["id"]]
        status = "ready" if err is None else f"FAILED: {err}"
        link = f"{meta['url']}&t={int(clip['start'])}s" if "watch?v=" in meta["url"] else meta["url"]
        title = clip["title"].replace("|", "/")
        lines.append(f"| {clip['id']} | {clip['score']} | {clip['duration']:.0f}s | {title} | {status} | "
                     f"[{format_timestamp(clip['start'])}]({link}) |")
    if resolved.get("rejected"):
        lines += ["", "## Not used", ""] + [f"- {r['id']} ({r['title']}): {r['reason']}" for r in resolved["rejected"]]
    if timings:
        lines += ["", "## Stage timings (seconds)", ""] + [f"- {k}: {v}" for k, v in timings.items()]
    return "\n".join(lines) + "\n"


def cleanup(job: Job) -> list[Path]:
    removed: list[Path] = []
    audio = job.audio()
    if audio is not None:
        audio.unlink()
        removed.append(audio)
    if job.src_dir.exists():
        shutil.rmtree(job.src_dir)
        removed.append(job.src_dir)
    return removed
