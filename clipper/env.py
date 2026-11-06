"""Project locations and external binaries."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
ASSETS_DIR = PROJECT_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
SFX_DIR = ASSETS_DIR / "sfx"
MODELS_DIR = PROJECT_ROOT / "models"
JOBS_DIR = PROJECT_ROOT / "jobs"
OUTPUT_DIR = PROJECT_ROOT / "output"

FACE_MODEL_PATH = MODELS_DIR / "face_landmarker.task"
FONT_PATH = FONTS_DIR / "Montserrat-Black.ttf"
WHOOSH_PATH = SFX_DIR / "whoosh.wav"

FFMPEG_FULL_DIR = Path(os.environ.get("CLIPPER_FFMPEG_DIR", "/opt/homebrew/opt/ffmpeg-full/bin"))


def ffmpeg_dir() -> Path | None:
    if (FFMPEG_FULL_DIR / "ffmpeg").exists():
        return FFMPEG_FULL_DIR
    found = shutil.which("ffmpeg")
    return Path(found).parent if found else None


def ffmpeg_bin() -> str:
    d = ffmpeg_dir()
    return str(d / "ffmpeg") if d else "ffmpeg"


def ffprobe_bin() -> str:
    d = ffmpeg_dir()
    return str(d / "ffprobe") if d else "ffprobe"


def prepend_ffmpeg_to_path() -> None:
    """Child processes (parakeet-mlx, yt-dlp) must find ffmpeg-full before any other ffmpeg."""
    d = ffmpeg_dir()
    if d is None:
        return
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if str(d) not in parts:
        os.environ["PATH"] = os.pathsep.join([str(d), *parts])
