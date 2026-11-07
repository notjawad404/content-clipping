"""Load and validate config/publish.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

from clipper.env import CONFIG_DIR
from clipper.publish import PublishError

DEFAULT_PATH = CONFIG_DIR / "publish.yaml"
REQUIRED = ("clips_repo", "ig_account_id")
DEFAULTS = {"graph_version": "v26.0", "max_attempts": 3, "poll_interval_s": 10, "poll_timeout_s": 300}


class PublishConfigError(PublishError):
    pass


def load_publish_config(path: Path = DEFAULT_PATH) -> dict:
    if not Path(path).exists():
        raise PublishConfigError(f"missing posting config: {path}")
    raw = yaml.safe_load(Path(path).read_text()) or {}
    for key in REQUIRED:
        if not raw.get(key):
            raise PublishConfigError(f"{path.name}: missing required key {key!r}")
    cfg = {**DEFAULTS, **raw}
    cfg["ig_account_id"] = str(cfg["ig_account_id"])
    return cfg
