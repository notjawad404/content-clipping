from pathlib import Path

import pytest

from clipper.config import ConfigError, deep_merge, load_config


def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_deep_merge_nested_and_replace():
    base = {"a": 1, "captions": {"color": "#FFF", "size": 76}, "tags": ["x"]}
    out = deep_merge(base, {"captions": {"color": "#000"}, "tags": ["y"]})
    assert out == {"a": 1, "captions": {"color": "#000", "size": 76}, "tags": ["y"]}
    assert base["captions"]["color"] == "#FFF"  # input not mutated


def test_load_config_precedence(tmp_path):
    write(tmp_path / "style.yaml", "max_clips: 8\ncaptions: {color: '#FFFFFF', size: 76}\n")
    write(tmp_path / "campaigns" / "acme.yaml", "max_clips: 5\ncaptions: {color: '#00E5FF'}\n")
    overrides = write(tmp_path / "overrides.yaml", "max_clips: 3\n")
    cfg = load_config("acme", overrides, config_dir=tmp_path)
    assert cfg["max_clips"] == 3
    assert cfg["captions"] == {"color": "#00E5FF", "size": 76}
    assert cfg["campaign"] == "acme"


def test_missing_overrides_file_is_ignored(tmp_path):
    write(tmp_path / "style.yaml", "max_clips: 8\n")
    assert load_config(None, tmp_path / "nope.yaml", config_dir=tmp_path)["max_clips"] == 8


def test_unknown_campaign_raises(tmp_path):
    write(tmp_path / "style.yaml", "max_clips: 8\n")
    with pytest.raises(ConfigError, match="Unknown campaign"):
        load_config("nope", config_dir=tmp_path)


def test_repo_style_yaml_loads():
    cfg = load_config()
    assert cfg["length"]["max"] == 90
    assert cfg["captions"]["max_chars"] == 15
