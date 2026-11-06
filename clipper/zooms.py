"""Decide when hard-cut punch-in zooms happen. Pure functions."""
from __future__ import annotations


def toggle_times(anchors: list[float], duration: float, min_gap: float, max_gap: float) -> list[float]:
    """Times where the zoom state flips (in, out, in, ...). Prefer anchors (sentence ends, emphasis words)."""
    toggles: list[float] = []
    last = 0.0
    pending = sorted(a for a in anchors if 0 < a < duration - 1.0)
    while True:
        candidates = [a for a in pending if min_gap <= a - last <= max_gap]
        if candidates:
            t = candidates[0]
        elif last + max_gap < duration - 1.0:
            t = last + max_gap
        else:
            break
        toggles.append(round(t, 3))
        last = t
    return toggles


def plan_zooms(segments: list[dict], anchors: list[float], duration: float, cfg: dict) -> list[dict]:
    zc = cfg["zoom"]
    if not zc["enabled"]:
        return []
    toggles = toggle_times(anchors, duration, zc["min_gap"], zc["max_gap"])
    zooms = []
    for i in range(0, len(toggles), 2):
        start = toggles[i]
        end = toggles[i + 1] if i + 1 < len(toggles) else duration
        seg = next((s for s in segments if s["start"] <= start < s["end"]), None)
        if seg is None or seg["layout"] != "fill":
            continue
        end = min(end, seg["end"])
        if end - start >= 0.5:
            zooms.append({"start": start, "end": round(end, 3), "scale": zc["scale"]})
    return zooms
