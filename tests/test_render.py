import json
import subprocess
from pathlib import Path

import pytest

from clipper import render
from clipper.config import load_config
from clipper.env import ffmpeg_bin, ffprobe_bin
from clipper.jobs import job_for
from clipper.render import (audio_graph, encode_args, loudnorm_pass2, parse_loudnorm, split_pieces,
                            video_graph)

FILL = {"start": 0.0, "end": 10.0, "layout": "fill", "boxes": [[196, 2, 606, 1076]], "face": [400, 300, 200, 200]}


def test_split_pieces_cuts_at_zoom_edges():
    pieces = split_pieces([FILL], [{"start": 4.0, "end": 8.0, "scale": 1.18}])
    assert [(p["start"], p["end"]) for p in pieces] == [(0.0, 4.0), (4.0, 8.0), (8.0, 10.0)]
    assert pieces[0]["boxes"] == FILL["boxes"] and pieces[2]["boxes"] == FILL["boxes"]
    assert pieces[1]["boxes"][0][2:] == [512, 910]   # zoomed crop is smaller


def test_video_graph_branches_and_captions():
    split = {"start": 10.0, "end": 14.0, "layout": "split", "boxes": [[208, 166, 584, 520], [1108, 166, 584, 520]]}
    fit = {"start": 14.0, "end": 16.0, "layout": "fit", "boxes": []}
    g = video_graph([FILL, split, fit], 30, "clip_01.ass")
    assert g.startswith("[0:v]split=3[v0][v1][v2];")
    assert "[v0]trim=start=0.000:end=10.000,setpts=PTS-STARTPTS,crop=606:1076:196:2,scale=1080:1920" in g
    assert "vstack" in g and "boxblur" in g
    assert g.endswith("[p0][p1][p2]concat=n=3:v=1:a=0,fps=30,ass=clip_01.ass:fontsdir=fonts,format=yuv420p[vout]")


def test_audio_graph_without_and_with_sfx():
    assert audio_graph([], -18, "LN").endswith(",LN,aresample=48000[aout]")
    g = audio_graph([3.85, 11.0], -18, "LN")
    assert "volume=-18dB,asplit=2[s0][s1]" in g
    assert "[s0]adelay=delays=3850:all=1[d0]" in g
    assert "[sp][d0][d1]amix=inputs=3:duration=first:normalize=0,LN,aresample=48000[aout]" in g


def test_parse_loudnorm_and_pass2():
    stderr = ('junk\n[Parsed_loudnorm_0 @ 0x1]\n{\n\t"input_i" : "-23.50",\n\t"input_tp" : "-4.10",\n'
              '\t"input_lra" : "6.30",\n\t"input_thresh" : "-34.00",\n\t"target_offset" : "0.20"\n}\n')
    s = loudnorm_pass2(parse_loudnorm(stderr))
    assert s.startswith("loudnorm=I=-14:TP=-1:LRA=11:measured_I=-23.50")
    assert "offset=0.20" in s and s.endswith("linear=true")


def test_loudnorm_pass2_falls_back_on_silence():
    m = {"input_i": "-inf", "input_tp": "-inf", "input_lra": "0.00", "input_thresh": "-inf", "target_offset": "inf"}
    assert loudnorm_pass2(m) == "loudnorm=I=-14:TP=-1:LRA=11"


def test_encode_args_quality_and_fast_modes():
    cfg = load_config()
    args = encode_args(cfg)
    assert args[args.index("-c:v") + 1] == "libx264" and args[args.index("-crf") + 1] == "18"
    assert "+faststart" in args
    cfg["render"]["fast"] = True
    assert "h264_videotoolbox" in encode_args(cfg)


def test_failed_final_pass_leaves_no_output_file(tmp_path, monkeypatch):
    job = job_for("vid", jobs_dir=tmp_path / "jobs", output_dir=tmp_path / "out")
    job.ensure_dirs()
    clip = {"id": "clip_01", "start": 2.0, "end": 10.0, "duration": 8.0, "first_word": 0, "last_word": 1,
            "hook_text": "Hook", "emphasis_words": []}
    words = [{"i": 0, "w": "Make", "s": 2.2, "e": 2.5}, {"i": 1, "w": "money.", "s": 2.6, "e": 3.0}]
    job.write_json(job.crops_dir / "clip_01.json", {"clip_id": "clip_01", "segments": [FILL | {"end": 8.0}]})
    loudnorm = ('{"input_i": "-23.0", "input_tp": "-4.0", "input_lra": "6.0", '
                '"input_thresh": "-34.0", "target_offset": "0.2"}')
    calls = []

    def fake_run(cmd, cwd, log):
        calls.append(cmd)
        if len(calls) == 1:  # loudnorm measurement
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr=f"noise\n{loudnorm}\n")
        Path(cmd[-1]).write_bytes(b"half an mp4")  # ffmpeg had started writing, then died
        raise render.RenderError("ffmpeg failed (exit 1)")

    monkeypatch.setattr(render, "_run", fake_run)
    with pytest.raises(render.RenderError):
        render.render_clip(job, clip, load_config(), words, meta_duration=100.0)
    assert len(calls) == 2
    assert not (job.out / "clip_01.mp4").exists() and not (job.out / "clip_01.partial.mp4").exists()


@pytest.mark.integration
def test_render_clip_synthetic(tmp_path):
    job = job_for("synthetic", jobs_dir=tmp_path / "jobs", output_dir=tmp_path / "out")
    job.ensure_dirs()
    src = job.src_dir / "clip_01.mp4"
    subprocess.run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=12",
                    "-f", "lavfi", "-i", "sine=frequency=220:duration=12",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)], check=True)
    clip = {"id": "clip_01", "start": 2.0, "end": 10.0, "duration": 8.0, "first_word": 0, "last_word": 3,
            "hook_text": "Test hook", "emphasis_words": ["million"]}
    words = [{"i": 0, "w": "Make", "s": 2.2, "e": 2.5}, {"i": 1, "w": "a", "s": 2.6, "e": 2.7},
             {"i": 2, "w": "million", "s": 2.8, "e": 3.3}, {"i": 3, "w": "dollars.", "s": 3.4, "e": 4.0}]
    job.write_json(job.crops_dir / "clip_01.json", {
        "clip_id": "clip_01", "src_w": 1920, "src_h": 1080, "offset": 2.0,
        "segments": [{"start": 0.0, "end": 5.0, "layout": "fill", "boxes": [[656, 2, 606, 1076]], "face": [860, 300, 200, 200]},
                     {"start": 5.0, "end": 8.0, "layout": "fit", "boxes": [], "face": None}]})
    cfg = load_config()
    cfg["zoom"]["min_gap"] = 1.0  # make sure a zoom (and whoosh) happens in this short clip
    out = render.render_clip(job, clip, cfg, words, meta_duration=12.0)
    probe = subprocess.run([ffprobe_bin(), "-v", "error", "-show_entries", "stream=codec_type,width,height",
                            "-show_entries", "format=duration", "-of", "json", str(out)],
                           capture_output=True, text=True, check=True)
    info = json.loads(probe.stdout)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert abs(float(info["format"]["duration"]) - 8.0) < 0.2
    assert any(s["codec_type"] == "audio" for s in info["streams"])
