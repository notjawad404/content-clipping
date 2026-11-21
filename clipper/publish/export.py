"""Keep a local copy of every queued clip with its captions, for manual uploads (Instagram etc.)."""
from __future__ import annotations

import re
import shutil
import urllib.request
from pathlib import Path

from clipper.env import OUTPUT_DIR, PROJECT_ROOT

UPLOADS_DIR = PROJECT_ROOT / "uploads"


def _clip_id(entry: dict) -> str:
    return entry["id"][len(entry["video_id"]) + 1:]


def _safe(text: str) -> str:
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip(" .")[:60] or "clip"


def captions_text(entry: dict) -> str:
    youtube = entry.get("youtube") or {}
    lines = [f"Title: {entry.get('title') or ''}", ""]
    if youtube.get("url"):
        lines += [f"YouTube: {youtube['url']}", ""]
    lines += ["== YouTube description ==", entry.get("youtube_description") or entry["caption"], "",
              "== YouTube tags ==", ", ".join(entry.get("youtube_tags") or []), "",
              "== TikTok caption ==", entry.get("tiktok_caption") or entry["caption"], "",
              "== Instagram caption ==", entry["caption"], ""]
    return "\n".join(lines)


def export_entry(entry: dict, video: Path | None = None, root: Path = UPLOADS_DIR,
                 fetch=None) -> Path | None:
    """Copy the clip and write its captions next to it. Returns the mp4 path, or None if no video is available."""
    folder = root / entry["video_id"]
    stem = f"{_clip_id(entry)} - {_safe(entry.get('title') or entry['caption'])}"
    target = folder / f"{stem}.mp4"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{_clip_id(entry)} - *"):
        if old.stem != stem:
            old.unlink()
    (folder / f"{stem}.txt").write_text(captions_text(entry), encoding="utf-8")
    if target.exists():
        return target
    source = video or OUTPUT_DIR / entry["video_id"] / f"{_clip_id(entry)}.mp4"
    if source.exists():
        shutil.copy2(source, target)
        return target
    if entry.get("asset_id") is not None:
        try:
            target.write_bytes((fetch or _download)(entry["asset_url"]))
            return target
        except OSError:
            target.unlink(missing_ok=True)
    (folder / f"{stem}.txt").unlink()
    return None


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as response:
        return response.read()
