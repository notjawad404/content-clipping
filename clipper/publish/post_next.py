"""Post the oldest queued clip as an Instagram Reel. Runs in GitHub Actions: stdlib + pyyaml only."""
from __future__ import annotations

import argparse
import http.client
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from clipper.publish import PublishError, clips_repo, gitops, queue
from clipper.publish.config import load_publish_config
from clipper.publish.instagram import IgError, InstagramClient, QuotaExceeded, TokenInvalid
from clipper.publish.youtube import QuotaExceeded as YtQuotaExceeded
from clipper.publish.youtube import TokenInvalid as YtTokenInvalid
from clipper.publish.youtube import YouTubeClient, YtError

DUPLICATE_WINDOW = timedelta(hours=24)
SHORTS_TAG = "#Shorts"
YT_ENV = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")


def _short(caption: str) -> str:
    return caption[:40] + ("…" if len(caption) > 40 else "")


MANUAL_CHECK_ERROR = "container already PUBLISHED; media id unknown, check the Instagram profile"


class _NotTheClipsFault(Exception):
    """An Instagram error before any container work (quota check, early duplicate check): never an attempt."""


def _outside_the_clip(call, *args):
    try:
        return call(*args)
    except (TokenInvalid, QuotaExceeded):
        raise
    except IgError as exc:
        raise _NotTheClipsFault(str(exc)) from None


class _AlreadyPublished(Exception):
    """The retry's container was already published, but its media id was never committed."""


def _container_status(client, container_id: str, log: Callable[[str], None]) -> str | None:
    """The container's status, or None (logged) when the status call failed."""
    try:
        return client.container_status(container_id)
    except TokenInvalid:
        raise
    except IgError as exc:
        log(f"container {container_id}: status call failed ({type(exc).__name__}); creating a new container")
        return None


def _container_usable(status: str | None, container_id: str, log: Callable[[str], None]) -> bool:
    if status in ("IN_PROGRESS", "FINISHED"):
        return True
    if status is not None:
        log(f"container {container_id} has status {status}; creating a new container")
    return False


def _normalized(caption) -> str:
    return str(caption or "").replace("\r\n", "\n").strip()


