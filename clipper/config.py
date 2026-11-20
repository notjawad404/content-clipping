"""Load style defaults, a campaign file and run overrides into one dict."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from clipper.env import CONFIG_DIR


class ConfigError(Exception):
    pass


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict: nested dicts merge, any other value in `override` replaces."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def load_config(
    campaign: str | None = None,
    overrides_path: Path | None = None,
    config_dir: Path = CONFIG_DIR,
) -> dict[str, Any]:
    cfg = _read_yaml(config_dir / "style.yaml")
    if campaign:
        campaign_path = config_dir / "campaigns" / f"{campaign}.yaml"
        if not campaign_path.exists():
            raise ConfigError(f"Unknown campaign '{campaign}': {campaign_path} not found")
        cfg = deep_merge(cfg, _read_yaml(campaign_path))
        cfg["campaign"] = campaign
    if overrides_path is not None and overrides_path.exists():
        cfg = deep_merge(cfg, _read_yaml(overrides_path))
    return cfg
