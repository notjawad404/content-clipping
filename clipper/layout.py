"""Pure reframing logic: face samples -> tracks -> per-shot layout segments with crop boxes."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

SAMPLE_FPS = 5.0          # face samples per second
WINDOW = 1.0              # seconds per speaking-activity window
DOMINANCE = 1.4           # active speaker's mouth variance must beat the other's by this factor
SILENT_VAR = 0.0004       # mouth-ratio variance below this means "not talking"
MIN_HOLD = 1.5            # never show a speaker for less than this many seconds
SPLIT_MIN = 3.0           # back-and-forth must last this long to use the split layout
SPLIT_SIZE_RATIO = 0.65   # both faces must be similar in size for split
SNAP_TOL = 0.75           # move a speaker switch to a sentence end within this distance
MIN_TRACK_PRESENCE = 0.3  # a face track must appear in this share of a shot's samples
MIN_FACE_AREA_RATIO = 0.10
TRACK_DIST_FRAC = 0.15    # max centre jump between samples, as a share of frame width
MIN_SHOT = 0.8

Box = tuple[float, float, float, float]


@dataclass
class Face:
    t: float
    box: Box    # x, y, w, h in source pixels
    mar: float  # mouth aspect ratio: inner-lip gap / mouth width

    @property
    def center(self) -> tuple[float, float]:
        x, y, w, h = self.box
        return x + w / 2, y + h / 2

    @property
    def area(self) -> float:
        return self.box[2] * self.box[3]


@dataclass
class Track:
    faces: list[Face] = field(default_factory=list)

    def median_box(self) -> Box:
        return tuple(statistics.median(f.box[k] for f in self.faces) for k in range(4))  # type: ignore[return-value]

    def median_area(self) -> float:
        _, _, w, h = self.median_box()
        return w * h

    def mar_variance(self, t0: float, t1: float) -> float:
        vals = [f.mar for f in self.faces if t0 <= f.t < t1]
        return statistics.pvariance(vals) if len(vals) >= 2 else 0.0


def even(v: float) -> int:
    n = int(v)
    return n - (n % 2)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(v, hi))


def fill_box(center_x: float, src_w: int, src_h: int) -> list[int]:
    w = even(min(src_w, src_h * 9 / 16))
    h = even(min(src_h, w * 16 / 9))
    x = even(_clamp(center_x - w / 2, 0, src_w - w))
    y = even((src_h - h) / 2)
    return [x, y, w, h]


def split_box(face_box: Box, src_w: int, src_h: int) -> list[int]:
    fx, fy, fw, fh = face_box
    h = min(src_h, fh * 2.6)
    w = h * 9 / 8
    if w > src_w:
        w, h = src_w, src_w * 8 / 9
    w, h = even(w), even(h)
    cx, cy = fx + fw / 2, fy + fh / 2
    x = even(_clamp(cx - w / 2, 0, src_w - w))
    y = even(_clamp(cy - h * 0.45, 0, src_h - h))
    return [x, y, w, h]


def zoom_box(base: list[int], center: tuple[float, float] | None, scale: float) -> list[int]:
    bx, by, bw, bh = base
    w, h = even(bw / scale), even(bh / scale)
    cx, cy = center if center else (bx + bw / 2, by + bh / 2)
    x = even(_clamp(cx - w / 2, bx, bx + bw - w))
    y = even(_clamp(cy - h * 0.4, by, by + bh - h))
    return [x, y, w, h]


def assign_tracks(samples: list[list[Face]], src_w: int) -> list[Track]:
    tracks: list[Track] = []
    max_dist = TRACK_DIST_FRAC * src_w
    for faces in samples:
        used: set[int] = set()
        for face in sorted(faces, key=lambda f: -f.area):
            best, best_d = None, max_dist
            for idx, track in enumerate(tracks):
                if idx in used:
                    continue
                d = math.dist(track.faces[-1].center, face.center)
                if d < best_d:
                    best, best_d = idx, d
            if best is None:
                tracks.append(Track([face]))
                used.add(len(tracks) - 1)
            else:
                tracks[best].faces.append(face)
                used.add(best)
    kept = [t for t in tracks if len(t.faces) >= MIN_TRACK_PRESENCE * max(len(samples), 1)]
    if kept:
        largest = max(t.median_area() for t in kept)
        kept = [t for t in kept if t.median_area() >= MIN_FACE_AREA_RATIO * largest]
    return sorted(kept, key=lambda t: t.median_box()[0])


def _window_labels(pair: list[Track], t0: float, t1: float) -> list[tuple[float, float, str]]:
    labels = []
    t = t0
    while t < t1 - 1e-6:
        e = min(t + WINDOW, t1)
        va, vb = pair[0].mar_variance(t, e), pair[1].mar_variance(t, e)
        a_on, b_on = va > SILENT_VAR, vb > SILENT_VAR
        if a_on and va >= DOMINANCE * vb:
            label = "A"
        elif b_on and vb >= DOMINANCE * va:
            label = "B"
        elif a_on and b_on:
            label = "both"
        else:
            label = "none"
        labels.append((t, e, label))
        t = e
    return labels


def _runs(labels: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    runs: list[tuple[float, float, str]] = []
    for s, e, label in labels:
        if runs and runs[-1][2] == label:
            runs[-1] = (runs[-1][0], e, label)
        else:
            runs.append((s, e, label))
    return runs


def _snap_switches(plan: list[list], sentence_ends: list[float]) -> list[list]:
    for i in range(len(plan) - 1):
        b = plan[i][1]
        near = [t for t in sentence_ends if abs(t - b) <= SNAP_TOL and plan[i][0] < t < plan[i + 1][1]]
        if near:
            nb = min(near, key=lambda t: abs(t - b))
            plan[i][1] = plan[i + 1][0] = nb
    return plan


def _enforce_min_hold(plan: list[list]) -> list[list]:
    out: list[list] = []
    for s, e, who in plan:
        if out and (e - s < MIN_HOLD or out[-1][2] == who):
            out[-1][1] = e
        else:
            out.append([s, e, who])
    if len(out) > 1 and out[0][1] - out[0][0] < MIN_HOLD:
        out[1][0] = out[0][0]
        out.pop(0)
    return out


def _segment(s: float, e: float, who: str, pair: list[Track], src_w: int, src_h: int) -> dict:
    seg: dict = {"start": round(s, 3), "end": round(e, 3), "layout": "fill", "boxes": [], "face": None}
    if who == "fit":
        seg["layout"] = "fit"
    elif who == "split":
        seg["layout"] = "split"
        seg["boxes"] = [split_box(t.median_box(), src_w, src_h) for t in pair]
    else:
        x, y, w, h = (pair[0] if who == "A" else pair[1]).median_box()
        seg["boxes"] = [fill_box(x + w / 2, src_w, src_h)]
        seg["face"] = [round(x), round(y), round(w), round(h)]
    return seg


def plan_shot(t0: float, t1: float, tracks: list[Track], src_w: int, src_h: int,
              sentence_ends: list[float]) -> list[dict]:
    if not tracks:
        return [_segment(t0, t1, "fit", [], src_w, src_h)]
    if len(tracks) == 1:
        return [_segment(t0, t1, "A", tracks, src_w, src_h)]
    pair = sorted(sorted(tracks, key=lambda t: -t.median_area())[:2], key=lambda t: t.median_box()[0])
    areas = [t.median_area() for t in pair]
    can_split = min(areas) >= SPLIT_SIZE_RATIO * max(areas)
    current = "A" if pair[0].mar_variance(t0, t1) >= pair[1].mar_variance(t0, t1) else "B"
    plan: list[list] = []
    for s, e, label in _runs(_window_labels(pair, t0, t1)):
        if label == "both" and can_split and e - s >= SPLIT_MIN:
            who = "split"
        elif label in ("A", "B"):
            who = label
        else:
            who = current
        if plan and plan[-1][2] == who:
            plan[-1][1] = e
        else:
            plan.append([s, e, who])
        current = who
    plan = _enforce_min_hold(_snap_switches(plan, sentence_ends))
    return [_segment(s, e, who, pair, src_w, src_h) for s, e, who in plan]


def merge_short_shots(shots: list[tuple[float, float]], min_len: float = MIN_SHOT) -> list[tuple[float, float]]:
    """Merge short INTERIOR shots into the previous shot. A short first or last shot is a different camera
    angle at the clip edge: it stays its own shot so it is planned (and cropped) from its own footage."""
    out: list[tuple[float, float]] = []
    last = len(shots) - 1
    for i, (s, e) in enumerate(shots):
        if 0 < i < last and e - s < min_len:
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def plan_clip(shots: list[tuple[float, float]], samples: list[tuple[float, list[Face]]],
              src_w: int, src_h: int, sentence_ends: list[float]) -> list[dict]:
    """shots and samples are in clip time (0 = first frame of the finished clip)."""
    segments: list[dict] = []
    for s, e in shots:
        in_shot = [faces for t, faces in samples if s <= t < e]
        tracks = assign_tracks(in_shot, src_w)
        segments += plan_shot(s, e, tracks, src_w, src_h, [t for t in sentence_ends if s < t < e])
    return segments
