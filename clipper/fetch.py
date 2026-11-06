"""YouTube downloads through the yt-dlp CLI of this venv."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from clipper.env import ffmpeg_dir
from clipper.jobs import Job

SECTION_PAD = 2.0
_ID_IN_URL = re.compile(r"(?:[?&]v=|/shorts/|/live/|/embed/|youtu\.be/)([A-Za-z0-9_-]{11})")
_BARE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
VIDEO_FORMAT = "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]"


class FetchError(Exception):
    pass


def extract_video_id(url: str) -> str:
    m = _ID_IN_URL.search(url)
    if m:
        return m.group(1)
    if _BARE_ID.fullmatch(url):
        return url
    raise FetchError(f"Could not find a YouTube video id in: {url}")


def base_cmd(cookies_browser: str | None = None) -> list[str]:
    cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", "--js-runtimes", "node"]
    d = ffmpeg_dir()
    if d is not None:
        cmd += ["--ffmpeg-location", str(d)]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    return cmd


def meta_cmd(url: str, cookies_browser: str | None = None) -> list[str]:
    return base_cmd(cookies_browser) + ["--dump-json", "--skip-download", url]


def audio_cmd(url: str, out_dir: Path, cookies_browser: str | None = None) -> list[str]:
    return base_cmd(cookies_browser) + [
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "-o", str(out_dir / "audio.%(ext)s"),
        url,
    ]


def section_window(start: float, end: float, duration: float | None, pad: float = SECTION_PAD) -> tuple[float, float]:
    s = max(0.0, start - pad)
    e = end + pad
    if duration:
        e = min(e, duration)
    return round(s, 3), round(e, 3)


def section_cmd(url: str, start: float, end: float, out_path: Path, cookies_browser: str | None = None) -> list[str]:
    return base_cmd(cookies_browser) + [
        "-f", VIDEO_FORMAT,
        "--download-sections", f"*{start:.3f}-{end:.3f}",
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "-o", str(out_path),
        url,
    ]


def parse_meta(info: dict) -> dict:
    chapters = [
        {"title": c.get("title", ""), "start": float(c.get("start_time", 0)), "end": float(c.get("end_time", 0))}
        for c in (info.get("chapters") or [])
    ]
    return {
        "video_id": info["id"],
        "title": info.get("title", ""),
        "channel": info.get("channel") or info.get("uploader", ""),
        "channel_handle": info.get("uploader_id", ""),
        "duration": float(info.get("duration") or 0),
        "chapters": chapters,
        "url": info.get("webpage_url") or f"https://www.youtube.com/watch?v={info['id']}",
    }


def run(cmd: list[str], log_path: Path) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(f"$ {' '.join(cmd)}\n\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}")
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
        hint = ""
        if "Sign in to confirm" in proc.stderr or "not a bot" in proc.stderr:
            hint = "\nYouTube bot check: ask the user before retrying with --cookies-from-browser."
        raise FetchError(f"yt-dlp failed (exit {proc.returncode}), log: {log_path}\n{tail}{hint}")
    return proc.stdout


def fetch_meta(job: Job, url: str, cookies_browser: str | None = None) -> dict:
    out = run(meta_cmd(url, cookies_browser), job.logs_dir / "fetch_meta.log")
    meta = parse_meta(json.loads(out.strip().splitlines()[-1]))
    job.write_json(job.meta, meta)
    return meta


def fetch_audio(job: Job, url: str, cookies_browser: str | None = None) -> Path:
    run(audio_cmd(url, job.root, cookies_browser), job.logs_dir / "fetch_audio.log")
    audio = job.audio()
    if audio is None:
        raise FetchError("yt-dlp finished but wrote no audio.* file")
    return audio


def fetch_section(job: Job, url: str, clip: dict, duration: float | None, cookies_browser: str | None = None) -> Path:
    out_path = job.src_dir / f"{clip['id']}.mp4"
    s, e = section_window(clip["start"], clip["end"], duration)
    run(section_cmd(url, s, e, out_path, cookies_browser), job.logs_dir / f"fetch_{clip['id']}.log")
    if not out_path.exists():
        raise FetchError(f"Section download for {clip['id']} produced no file")
    return out_path
