"""One ffmpeg pass per clip: crop/zoom, captions, SFX, loudness, encode."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from clipper.captions import build_ass, clean, group_words
from clipper.clips import clip_words, sentence_end_times
from clipper.env import FONTS_DIR, WHOOSH_PATH, ffmpeg_bin
from clipper.fetch import section_window
from clipper.jobs import Job
from clipper.layout import zoom_box
from clipper.zooms import plan_zooms

OUT_W, OUT_H, HALF_H = 1080, 1920, 960
LOUDNORM = "loudnorm=I=-14:TP=-1:LRA=11"
WHOOSH_LEAD = 0.15  # start the whoosh slightly before the cut
STEREO_48K = "aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo"


class RenderError(Exception):
    pass


def split_pieces(segments: list[dict], zooms: list[dict]) -> list[dict]:
    """Cut segments at zoom edges so every piece has exactly one crop."""
    pieces = []
    for seg in segments:
        cuts = {seg["start"], seg["end"]}
        for z in zooms:
            cuts.update(t for t in (z["start"], z["end"]) if seg["start"] < t < seg["end"])
        edges = sorted(cuts)
        for a, b in zip(edges, edges[1:]):
            mid = (a + b) / 2
            zoom = next((z for z in zooms if z["start"] <= mid < z["end"]), None)
            boxes = seg["boxes"]
            if zoom and seg["layout"] == "fill":
                face = seg.get("face")
                center = (face[0] + face[2] / 2, face[1] + face[3] / 2) if face else None
                boxes = [zoom_box(boxes[0], center, zoom["scale"])]
            pieces.append({"start": a, "end": b, "layout": seg["layout"], "boxes": boxes})
    return pieces


def video_graph(pieces: list[dict], fps: int, ass_name: str | None) -> str:
    n = len(pieces)
    chains = [f"[0:v]split={n}" + "".join(f"[v{i}]" for i in range(n))]
    for i, p in enumerate(pieces):
        head = f"[v{i}]trim=start={p['start']:.3f}:end={p['end']:.3f},setpts=PTS-STARTPTS"
        if p["layout"] == "fill":
            x, y, w, h = p["boxes"][0]
            chains.append(f"{head},crop={w}:{h}:{x}:{y},scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1[p{i}]")
        elif p["layout"] == "split":
            (x1, y1, w1, h1), (x2, y2, w2, h2) = p["boxes"]
            chains += [
                f"{head},split[a{i}][b{i}]",
                f"[a{i}]crop={w1}:{h1}:{x1}:{y1},scale={OUT_W}:{HALF_H}:flags=lanczos[t{i}]",
                f"[b{i}]crop={w2}:{h2}:{x2}:{y2},scale={OUT_W}:{HALF_H}:flags=lanczos[u{i}]",
                f"[t{i}][u{i}]vstack,setsar=1[p{i}]",
            ]
        else:  # fit: whole frame over a blurred, filled background
            chains += [
                f"{head},split[a{i}][b{i}]",
                f"[a{i}]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=10:2,"
                f"scale={OUT_W}:{OUT_H}[g{i}]",
                f"[b{i}]scale={OUT_W}:-2[f{i}]",
                f"[g{i}][f{i}]overlay=(W-w)/2:(H-h)/2,setsar=1[p{i}]",
            ]
    tail = "".join(f"[p{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,fps={fps}"
    if ass_name:
        tail += f",ass={ass_name}:fontsdir=fonts"
    chains.append(tail + ",format=yuv420p[vout]")
    return ";".join(chains)


def audio_graph(sfx_times: list[float], gain_db: float, loudnorm: str) -> str:
    if not sfx_times:
        return f"[0:a]{STEREO_48K},{loudnorm},aresample=48000[aout]"
    n = len(sfx_times)
    chains = [f"[0:a]{STEREO_48K}[sp]",
              f"[1:a]{STEREO_48K},volume={gain_db}dB,asplit={n}" + "".join(f"[s{i}]" for i in range(n))]
    chains += [f"[s{i}]adelay=delays={int(round(t * 1000))}:all=1[d{i}]" for i, t in enumerate(sfx_times)]
    chains.append("[sp]" + "".join(f"[d{i}]" for i in range(n))
                  + f"amix=inputs={n + 1}:duration=first:normalize=0,{loudnorm},aresample=48000[aout]")
    return ";".join(chains)


def parse_loudnorm(stderr: str) -> dict:
    blocks = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr)
    if not blocks:
        raise RenderError("loudnorm measurement not found in ffmpeg output")
    return json.loads(blocks[-1])


def loudnorm_pass2(m: dict) -> str:
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if any("inf" in str(m[k]) for k in keys):  # silent audio: fall back to single-pass
        return LOUDNORM
    return (f"{LOUDNORM}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
            f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")


def encode_args(cfg: dict) -> list[str]:
    r = cfg["render"]
    if r["fast"]:
        video = ["-c:v", "h264_videotoolbox", "-q:v", "60", "-profile:v", "high"]
    else:
        video = ["-c:v", "libx264", "-preset", "medium", "-crf", str(r["crf"]), "-profile:v", "high"]
    return video + ["-pix_fmt", "yuv420p", "-r", str(r["fps"]), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-movflags", "+faststart"]


def _input_args(src: Path, offset: float, duration: float, use_sfx: bool) -> list[str]:
    args = ["-ss", f"{offset:.3f}", "-t", f"{duration:.3f}", "-i", str(src)]
    if use_sfx:
        args += ["-i", str(WHOOSH_PATH)]
    return args


def _run(cmd: list[str], cwd: Path, log: Path) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(f"$ {' '.join(cmd)}\n\n{proc.stderr}")
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-10:])
        raise RenderError(f"ffmpeg failed (exit {proc.returncode}), log: {log}\n{tail}")
    return proc


def _link_fonts(render_dir: Path) -> None:
    link = render_dir / "fonts"
    if not link.exists():
        os.symlink(FONTS_DIR, link)


def render_clip(job: Job, clip: dict, cfg: dict, words: list[dict], meta_duration: float | None) -> Path:
    cid = clip["id"]
    segments = job.read_json(job.crops_dir / f"{cid}.json")["segments"]
    duration = clip["duration"]
    section_start, _ = section_window(clip["start"], clip["end"], meta_duration)
    offset = round(clip["start"] - section_start, 3)
    src = job.src_dir / f"{cid}.mp4"

    cw = clip_words(words, clip)
    emphasis = {e.lower() for e in clip.get("emphasis_words", [])}
    anchors = sentence_end_times(cw) + [w["e"] for w in cw if clean(w["w"]).lower() in emphasis]
    zooms = plan_zooms(segments, anchors, duration, cfg)
    pieces = split_pieces(segments, zooms)

    cap = cfg["captions"]
    groups = group_words(cw, cap["max_words"], cap["max_chars"], cap["uppercase"])
    ass_name = f"{cid}.ass"
    build_ass(groups, cfg, segments, clip.get("hook_text"), emphasis).save(str(job.render_dir / ass_name))
    _link_fonts(job.render_dir)

    use_sfx = cfg["sfx"]["enabled"] and bool(zooms) and WHOOSH_PATH.exists()
    sfx_times = [max(0.0, z["start"] - WHOOSH_LEAD) for z in zooms] if use_sfx else []
    inputs = _input_args(src, offset, duration, use_sfx)
    gain = cfg["sfx"]["gain_db"]

    measure_cmd = [ffmpeg_bin(), "-hide_banner", "-nostats", *inputs,
                   "-filter_complex", audio_graph(sfx_times, gain, f"{LOUDNORM}:print_format=json"),
                   "-map", "[aout]", "-f", "null", "-"]
    measured = parse_loudnorm(_run(measure_cmd, job.render_dir, job.logs_dir / f"{cid}_loudnorm.log").stderr)

    out = job.out / f"{cid}.mp4"
    graph = video_graph(pieces, cfg["render"]["fps"], ass_name) + ";" + audio_graph(sfx_times, gain, loudnorm_pass2(measured))
    cmd = [ffmpeg_bin(), "-hide_banner", "-y", *inputs, "-filter_complex", graph,
           "-map", "[vout]", "-map", "[aout]", *encode_args(cfg), "-t", f"{duration:.3f}", str(out)]
    _run(cmd, job.render_dir, job.logs_dir / f"{cid}_render.log")
    return out
