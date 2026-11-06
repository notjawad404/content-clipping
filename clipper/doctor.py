"""Environment preflight: binaries, Python packages, assets, disk space."""
from __future__ import annotations

import importlib.metadata
import importlib.util
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from clipper.env import FACE_MODEL_PATH, FFMPEG_FULL_DIR, FONT_PATH, PROJECT_ROOT, WHOOSH_PATH, ffmpeg_bin, ffmpeg_dir

MIN_FREE_GB = 5.0
SETUP_ASSETS = "bash scripts/setup_assets.sh"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""


def check_disk(path: Path, usage: Callable = shutil.disk_usage) -> Check:
    free_gb = usage(path).free / 1024**3
    return Check("disk space", free_gb >= MIN_FREE_GB, f"{free_gb:.1f} GB free (need {MIN_FREE_GB:.0f} GB)",
                 "Free up disk space, e.g. delete old folders in jobs/ and output/")


def listed_names(ffmpeg_list_output: str) -> set[str]:
    """Second column of `ffmpeg -filters` / `ffmpeg -encoders` entry lines."""
    return {parts[1] for parts in (line.split() for line in ffmpeg_list_output.splitlines()) if len(parts) >= 3}


def node_major(version_output: str) -> int | None:
    m = re.match(r"v(\d+)", version_output.strip())
    return int(m.group(1)) if m else None


def _output(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _dist_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run_doctor() -> list[Check]:
    checks = [Check("python", sys.version_info[:2] == (3, 12), sys.version.split()[0], "Run through `uv run` (Python 3.12)")]
    checks.append(Check("ffmpeg-full", (FFMPEG_FULL_DIR / "ffmpeg").exists(), f"using {ffmpeg_dir()}", "brew install ffmpeg-full"))
    filters = listed_names(_output([ffmpeg_bin(), "-hide_banner", "-filters"]))
    checks.append(Check("ffmpeg libass", {"ass", "subtitles"} <= filters, "ass/subtitles filters", "brew install ffmpeg-full"))
    encoders = listed_names(_output([ffmpeg_bin(), "-hide_banner", "-encoders"]))
    checks.append(Check("ffmpeg libx264", "libx264" in encoders, "libx264 encoder", "brew install ffmpeg-full"))
    major = node_major(_output(["node", "--version"]))
    checks.append(Check("node (yt-dlp JS runtime)", bool(major and major >= 20), f"node v{major}", "brew install node@22"))
    for dist in ("yt-dlp", "yt-dlp-ejs"):
        version = _dist_version(dist)
        checks.append(Check(dist, version is not None, f"{dist} {version}", "uv sync"))
    for module in ("parakeet_mlx", "mediapipe", "scenedetect", "cv2", "pysubs2"):
        checks.append(Check(module, importlib.util.find_spec(module) is not None, f"import {module}", "uv sync"))
    for label, path in (("face model", FACE_MODEL_PATH), ("caption font", FONT_PATH), ("whoosh sfx", WHOOSH_PATH)):
        checks.append(Check(label, path.exists(), str(path.relative_to(PROJECT_ROOT)), SETUP_ASSETS))
    checks.append(check_disk(PROJECT_ROOT))
    return checks


def format_report(checks: list[Check]) -> str:
    lines = []
    for c in checks:
        lines.append(f"{'OK  ' if c.ok else 'FAIL'} {c.name}: {c.detail}" + ("" if c.ok else f"\n     fix: {c.fix}"))
    lines.append("All checks passed." if all(c.ok for c in checks) else "Some checks failed; run the fixes above.")
    return "\n".join(lines)
