"""Load and validate config/publish.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

from clipper.env import CONFIG_DIR
from clipper.publish import PublishError

DEFAULT_PATH = CONFIG_DIR / "publish.yaml"
REQUIRED = ("clips_repo",)
DEFAULTS = {"graph_version": "v26.0", "queue_branch": "master", "max_attempts": 3, "poll_interval_s": 10, "poll_timeout_s": 300,
            "youtube": False, "youtube_privacy": "private", "tiktok": False, "tiktok_privacy": "SELF_ONLY",
            "tiktok_mode": "draft", "tiktok_keep_days": 7, "instagram_backlog": [],
            "publer": False, "publer_accounts": [], "publer_mode": "publish"}
YOUTUBE_PRIVACY = ("private", "unlisted", "public")
TIKTOK_PRIVACY = ("SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE")
POSITIVE_INT_KEYS = ("max_attempts", "poll_interval_s", "poll_timeout_s", "tiktok_keep_days")
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
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
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
    for key in ("youtube", "tiktok", "publer"):
        if not isinstance(cfg[key], bool):
            raise PublishConfigError(f"{path.name}: {key} must be true or false")
    if cfg["youtube_privacy"] not in YOUTUBE_PRIVACY:
        raise PublishConfigError(f"{path.name}: youtube_privacy must be one of {', '.join(YOUTUBE_PRIVACY)}")
    if cfg["tiktok_mode"] not in ("manual", "draft", "direct"):
        raise PublishConfigError(f"{path.name}: tiktok_mode must be manual, draft or direct")
    if cfg["tiktok_privacy"] not in TIKTOK_PRIVACY:
        raise PublishConfigError(f"{path.name}: tiktok_privacy must be one of {', '.join(TIKTOK_PRIVACY)}")
    if cfg["publer_mode"] not in ("publish", "draft"):
        raise PublishConfigError(f"{path.name}: publer_mode must be publish or draft")
    accounts = cfg["publer_accounts"]
    if not isinstance(accounts, list) or not all(_is_non_empty_str(a) or _is_int(a) for a in accounts):
        raise PublishConfigError(f"{path.name}: publer_accounts must be a list of Publer account ids")
    cfg["publer_accounts"] = [str(a) for a in accounts]
    if cfg["publer"] and not cfg["publer_accounts"]:
        raise PublishConfigError(f"{path.name}: publer is on but publer_accounts is empty")
    account = cfg.get("ig_account_id")
    if account is None:
        cfg["ig_account_id"] = None
    elif _is_int(account):
        cfg["ig_account_id"] = str(account)
    elif not _is_non_empty_str(account):
        raise PublishConfigError(f"{path.name}: ig_account_id must be a non-empty string or an integer")
    backlog = cfg["instagram_backlog"]
    if not isinstance(backlog, list) or not all(_is_non_empty_str(v) for v in backlog):
        raise PublishConfigError(f"{path.name}: instagram_backlog must be a list of video ids")
    if cfg["ig_account_id"] is None and not cfg["youtube"] and not cfg["tiktok"] and not cfg["publer"]:
        raise PublishConfigError(f"{path.name}: no platform enabled; set ig_account_id, youtube, tiktok or publer")
    return cfg
