import json
import subprocess

import pytest

from clipper import reframe
from clipper.env import FACE_MODEL_PATH, ffmpeg_bin
from clipper.jobs import job_for
from clipper.reframe import mouth_ratio, to_clip_shots


def test_to_clip_shots_shifts_clamps_and_merges_interior_only():
    shots = [(0.0, 1.5), (1.5, 2.2), (2.2, 20.0), (20.0, 40.0)]
    assert to_clip_shots(shots, offset=2.0, duration=30.0) == [(0.0, 0.2), (0.2, 18.0), (18.0, 30.0)]


def test_to_clip_shots_without_cuts_is_one_shot():
    assert to_clip_shots([], offset=2.0, duration=25.0) == [(0.0, 25.0)]


def test_mouth_ratio():
    pts = [(0.0, 0.0)] * 300
    pts[13], pts[14], pts[61], pts[291] = (50, 40), (50, 60), (30, 50), (70, 50)
    assert mouth_ratio(pts) == pytest.approx(0.5)


@pytest.mark.integration
def test_run_on_synthetic_video_without_faces(tmp_path):
    assert FACE_MODEL_PATH.exists(), "run scripts/setup_assets.sh first"
    job = job_for("synthetic", jobs_dir=tmp_path / "jobs", output_dir=tmp_path / "out")
    job.ensure_dirs()
    src = job.src_dir / "clip_01.mp4"
    subprocess.run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=1920x1080:rate=30:duration=8", "-pix_fmt", "yuv420p", str(src)], check=True)
    clip = {"id": "clip_01", "start": 2.0, "end": 6.0, "duration": 4.0, "first_word": 0, "last_word": 0}
    words = [{"i": 0, "w": "Hello.", "s": 2.5, "e": 3.0}]
    data = json.loads(reframe.run(job, clip, words, meta_duration=8.0).read_text())
    assert (data["src_w"], data["src_h"], data["offset"]) == (1920, 1080, 2.0)
    assert data["segments"][0]["start"] == 0.0 and data["segments"][-1]["end"] == 4.0
    assert {s["layout"] for s in data["segments"]} == {"fit"}
