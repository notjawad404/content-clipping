"""Load and validate config/publish.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

from clipper.env import CONFIG_DIR
from clipper.publish import PublishError

DEFAULT_PATH = CONFIG_DIR / "publish.yaml"
REQUIRED = ("clips_repo", "ig_account_id")
DEFAULTS = {"graph_version": "v26.0", "queue_branch": "master", "max_attempts": 3, "poll_interval_s": 10, "poll_timeout_s": 300,
            "youtube": False, "youtube_privacy": "private"}
YOUTUBE_PRIVACY = ("private", "unlisted", "public")
POSITIVE_INT_KEYS = ("max_attempts", "poll_interval_s", "poll_timeout_s")
NON_EMPTY_STR_KEYS = ("clips_repo", "graph_version", "queue_branch")


class PublishConfigError(PublishError):
    pass


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_non_empty_str(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def load_publish_config(path: Path = DEFAULT_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        raise PublishConfigError(f"missing posting config: {path}")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise PublishConfigError(f"{path.name}: could not read ({type(exc).__name__})") from None
    if not isinstance(raw, dict):
        raise PublishConfigError(f"{path.name}: expected a mapping of settings")
    raw = {key: value for key, value in raw.items() if value is not None}
    for key in REQUIRED:
        if not raw.get(key):
            raise PublishConfigError(f"{path.name}: missing required key {key!r}")
    cfg = {**DEFAULTS, **raw}
    for key in POSITIVE_INT_KEYS:
        if not (_is_int(cfg[key]) and cfg[key] > 0):
            raise PublishConfigError(f"{path.name}: {key} must be a positive integer")
    for key in NON_EMPTY_STR_KEYS:
        if not _is_non_empty_str(cfg[key]):
            raise PublishConfigError(f"{path.name}: {key} must be a non-empty string")
    if not isinstance(cfg["youtube"], bool):
        raise PublishConfigError(f"{path.name}: youtube must be true or false")
    if cfg["youtube_privacy"] not in YOUTUBE_PRIVACY:
        raise PublishConfigError(f"{path.name}: youtube_privacy must be one of {', '.join(YOUTUBE_PRIVACY)}")
    account = cfg["ig_account_id"]
    if _is_int(account):
        cfg["ig_account_id"] = str(account)
    elif not _is_non_empty_str(account):
        raise PublishConfigError(f"{path.name}: ig_account_id must be a non-empty string or an integer")
    return cfg
