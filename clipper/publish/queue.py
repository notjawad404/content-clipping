"""File-based clip queue: one JSON file per clip in queue/{pending,posted,failed}/."""
from __future__ import annotations

import json
from pathlib import Path

from clipper.env import PROJECT_ROOT
from clipper.publish import PublishError

STATES = ("pending", "posted", "failed")
QUEUE_ROOT = PROJECT_ROOT / "queue"


class QueueError(PublishError):
    pass


def new_platform_state() -> dict:
    return {"video_id": None, "url": None, "attempts": 0, "last_error": None}


new_youtube_state = new_platform_state


def new_entry(*, video_id: str, clip_id: str, campaign: str | None, caption: str, asset_url: str,
              asset_id: int, queued_at: str, title: str | None = None,
              youtube_description: str | None = None, tiktok_caption: str | None = None,
              youtube_tags: list[str] | None = None) -> dict:
    return {"id": f"{video_id}_{clip_id}", "video_id": video_id, "campaign": campaign, "caption": caption,
            "title": title, "youtube_description": youtube_description, "tiktok_caption": tiktok_caption,
            "youtube_tags": youtube_tags or [],
            "asset_url": asset_url, "asset_id": asset_id, "queued_at": queued_at, "attempts": 0,
            "last_error": None, "container_id": None, "media_id": None, "permalink": None,
            "youtube": new_platform_state()}


def _dir(root: Path, state: str) -> Path:
    if state not in STATES:
        raise QueueError(f"unknown queue state {state!r}; expected one of {STATES}")
    return root / state


def path_for(root: Path, state: str, entry_id: str) -> Path:
    return _dir(root, state) / f"{entry_id}.json"


def save(root: Path, state: str, entry: dict) -> None:
    directory = _dir(root, state)
    directory.mkdir(parents=True, exist_ok=True)
    path_for(root, state, entry["id"]).write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8", newline="\n")


def load_all(root: Path, state: str) -> list[dict]:
    directory = _dir(root, state)
    if not directory.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]


def exists_anywhere(root: Path, entry_id: str) -> bool:
    return any(path_for(root, state, entry_id).exists() for state in STATES)


def next_pending(root: Path) -> dict | None:
    return min(load_all(root, "pending"), key=lambda e: (e["queued_at"], e["id"]), default=None)


def move(root: Path, entry: dict, from_state: str, to_state: str) -> None:
    save(root, to_state, entry)
    source = path_for(root, from_state, entry["id"])
    if source.exists():
        source.unlink()
