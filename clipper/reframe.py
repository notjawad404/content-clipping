"""Reframe stage I/O: shot cuts (PySceneDetect) + face samples (MediaPipe) -> crops/<clip>.json."""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from clipper.clips import clip_words, sentence_end_times
from clipper.env import FACE_MODEL_PATH
from clipper.fetch import section_window
from clipper.jobs import Job
from clipper.layout import SAMPLE_FPS, Face, merge_short_shots, plan_clip

SHOT_THRESHOLD = 27.0
ANALYSIS_WIDTH = 960
LIP_TOP, LIP_BOTTOM, MOUTH_LEFT, MOUTH_RIGHT = 13, 14, 61, 291


def probe(video: Path) -> tuple[int, int, float, float]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV cannot open {video}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    cap.release()
    return w, h, fps, frames / fps


def detect_shots(video: Path) -> list[tuple[float, float]]:
    from scenedetect import ContentDetector, detect

    scenes = detect(str(video), ContentDetector(threshold=SHOT_THRESHOLD))
    return [(start.get_seconds(), end.get_seconds()) for start, end in scenes]


def mouth_ratio(pts: list[tuple[float, float]]) -> float:
    width = math.dist(pts[MOUTH_LEFT], pts[MOUTH_RIGHT])
    return math.dist(pts[LIP_TOP], pts[LIP_BOTTOM]) / width if width > 0 else 0.0


def sample_faces(video: Path, src_w: int, src_h: int, fps: float, t_offset: float = 0.0,
                 model_path: Path = FACE_MODEL_PATH) -> list[tuple[float, list[Face]]]:
    """Run FaceLandmarker ~SAMPLE_FPS times per second. Times are returned as (section time - t_offset)."""
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    options = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=4,
    )
    step = max(1, round(fps / SAMPLE_FPS))
    samples: list[tuple[float, list[Face]]] = []
    cap = cv2.VideoCapture(str(video))
    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        idx = 0
        while cap.grab():
            if idx % step == 0:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                t_src = idx / fps
                scale = ANALYSIS_WIDTH / frame.shape[1]
                if scale < 1:
                    frame = cv2.resize(frame, (ANALYSIS_WIDTH, round(frame.shape[0] * scale)))
                rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect_for_video(image, int(t_src * 1000))
                t = round(t_src - t_offset, 3)
                faces = []
                for landmarks in result.face_landmarks:
                    pts = [(lm.x * src_w, lm.y * src_h) for lm in landmarks]
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    box = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
                    faces.append(Face(t, box, mouth_ratio(pts)))
                samples.append((t, faces))
            idx += 1
    cap.release()
    return samples


def to_clip_shots(shots: list[tuple[float, float]], offset: float, duration: float) -> list[tuple[float, float]]:
    clip_shots = [(max(0.0, s - offset), min(duration, e - offset)) for s, e in shots]
    clip_shots = [(round(s, 3), round(e, 3)) for s, e in clip_shots if e - s > 0.01]
    if not clip_shots:
        return [(0.0, duration)]
    clip_shots[0] = (0.0, clip_shots[0][1])
    clip_shots[-1] = (clip_shots[-1][0], duration)
    return merge_short_shots(clip_shots)


def run(job: Job, clip: dict, words: list[dict], meta_duration: float | None) -> Path:
    src = job.src_dir / f"{clip['id']}.mp4"
    section_start, _ = section_window(clip["start"], clip["end"], meta_duration)
    offset = round(clip["start"] - section_start, 3)
    src_w, src_h, fps, _ = probe(src)
    shots = to_clip_shots(detect_shots(src), offset, clip["duration"])
    samples = sample_faces(src, src_w, src_h, fps, t_offset=offset)
    ends = sentence_end_times(clip_words(words, clip))
    segments = plan_clip(shots, samples, src_w, src_h, ends)
    out = job.crops_dir / f"{clip['id']}.json"
    job.write_json(out, {"clip_id": clip["id"], "src_w": src_w, "src_h": src_h, "offset": offset, "segments": segments})
    return out
