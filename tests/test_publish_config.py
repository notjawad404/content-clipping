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


def test_malformed_yaml_raises_config_error(tmp_path):
    with pytest.raises(PublishConfigError, match="could not read"):
        load_publish_config(write(tmp_path, "clips_repo: [unclosed\n"))


def test_directory_path_raises_config_error(tmp_path):
    with pytest.raises(PublishConfigError, match="could not read"):
        load_publish_config(tmp_path)


def test_yaml_that_is_not_a_mapping_raises_config_error(tmp_path):
    with pytest.raises(PublishConfigError, match="expected a mapping"):
        load_publish_config(write(tmp_path, "- clips_repo\n- ig_account_id\n"))


def test_null_value_keeps_the_default(tmp_path):
    cfg = load_publish_config(write(tmp_path, 'clips_repo: me/clips\nig_account_id: "1"\nmax_attempts:\n'))
    assert cfg["max_attempts"] == 3


def test_null_required_key_is_reported_as_missing(tmp_path):
    with pytest.raises(PublishConfigError, match="missing required key 'clips_repo'"):
        load_publish_config(write(tmp_path, 'clips_repo:\nig_account_id: "1"\n'))


@pytest.mark.parametrize("line", [
    "max_attempts: three",
    "max_attempts: -1",
    "max_attempts: 0",
    "max_attempts: true",
    "poll_interval_s: 1.5",
    "poll_timeout_s: false",
])
def test_invalid_numeric_setting_names_the_key(tmp_path, line):
    key = line.split(":")[0]
    text = f'clips_repo: me/clips\nig_account_id: "1"\n{line}\n'
    with pytest.raises(PublishConfigError, match=key):
        load_publish_config(write(tmp_path, text))


@pytest.mark.parametrize("line, key", [
    ("clips_repo: [1]", "clips_repo"),
    ('graph_version: ""', "graph_version"),
    ("ig_account_id: [1]", "ig_account_id"),
    ("ig_account_id: true", "ig_account_id"),
])
def test_invalid_string_setting_names_the_key(tmp_path, line, key):
    base = {"clips_repo": "me/clips", "ig_account_id": "1"}
    lines = [f"{k}: {v}" for k, v in base.items() if not line.startswith(k + ":")] + [line]
    with pytest.raises(PublishConfigError, match=key):
        load_publish_config(write(tmp_path, "\n".join(lines) + "\n"))


def test_string_path_is_accepted(tmp_path):
    path = write(tmp_path, 'clips_repo: me/clips\nig_account_id: "123"\n')
    assert load_publish_config(str(path))["ig_account_id"] == "123"
