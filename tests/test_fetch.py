import pytest

from clipper.fetch import (SECTION_ENCODE, FetchError, audio_cmd, extract_video_id, parse_meta, section_cmd,
                           section_window)


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ?si=abc",
    "https://www.youtube.com/watch?app=desktop&v=dQw4w9WgXcQ&t=42s",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
    "https://www.youtube.com/live/dQw4w9WgXcQ",
    "dQw4w9WgXcQ",
])
def test_extract_video_id(url):
    assert extract_video_id(url) == "dQw4w9WgXcQ"


def test_extract_video_id_rejects_garbage():
    with pytest.raises(FetchError):
        extract_video_id("https://example.com/nothing")


def test_audio_cmd_is_a_list_and_handles_spaces(tmp_path):
    out_dir = tmp_path / "Content Clipping"
    cmd = audio_cmd("https://youtu.be/dQw4w9WgXcQ", out_dir)
    assert isinstance(cmd, list)
    assert str(out_dir / "audio.%(ext)s") in cmd
    i = cmd.index("--js-runtimes")
    assert cmd[i + 1] == "node"


def test_cookies_flag_only_when_requested(tmp_path):
    assert "--cookies-from-browser" not in audio_cmd("u", tmp_path)
    cmd = audio_cmd("u", tmp_path, cookies_browser="chrome")
    assert cmd[cmd.index("--cookies-from-browser") + 1] == "chrome"


def test_section_cmd_formats_range(tmp_path):
    cmd = section_cmd("u", 10.0, 55.5, tmp_path / "clip_01.mp4")
    assert cmd[cmd.index("--download-sections") + 1] == "*10.000-55.500"
    assert "--force-keyframes-at-cuts" in cmd
    assert cmd[cmd.index("--merge-output-format") + 1] == "mp4"
    assert cmd[cmd.index("--downloader-args") + 1] == SECTION_ENCODE
    assert cmd.index("--downloader-args") < cmd.index("u")


def test_section_window_pads_and_clamps():
    assert section_window(1.0, 30.0, 100.0) == (0.0, 32.0)
    assert section_window(50.0, 99.0, 100.0) == (48.0, 100.0)
    assert section_window(50.0, 60.0, None) == (48.0, 62.0)


def test_parse_meta():
    info = {"id": "dQw4w9WgXcQ", "title": "Ep 1", "channel": "Pod", "uploader_id": "@pod",
            "duration": 3600, "chapters": [{"title": "Intro", "start_time": 0, "end_time": 60}],
            "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    meta = parse_meta(info)
    assert meta["video_id"] == "dQw4w9WgXcQ"
    assert meta["duration"] == 3600.0
    assert meta["channel_handle"] == "@pod"
    assert meta["chapters"] == [{"title": "Intro", "start": 0.0, "end": 60.0}]
