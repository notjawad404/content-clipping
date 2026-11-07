import pytest

from clipper.publish.config import PublishConfigError, load_publish_config


def write(tmp_path, text):
    path = tmp_path / "publish.yaml"
    path.write_text(text)
    return path


def test_defaults_are_applied(tmp_path):
    cfg = load_publish_config(write(tmp_path, 'clips_repo: me/clips\nig_account_id: "123"\n'))
    assert cfg == {"clips_repo": "me/clips", "ig_account_id": "123", "graph_version": "v26.0",
                   "max_attempts": 3, "poll_interval_s": 10, "poll_timeout_s": 300}


def test_account_id_written_as_a_number_becomes_a_string(tmp_path):
    cfg = load_publish_config(write(tmp_path, "clips_repo: me/clips\nig_account_id: 123\n"))
    assert cfg["ig_account_id"] == "123"


def test_missing_required_key_names_the_key(tmp_path):
    with pytest.raises(PublishConfigError, match="ig_account_id"):
        load_publish_config(write(tmp_path, "clips_repo: me/clips\n"))


def test_the_shipped_config_is_valid():
    cfg = load_publish_config()
    assert cfg["clips_repo"] == "hammadalive7/content-clips"
    assert cfg["ig_account_id"] == "17841438716134897"