def _recent_duplicate(client, caption: str, now: datetime) -> dict | None:
    wanted = _normalized(caption)
    for item in client.recent_media(5):
        if _normalized(item.get("caption")) != wanted:
            continue
        try:
            created = datetime.strptime(item["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        except (KeyError, TypeError, ValueError):
            continue
        if now - created <= DUPLICATE_WINDOW:
            return item
    return None


def _record_duplicate(root: Path, entry: dict, duplicate: dict, commit: Callable[[str], object],
                      log: Callable[[str], None]) -> None:
    log("found an identical recent post; recording it instead of publishing again")
    entry["media_id"] = str(duplicate["id"])
    entry["permalink"] = duplicate.get("permalink")
    queue.save(root, "pending", entry)
    commit(f"queue: published {entry['id']}")


def _publish(root: Path, client, cfg: dict, entry: dict, dry_run: bool, commit: Callable[[str], object],
             now: datetime, log: Callable[[str], None]) -> bool:
    """Create/reuse the container and publish. Returns False for a dry run (nothing published)."""
    is_retry = bool(entry.get("container_id"))
    if is_retry and not dry_run:
        # A previous run may have published and then failed to commit: look before touching any container.
        duplicate = _outside_the_clip(_recent_duplicate, client, entry["caption"], now)
        if duplicate:
            _record_duplicate(root, entry, duplicate, commit, log)
            return True
    container = entry.get("container_id")
    if container:
        status = _container_status(client, container, log)
        if status == "PUBLISHED":
            # Already posted; only the media id commit was lost. Never create or publish another one.
            raise _AlreadyPublished()
        if not _container_usable(status, container, log):
            container = None
    if not container:
        container = client.create_reel_container(entry["asset_url"], entry["caption"])
        if not dry_run:
            entry["container_id"] = container
            queue.save(root, "pending", entry)
            commit(f"queue: container for {entry['id']}")
    client.wait_until_finished(container, cfg["poll_interval_s"], cfg["poll_timeout_s"])
    if dry_run:
        log("dry run: container FINISHED; not publishing")
        return False
    # Second chance: a post may have appeared while the container was processing.
    duplicate = _recent_duplicate(client, entry["caption"], now) if is_retry else None
    if duplicate:
        _record_duplicate(root, entry, duplicate, commit, log)
        return True
    entry["media_id"] = client.publish(container)
    try:
        entry["permalink"] = client.permalink(entry["media_id"])
    except IgError:
        entry["permalink"] = None
    queue.save(root, "pending", entry)
    commit(f"queue: published {entry['id']}")
    return True


def _needs_manual_check(root: Path, entry: dict, commit: Callable[[str], object],
                        log: Callable[[str], None], dry_run: bool) -> int:
    log(f"{entry['id']}: {MANUAL_CHECK_ERROR}")
    if dry_run:
        return 1
    entry["last_error"] = MANUAL_CHECK_ERROR
    try:
        queue.move(root, entry, "pending", "failed")
        commit(f"queue: needs a manual check: {entry['id']}")
    except (PublishError, OSError) as exc:
        log(f"error: could not record the manual-check state: {exc}")
    return 1


def _finalize(root: Path, entry: dict, delete_asset: Callable[[int], object],
              commit: Callable[[str], object], log: Callable[[str], None]) -> None:
    queue.move(root, entry, "pending", "posted")
    if entry.get("asset_id") is not None:
        try:
            delete_asset(entry["asset_id"])
        except PublishError as exc:
            log(f"warning: could not delete the release asset: {exc}")
    commit(f"queue: posted {entry['id']}")
    links = [entry.get("permalink") or entry.get("media_id")]
    youtube_url = (entry.get("youtube") or {}).get("url")
    if youtube_url:
        links.append(f"YouTube: {youtube_url}")
    log(f"posted {entry['id']}: {' | '.join(link for link in links if link)}")


def _record_failure(root: Path, entry: dict, exc: Exception, cfg: dict, commit: Callable[[str], object],
                    log: Callable[[str], None], dry_run: bool, keep_open: bool = False) -> int:
    """`keep_open`: YouTube still needs this entry, so an exhausted Instagram attempt count must not move it."""
    if dry_run:
        log(f"dry run failed: {exc}")
        return 1
    entry["attempts"] += 1
    entry["last_error"] = str(exc)
    state = "pending"
    if entry["attempts"] >= cfg["max_attempts"] and not keep_open:
        queue.move(root, entry, "pending", "failed")
        state = "failed"
    else:
        queue.save(root, "pending", entry)
    log(f"error: {exc} (attempt {entry['attempts']}/{cfg['max_attempts']}; entry is now {state})")
    try:
        commit(f"queue: attempt {entry['attempts']} failed for {entry['id']}")
    except PublishError as commit_exc:
        log(f"error: could not commit the failure record: {commit_exc}")
    return 1


def _is_stale_duplicate(root: Path, entry: dict) -> bool:
    return any(queue.path_for(root, state, entry["id"]).exists() for state in ("posted", "failed"))


def _remove_stale_duplicate(root: Path, entry: dict, commit: Callable[[str], object],
                            log: Callable[[str], None], dry_run: bool) -> int:
    """A pending file for an id already in posted/ or failed/ (e.g. a stale branch was merged): drop only it."""
    log(f"stale duplicate of {entry['id']} already in posted/failed; removing the pending copy")
    if dry_run:
        return 0
    try:
        queue.path_for(root, "pending", entry["id"]).unlink(missing_ok=True)
        commit(f"queue: remove stale duplicate {entry['id']}")
    except (PublishError, OSError) as exc:
        log(f"error: could not remove the stale duplicate: {exc}")
        return 1
    return 0


def _instagram(root: Path, client, cfg: dict, entry: dict, delete_asset: Callable[[int], object], dry_run: bool,
               commit: Callable[[str], object], now: datetime, log: Callable[[str], None], *,
               finalize: bool = True, keep_open: bool = False) -> int:
    """The Instagram half. With finalize=False the entry stays pending after a success, for the YouTube half."""
    try:
        if entry.get("media_id"):
            if dry_run:
                log("dry run: entry is already published; nothing to check")
                return 0
            log("already published on an earlier run; finishing cleanup")
        else:
            used, total = _outside_the_clip(client.publishing_limit)
            if used >= total:
                log(f"publishing quota reached ({used}/{total}); will retry on the next run")
                return 0
            if not _publish(root, client, cfg, entry, dry_run, commit, now, log):
                return 0
        if finalize:
            _finalize(root, entry, delete_asset, commit, log)
    except _NotTheClipsFault as exc:
        log(f"error: {exc}")
        return 1
    except _AlreadyPublished:
        return _needs_manual_check(root, entry, commit, log, dry_run)
    except TokenInvalid as exc:
        log(f"error: Instagram rejected the access token ({exc}). "
            "Generate a new one and update the IG_ACCESS_TOKEN secret.")
        return 1
    except QuotaExceeded:
        log("publishing quota reached; will retry on the next run")
        return 0
    except IgError as exc:
        return _record_failure(root, entry, exc, cfg, commit, log, dry_run, keep_open)
    except (PublishError, OSError) as exc:
        # Not an Instagram failure (git, queue files): never counts as an attempt.
        if entry.get("media_id"):
            log(f"error: {exc}; the clip is published (media id {entry['media_id']}) "
                "but the queue update was not completed")
        else:
            log(f"error: {exc}")
        return 1
    return 0


class DownloadError(PublishError):
    pass


class YouTubePoster:
    """Downloads a queued clip's Release asset and uploads it to YouTube. The queue never touches the client."""

    def __init__(self, client: YouTubeClient, privacy: str,
                 fetch: Callable[[str], bytes] | None = None):
        self._client = client
        self._privacy = privacy
        self._fetch = fetch or self._download

    @staticmethod
    def _download(url: str) -> bytes:
        try:
            with urllib.request.urlopen(url, timeout=300) as response:
                return response.read()
        except (OSError, http.client.HTTPException) as exc:
            raise DownloadError(f"could not download the clip: {type(exc).__name__}") from None

    def check(self) -> None:
        self._client.access_token()

    def post(self, entry: dict) -> tuple[str, str]:
        title = entry.get("title") or str(entry["caption"]).splitlines()[0][:90]
        if len(title) + len(SHORTS_TAG) + 1 <= 100:
            title = f"{title} {SHORTS_TAG}"
        description = entry.get("youtube_description") or entry["caption"]
        if SHORTS_TAG.lower() not in description.lower():
            description = f"{description}\n\n{SHORTS_TAG}"
        video_id = self._client.upload(self._fetch(entry["asset_url"]), title, description,
                                       privacy=self._privacy)
        return video_id, f"https://www.youtube.com/shorts/{video_id}"


def _youtube(root: Path, entry: dict, cfg: dict, poster, dry_run: bool, commit: Callable[[str], object],
             log: Callable[[str], None]) -> int:
    state = entry["youtube"]
    if state["video_id"] or state["attempts"] >= cfg["max_attempts"]:
        return 0
    try:
        if dry_run:
            poster.check()
            log("dry run: YouTube token refreshed; not uploading")
            return 0
        video_id, url = poster.post(entry)
    except YtTokenInvalid as exc:
        log(f"error: YouTube rejected the credentials ({exc}). Generate a new refresh token with "
            "scripts/yt_auth.py and update the YT_REFRESH_TOKEN secret.")
        return 1
    except YtQuotaExceeded:
        log("YouTube upload quota reached; will retry on the next run")
        return 0
    except YtError as exc:
        if dry_run:
            log(f"dry run failed: {exc}")
            return 1
        state["attempts"] += 1
        state["last_error"] = str(exc)
        queue.save(root, "pending", entry)
        log(f"error: YouTube: {exc} (attempt {state['attempts']}/{cfg['max_attempts']})")
        try:
            commit(f"queue: youtube attempt {state['attempts']} failed for {entry['id']}")
        except PublishError as commit_exc:
            log(f"error: could not commit the failure record: {commit_exc}")
        return 1
    except (PublishError, OSError) as exc:
        log(f"error: YouTube: {exc}")  # download/queue problems are not YouTube's fault: no attempt counted
        return 1
    state.update(video_id=video_id, url=url, last_error=None)
    try:
        queue.save(root, "pending", entry)
        commit(f"queue: youtube published {entry['id']}")
    except (PublishError, OSError) as exc:
        log(f"error: {exc}; the clip is on YouTube ({url}) but the queue update was not completed")
        return 1
    return 0


def _settle(root: Path, entry: dict, cfg: dict, delete_asset: Callable[[int], object],
            commit: Callable[[str], object], log: Callable[[str], None]) -> None:
    """Close the entry once no platform can still be retried."""
    limit = cfg["max_attempts"]
    done_ig, done_yt = bool(entry.get("media_id")), bool(entry["youtube"]["video_id"])
    if (not done_ig and entry["attempts"] < limit) or (not done_yt and entry["youtube"]["attempts"] < limit):
        return
    if done_ig or done_yt:
        _finalize(root, entry, delete_asset, commit, log)
        return
    queue.move(root, entry, "pending", "failed")
    commit(f"queue: failed {entry['id']}")
    log(f"{entry['id']}: every platform ran out of attempts; entry is now failed")


def _post_both(root: Path, client, cfg: dict, entry: dict, delete_asset: Callable[[int], object], poster,
               dry_run: bool, commit: Callable[[str], object], now: datetime, log: Callable[[str], None]) -> int:
    limit = cfg["max_attempts"]
    entry.setdefault("youtube", queue.new_youtube_state())
    youtube_open = not entry["youtube"]["video_id"] and entry["youtube"]["attempts"] < limit
    code = 0
    if not entry.get("media_id") and entry["attempts"] < limit:
        code = _instagram(root, client, cfg, entry, delete_asset, dry_run, commit, now, log,
                          finalize=False, keep_open=youtube_open)
    elif entry.get("media_id"):
        log("already published on Instagram; only YouTube is left")
    if not queue.path_for(root, "pending", entry["id"]).exists():
        return code  # Instagram moved it (needs a manual check); nothing more to do automatically
    try:
        code = max(code, _youtube(root, entry, cfg, poster, dry_run, commit, log))
        if not dry_run:
            _settle(root, entry, cfg, delete_asset, commit, log)
    except (PublishError, OSError) as exc:
        log(f"error: {exc}")
        return 1
    return code


def post_next(root: Path, client, cfg: dict, delete_asset: Callable[[int], object], *, dry_run: bool = False,
              commit: Callable[[str], object] | None = None, now: datetime | None = None,
              log: Callable[[str], None] = print, youtube: YouTubePoster | None = None) -> int:
    commit = commit or (lambda message: None)
    now = now or datetime.now(timezone.utc)
    try:
        entry = queue.next_pending(root)
    except (PublishError, OSError, ValueError) as exc:
        log(f"error: could not read the queue: {exc}")
        return 1
    if entry is None:
        log("nothing to post: the queue is empty")
        return 0
    if _is_stale_duplicate(root, entry):
        return _remove_stale_duplicate(root, entry, commit, log, dry_run)
    log(f"next: {entry['id']} ({_short(entry['caption'])})")
    if youtube is not None:
        return _post_both(root, client, cfg, entry, delete_asset, youtube, dry_run, commit, now, log)
    return _instagram(root, client, cfg, entry, delete_asset, dry_run, commit, now, log)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="post-next", description="Post the oldest queued clip to Instagram")
    parser.add_argument("--dry-run", action="store_true", help="create and process the container, do not publish")
    args = parser.parse_args(argv)
    token = os.environ.get("IG_ACCESS_TOKEN")
    if not token:
        print("error: the IG_ACCESS_TOKEN environment variable is not set")
        return 2
    try:
        cfg = load_publish_config()
        client = InstagramClient(token, cfg["ig_account_id"], cfg["graph_version"])
        poster = None
        if cfg.get("youtube"):
            missing = [name for name in YT_ENV if not os.environ.get(name)]
            if missing:
                print(f"error: youtube is enabled but these environment variables are not set: {', '.join(missing)}")
                return 2
            poster = YouTubePoster(YouTubeClient(*(os.environ[name] for name in YT_ENV)),
                                   cfg.get("youtube_privacy", "private"))
        return post_next(queue.QUEUE_ROOT, client, cfg,
                         lambda asset_id: clips_repo.delete_asset(cfg["clips_repo"], asset_id),
                         dry_run=args.dry_run,
                         commit=None if args.dry_run
                         else (lambda message: gitops.commit_queue(message, branch=cfg["queue_branch"])),
                         youtube=poster)
    except PublishError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
