"""Post the oldest queued clip as an Instagram Reel. Runs in GitHub Actions: stdlib + pyyaml only."""
from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from clipper.publish import PublishError, clips_repo, gitops, publer, queue, tiktok
from clipper.env import PROJECT_ROOT
from clipper.publish.config import load_publish_config
from clipper.publish.instagram import IgError, InstagramClient, QuotaExceeded, TokenInvalid
from clipper.publish.youtube import QuotaExceeded as YtQuotaExceeded
from clipper.publish.youtube import TokenInvalid as YtTokenInvalid
from clipper.publish.youtube import YouTubeClient, YtError

DUPLICATE_WINDOW = timedelta(hours=24)
SHORTS_TAG = "#Shorts"
YT_ENV = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
TT_ENV = ("TT_CLIENT_KEY", "TT_CLIENT_SECRET", "TT_REFRESH_TOKEN")
PUBLER_ENV = ("PUBLER_API_KEY", "PUBLER_WORKSPACE_ID")


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
                      log: Callable[[str], None], where: str = "pending") -> None:
    log("found an identical recent post; recording it instead of publishing again")
    entry["media_id"] = str(duplicate["id"])
    entry["permalink"] = duplicate.get("permalink")
    queue.save(root, where, entry)
    commit(f"queue: published {entry['id']}")


def _publish(root: Path, client, cfg: dict, entry: dict, dry_run: bool, commit: Callable[[str], object],
             now: datetime, log: Callable[[str], None], where: str = "pending") -> bool:
    """Create/reuse the container and publish. Returns False for a dry run (nothing published)."""
    is_retry = bool(entry.get("container_id"))
    if is_retry and not dry_run:
        # A previous run may have published and then failed to commit: look before touching any container.
        duplicate = _outside_the_clip(_recent_duplicate, client, entry["caption"], now)
        if duplicate:
            _record_duplicate(root, entry, duplicate, commit, log, where)
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
            queue.save(root, where, entry)
            commit(f"queue: container for {entry['id']}")
    client.wait_until_finished(container, cfg["poll_interval_s"], cfg["poll_timeout_s"])
    if dry_run:
        log("dry run: container FINISHED; not publishing")
        return False
    # Second chance: a post may have appeared while the container was processing.
    duplicate = _recent_duplicate(client, entry["caption"], now) if is_retry else None
    if duplicate:
        _record_duplicate(root, entry, duplicate, commit, log, where)
        return True
    entry["media_id"] = client.publish(container)
    try:
        entry["permalink"] = client.permalink(entry["media_id"])
    except IgError:
        entry["permalink"] = None
    queue.save(root, where, entry)
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
    tiktok_waiting = "tiktok" in entry and not entry["tiktok"]["video_id"]
    if entry.get("asset_id") is not None and not tiktok_waiting and not entry.get("ig_waiting"):
        try:
            delete_asset(entry["asset_id"])
        except PublishError as exc:
            log(f"warning: could not delete the release asset: {exc}")
    commit(f"queue: posted {entry['id']}")
    links = [entry.get("permalink") or entry.get("media_id")]
    for key, name in (("youtube", "YouTube"), ("tiktok", "TikTok"), ("publer", "Publer job")):
        state = entry.get(key) or {}
        if state.get("url") or state.get("video_id"):
            links.append(f"{name}: {state.get('url') or state['video_id']}")
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


def _download(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=300) as response:
            return response.read()
    except (OSError, http.client.HTTPException) as exc:
        raise DownloadError(f"could not download the clip: {type(exc).__name__}") from None


def _fit_tags(tags: list[str], limit: int = 500) -> list[str]:
    """YouTube caps tags at 500 characters, counting a comma between tags and quotes around ones with spaces."""
    kept, used = [], 0
    for tag in (str(t).strip().lstrip("#") for t in tags):
        cost = len(tag) + (2 if " " in tag else 0) + (1 if kept else 0)
        if tag and tag.lower() not in (k.lower() for k in kept) and used + cost <= limit:
            kept.append(tag)
            used += cost
    return kept


class YouTubePoster:
    """Downloads a queued clip's Release asset and uploads it to YouTube. The queue never touches the client."""
    key, name = "youtube", "YouTube"
    token_invalid, quota, api_error = YtTokenInvalid, YtQuotaExceeded, YtError
    token_hint = "Generate a new refresh token with scripts/yt_auth.py and update the YT_REFRESH_TOKEN secret."

    def __init__(self, client: YouTubeClient, privacy: str,
                 fetch: Callable[[str], bytes] | None = None):
        self._client = client
        self._privacy = privacy
        self._fetch = fetch or _download

    def check(self) -> None:
        self._client.access_token()

    def post(self, entry: dict) -> tuple[str, str]:
        title = entry.get("title") or str(entry["caption"]).splitlines()[0][:90]
        if len(title) + len(SHORTS_TAG) + 1 <= 100:
            title = f"{title} {SHORTS_TAG}"
        description = entry.get("youtube_description") or entry["caption"]
        tags = [w for w in str(entry["caption"]).split() if w.startswith("#") and w.lower() not in description.lower()]
        if "#" not in description and tags:
            description = f"{description}\n\n{' '.join(tags)}"
        if SHORTS_TAG.lower() not in description.lower():
            description = f"{description}\n\n{SHORTS_TAG}"
        video_id = self._client.upload(self._fetch(entry["asset_url"]), title, description,
                                       tags=_fit_tags(entry.get("youtube_tags") or []), privacy=self._privacy)
        return video_id, f"https://www.youtube.com/shorts/{video_id}"


def _local_or_download(entry: dict) -> bytes:
    local = PROJECT_ROOT / "output" / entry["video_id"] / f"{entry['id'][len(entry['video_id']) + 1:]}.mp4"
    return local.read_bytes() if local.exists() else _download(entry["asset_url"])


class TikTokPoster:
    """Sends a clip to TikTok as an inbox draft (default) or a direct post. Still processing at the timeout
    counts as sent."""
    key, name = "tiktok", "TikTok"
    token_invalid, quota, api_error = tiktok.TokenInvalid, tiktok.QuotaExceeded, tiktok.TtError
    token_hint = "Generate a new refresh token with scripts/tiktok_auth.py and update the TT_REFRESH_TOKEN secret."

    def __init__(self, client: tiktok.TikTokClient, privacy: str, interval_s: float = 10, timeout_s: float = 300,
                 fetch: Callable[[dict], bytes] | None = None, mode: str = "direct"):
        self._client = client
        self._privacy = privacy
        self._interval = interval_s
        self._timeout = timeout_s
        self._fetch = fetch or _local_or_download
        self.mode = mode

    def _check_privacy(self, info: dict) -> None:
        options = info.get("privacy_level_options") or []
        if self._privacy not in options:
            raise tiktok.ApiError(f"privacy {self._privacy} is not allowed for this account "
                                  f"(allowed: {', '.join(options) or 'none'})")

    def check(self) -> None:
        if self.mode == "draft":
            self._client.access_token()
        else:
            self._check_privacy(self._client.creator_info())

    def post(self, entry: dict) -> tuple[str, str | None]:
        if self.mode == "draft":
            publish_id = self._client.upload_draft(self._fetch(entry))
            try:
                self._client.wait(publish_id, self._interval, self._timeout, done=("SEND_TO_USER_INBOX",
                                                                                   "PUBLISH_COMPLETE"))
            except tiktok.ApiError as exc:
                if exc.code != "TIMEOUT":
                    raise
            return publish_id, None
        info = self._client.creator_info()
        self._check_privacy(info)
        caption = entry.get("tiktok_caption") or entry["caption"]
        publish_id = self._client.upload(self._fetch(entry), caption, self._privacy)
        try:
            done = self._client.wait(publish_id, self._interval, self._timeout)
        except tiktok.ApiError as exc:
            if exc.code == "TIMEOUT":
                return publish_id, None
            raise
        ids = done.get("publicaly_available_post_id") or []
        user = info.get("creator_username")
        return publish_id, (f"https://www.tiktok.com/@{user}/video/{ids[0]}" if ids and user else None)


def _publer_network(provider: str, entry: dict, media: list[dict], tiktok_privacy: str) -> dict:
    caption = entry["caption"]
    if provider == "youtube":
        title = entry.get("title") or str(caption).splitlines()[0][:90]
        return {"type": "short", "title": title[:100], "text": entry.get("youtube_description") or caption,
                "media": media}
    if provider == "tiktok":
        return {"type": "video", "text": entry.get("tiktok_caption") or caption, "media": media,
                "details": {"privacy": tiktok_privacy}}
    if provider in ("instagram", "facebook"):
        return {"type": "reel", "text": caption, "media": media, "details": {"type": "reel"}}
    return {"type": "video", "text": caption, "media": media}


class PublerPoster:
    """Uploads a clip to Publer once and posts it to every configured account. Accounts that succeed are kept
    in the entry's publer state, so a retry only posts to the ones that failed."""
    key, name = "publer", "Publer"
    token_invalid, quota, api_error = publer.TokenInvalid, publer.QuotaExceeded, publer.PbError
    token_hint = "Create a new API key in Publer (Settings > Access & Login > API) and update PUBLER_API_KEY."

    def __init__(self, client: publer.PublerClient, accounts: list[str], *, draft: bool = False,
                 tiktok_privacy: str = "SELF_ONLY", interval_s: float = 10, timeout_s: float = 300,
                 fetch: Callable[[dict], bytes] | None = None):
        self._client = client
        self._accounts = accounts
        self._draft = draft
        self._tiktok_privacy = tiktok_privacy
        self._interval = interval_s
        self._timeout = timeout_s
        self._fetch = fetch or _local_or_download
        self._providers: dict[str, str] | None = None

    def _provider_map(self) -> dict[str, str]:
        if self._providers is None:
            known = {str(a.get("id")): str(a.get("provider")) for a in self._client.accounts()}
            missing = [a for a in self._accounts if a not in known]
            if missing:
                raise publer.ApiError(f"accounts not in this Publer workspace: {', '.join(missing)}")
            self._providers = {a: known[a] for a in self._accounts}
        return self._providers

    def check(self) -> None:
        self._provider_map()

    def post(self, entry: dict) -> tuple[str, str | None]:
        state = entry[self.key]
        done = state.setdefault("done", [])
        providers = self._provider_map()
        todo = [a for a in self._accounts if a not in done]
        if todo:
            media = [{"id": self._client.upload_video(self._fetch(entry), f"{entry['id']}.mp4"), "type": "video"}]
            by_provider: dict[str, list[str]] = {}
            for account in todo:
                by_provider.setdefault(providers[account], []).append(account)
            posts = [{"networks": {p: _publer_network(p, entry, media, self._tiktok_privacy)},
                      "accounts": [{"id": a} for a in ids]} for p, ids in by_provider.items()]
            job_id = self._client.create_posts(posts, draft=self._draft)
            state["job_id"] = job_id
            result = self._client.wait(job_id, self._interval, self._timeout)
            failures = result.get("failures") if isinstance(result, dict) else None
            text = json.dumps(failures) if failures else ""
            failed = [a for a in todo if a in text] or (todo if failures else [])
            done.extend(a for a in todo if a not in failed)
            if failed:
                raise publer.ApiError(f"failed for {', '.join(failed)}: {text[:300]}")
        return state.get("job_id") or "done", None


def _platform(root: Path, entry: dict, cfg: dict, poster, dry_run: bool, commit: Callable[[str], object],
              log: Callable[[str], None], where: str = "pending") -> int:
    state = entry.setdefault(poster.key, queue.new_platform_state())
    if state["video_id"] or state["attempts"] >= cfg["max_attempts"]:
        return 0
    try:
        if dry_run:
            poster.check()
            log(f"dry run: {poster.name} credentials work; not uploading")
            return 0
        video_id, url = poster.post(entry)
    except poster.token_invalid as exc:
        log(f"error: {poster.name} rejected the credentials ({exc}). {poster.token_hint}")
        return 1
    except poster.quota:
        log(f"{poster.name} posting limit reached; will retry on the next run")
        return 0
    except poster.api_error as exc:
        if dry_run:
            log(f"dry run failed: {poster.name}: {exc}")
            return 1
        state["attempts"] += 1
        state["last_error"] = str(exc)
        queue.save(root, where, entry)
        log(f"error: {poster.name}: {exc} (attempt {state['attempts']}/{cfg['max_attempts']})")
        try:
            commit(f"queue: {poster.key} attempt {state['attempts']} failed for {entry['id']}")
        except PublishError as commit_exc:
            log(f"error: could not commit the failure record: {commit_exc}")
        return 1
    except (PublishError, OSError) as exc:
        log(f"error: {poster.name}: {exc}")  # download/queue problems are not the platform's fault
        return 1
    state.update(video_id=video_id, url=url, last_error=None)
    try:
        queue.save(root, where, entry)
        commit(f"queue: {poster.key} published {entry['id']}")
    except (PublishError, OSError) as exc:
        log(f"error: {exc}; the clip is on {poster.name} ({url or video_id}) but the queue update was not completed")
        return 1
    return 0


def _open(state: dict, limit: int) -> bool:
    return not state["video_id"] and state["attempts"] < limit


def _settle(root: Path, entry: dict, cfg: dict, posters: list, delete_asset: Callable[[int], object],
            commit: Callable[[str], object], log: Callable[[str], None], *, instagram: bool) -> None:
    """Close the entry once no platform can still be retried."""
    limit = cfg["max_attempts"]
    states = [entry[p.key] for p in posters]
    ig_open = instagram and not entry.get("media_id") and entry["attempts"] < limit
    if ig_open or any(_open(s, limit) for s in states):
        return
    if (instagram and entry.get("media_id")) or any(s["video_id"] for s in states):
        _finalize(root, entry, delete_asset, commit, log)
        return
    entry.pop("tiktok", None)
    queue.move(root, entry, "pending", "failed")
    commit(f"queue: failed {entry['id']}")
    log(f"{entry['id']}: every platform ran out of attempts; entry is now failed")


def _post_platforms(root: Path, entry: dict, cfg: dict, delete_asset: Callable[[int], object], posters: list,
                    dry_run: bool, commit: Callable[[str], object], log: Callable[[str], None], *,
                    code: int = 0, instagram: bool = False) -> int:
    try:
        for poster in posters:
            code = max(code, _platform(root, entry, cfg, poster, dry_run, commit, log))
        if not dry_run:
            _settle(root, entry, cfg, posters, delete_asset, commit, log, instagram=instagram)
    except (PublishError, OSError) as exc:
        log(f"error: {exc}")
        return 1
    return code


def _post_both(root: Path, client, cfg: dict, entry: dict, delete_asset: Callable[[int], object], posters: list,
               dry_run: bool, commit: Callable[[str], object], now: datetime, log: Callable[[str], None]) -> int:
    limit = cfg["max_attempts"]
    for poster in posters:
        entry.setdefault(poster.key, queue.new_platform_state())
    others_open = any(_open(entry[p.key], limit) for p in posters)
    code = 0
    if not entry.get("media_id") and entry["attempts"] < limit:
        code = _instagram(root, client, cfg, entry, delete_asset, dry_run, commit, now, log,
                          finalize=False, keep_open=others_open)
    elif entry.get("media_id"):
        log("already published on Instagram; only the other platforms are left")
    if not queue.path_for(root, "pending", entry["id"]).exists():
        return code  # Instagram moved it (needs a manual check); nothing more to do automatically
    return _post_platforms(root, entry, cfg, delete_asset, posters, dry_run, commit, log,
                           code=code, instagram=True)


def post_next(root: Path, client, cfg: dict, delete_asset: Callable[[int], object], *, dry_run: bool = False,
              commit: Callable[[str], object] | None = None, now: datetime | None = None,
              log: Callable[[str], None] = print, youtube: YouTubePoster | None = None,
              tiktok_later: bool = False, publer: PublerPoster | None = None, ig_later: bool = False) -> int:
    """`tiktok_later`: mark the entry for a TikTok draft once it is posted, and keep its asset until then.
    `ig_later`: the same for Instagram, which posts on its own schedule (instagram_next)."""
    commit = commit or (lambda message: None)
    now = now or datetime.now(timezone.utc)
    posters = [p for p in (youtube, publer) if p is not None]
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
    if tiktok_later:
        entry.setdefault("tiktok", queue.new_platform_state())
    if ig_later and not entry.get("media_id") and entry["attempts"] < cfg["max_attempts"]:
        entry["ig_waiting"] = True
    if client is None:
        if not posters:
            log("error: no platform configured")
            return 1
        return _post_platforms(root, entry, cfg, delete_asset, posters, dry_run, commit, log)
    if posters:
        return _post_both(root, client, cfg, entry, delete_asset, posters, dry_run, commit, now, log)
    return _instagram(root, client, cfg, entry, delete_asset, dry_run, commit, now, log)


def _ig_candidates(root: Path, cfg: dict, slot: str) -> list[tuple[str, dict]]:
    """Clips still waiting for Instagram, oldest first. The "old" slot takes only instagram_backlog videos."""
    backlog = set(cfg.get("instagram_backlog") or [])
    found = [("pending", e) for e in queue.load_all(root, "pending")
             if not e.get("media_id") and not _is_stale_duplicate(root, e)]
    found += [("posted", e) for e in queue.load_all(root, "posted") if e.get("ig_waiting")]
    found = [(w, e) for w, e in found if e["attempts"] < cfg["max_attempts"] and e.get("asset_url")
             and (e["video_id"] in backlog) == (slot == "old")]
    return sorted(found, key=lambda pair: (pair[1]["queued_at"], pair[1]["id"]))


def _ig_done(root: Path, entry: dict, where: str, delete_asset: Callable[[int], object],
             log: Callable[[str], None]) -> None:
    entry.pop("ig_waiting", None)
    tiktok_waiting = "tiktok" in entry and not entry["tiktok"]["video_id"]
    if where == "posted" and entry.get("asset_id") is not None and not tiktok_waiting:
        try:
            delete_asset(entry["asset_id"])
            entry["asset_id"] = None
        except PublishError as exc:
            log(f"warning: could not delete the release asset: {exc}")
    queue.save(root, where, entry)


def instagram_next(root: Path, client, cfg: dict, delete_asset: Callable[[int], object], *, slot: str = "new",
                   dry_run: bool = False, commit: Callable[[str], object] | None = None,
                   now: datetime | None = None, log: Callable[[str], None] = print) -> int:
    """Post one clip to Instagram: the oldest new clip, or with slot="old" the oldest backlog clip."""
    commit = commit or (lambda message: None)
    now = now or datetime.now(timezone.utc)
    try:
        candidates = _ig_candidates(root, cfg, slot)
    except (PublishError, OSError, ValueError) as exc:
        log(f"error: could not read the queue: {exc}")
        return 1
    if not candidates:
        log(f"Instagram ({slot}): nothing waiting")
        return 0
    where, entry = candidates[0]
    log(f"Instagram ({slot}) next: {entry['id']} ({_short(entry['caption'])})")
    try:
        used, total = _outside_the_clip(client.publishing_limit)
        if used >= total:
            log(f"publishing quota reached ({used}/{total}); will retry on the next run")
            return 0
        if not _publish(root, client, cfg, entry, dry_run, commit, now, log, where):
            return 0
        _ig_done(root, entry, where, delete_asset, log)
        commit(f"queue: instagram published {entry['id']}")
        log(f"posted {entry['id']} to Instagram: {entry.get('permalink') or entry['media_id']}")
    except _NotTheClipsFault as exc:
        log(f"error: {exc}")
        return 1
    except _AlreadyPublished:
        log(f"{entry['id']}: {MANUAL_CHECK_ERROR}")
        if not dry_run:
            entry["last_error"] = MANUAL_CHECK_ERROR
            entry["attempts"] = cfg["max_attempts"]
            _ig_done(root, entry, where, lambda asset_id: None, log)
            commit(f"queue: needs a manual check: {entry['id']}")
        return 1
    except TokenInvalid as exc:
        log(f"error: Instagram rejected the access token ({exc}). "
            "Generate a new one and update the IG_ACCESS_TOKEN secret.")
        return 1
    except QuotaExceeded:
        log("publishing quota reached; will retry on the next run")
        return 0
    except IgError as exc:
        if dry_run:
            log(f"dry run failed: {exc}")
            return 1
        entry["attempts"] += 1
        entry["last_error"] = str(exc)
        if entry["attempts"] >= cfg["max_attempts"]:
            _ig_done(root, entry, where, delete_asset, log)
        else:
            queue.save(root, where, entry)
        log(f"error: {exc} (attempt {entry['attempts']}/{cfg['max_attempts']})")
        try:
            commit(f"queue: instagram attempt {entry['attempts']} failed for {entry['id']}")
        except PublishError as commit_exc:
            log(f"error: could not commit the failure record: {commit_exc}")
        return 1
    except (PublishError, OSError) as exc:
        log(f"error: {exc}")
        return 1
    return 0


def tiktok_drafts(root: Path, cfg: dict, poster: TikTokPoster, delete_asset: Callable[[int], object], *,
                  dry_run: bool = False, commit: Callable[[str], object] | None = None,
                  log: Callable[[str], None] = print, summary: Callable[[str], None] | None = None,
                  limit: int = 5, ids: list[str] | None = None) -> int:
    """Send already-posted clips to TikTok, oldest first. `ids` also picks posted clips not marked for TikTok."""
    commit = commit or (lambda message: None)
    summary = summary or log
    try:
        posted = sorted(queue.load_all(root, "posted"), key=lambda e: (e["queued_at"], e["id"]))
    except (PublishError, OSError, ValueError) as exc:
        log(f"error: could not read the queue: {exc}")
        return 1
    if ids is not None:
        wanted = [e for e in posted if e["id"] in ids]
        for entry in wanted:
            entry.setdefault("tiktok", queue.new_platform_state())
    else:
        wanted = [e for e in posted if "tiktok" in e]
    wanted = [e for e in wanted if _open(e["tiktok"], cfg["max_attempts"])]
    if not wanted:
        log("TikTok: nothing waiting")
        return 0
    if dry_run:
        log(f"TikTok: {len(wanted)} clip(s) waiting")
        return _platform(root, wanted[0], cfg, poster, True, commit, log, where="posted")
    code, sent = 0, 0
    for entry in wanted[:limit]:
        code = max(code, _platform(root, entry, cfg, poster, False, commit, log, where="posted"))
        state = entry["tiktok"]
        if state["video_id"]:
            sent += 1
            caption = entry.get("tiktok_caption") or entry["caption"]
            summary(f"### {entry['id']}\n\n{entry.get('title') or ''}\n\n```\n{caption}\n```\n")
        elif state["attempts"] < cfg["max_attempts"]:
            break  # posting limit or a fresh failure: try again on the next run
        if entry.get("asset_id") is not None and not entry.get("ig_waiting"):
            try:
                delete_asset(entry["asset_id"])
            except PublishError as exc:
                log(f"warning: could not delete the release asset: {exc}")
    verb = "drafts sent to your TikTok inbox" if poster.mode == "draft" else "posted to TikTok"
    log(f"TikTok: {sent} {verb}")
    return code


def _handoff_text(entry: dict) -> str:
    caption = entry.get("tiktok_caption") or entry["caption"]
    return (f"### {entry.get('title') or entry['id']}\n\n[Download {entry['id']}.mp4]({entry['asset_url']})"
            f"\n\n```\n{caption}\n```\n")


def tiktok_handoff(root: Path, cfg: dict, delete_asset: Callable[[int], object], *, now: datetime | None = None,
                   dry_run: bool = False, commit: Callable[[str], object] | None = None,
                   log: Callable[[str], None] = print, summary: Callable[[str], None] | None = None) -> int:
    """Manual mode: list posted clips for upload in TikTok Studio; delete their assets after tiktok_keep_days."""
    commit = commit or (lambda message: None)
    summary = summary or log
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    cutoff = now - timedelta(days=cfg["tiktok_keep_days"])
    try:
        posted = sorted(queue.load_all(root, "posted"), key=lambda e: (e["queued_at"], e["id"]))
    except (PublishError, OSError, ValueError) as exc:
        log(f"error: could not read the queue: {exc}")
        return 1
    marked = [e for e in posted if "tiktok" in e]
    new = [e for e in marked if not e["tiktok"]["video_id"]]
    if dry_run:
        log(f"TikTok: {len(new)} new clip(s) to hand off")
        return 0
    try:
        for entry in new:
            entry["tiktok"].update(video_id="manual", url=entry["asset_url"], sent_at=stamp, last_error=None)
            queue.save(root, "posted", entry)
            summary(_handoff_text(entry))
        for entry in marked:
            state = entry["tiktok"]
            sent = datetime.strptime(state.get("sent_at") or stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if (state["video_id"] == "manual" and entry.get("asset_id") is not None and sent < cutoff
                    and not entry.get("ig_waiting")):
                try:
                    delete_asset(entry["asset_id"])
                except PublishError as exc:
                    log(f"warning: could not delete the release asset: {exc}")
                entry["asset_id"], state["url"] = None, None
                queue.save(root, "posted", entry)
        ready = [e for e in reversed(marked) if e["tiktok"]["video_id"] == "manual" and e.get("asset_id") is not None]
        days = cfg["tiktok_keep_days"]
        lines = ["# TikTok uploads", "", f"Clips already on YouTube, newest first. Upload each in TikTok Studio "
                 f"and paste its caption. Download links work for {days} days after a clip is listed.", ""]
        lines += [_handoff_text(e) for e in ready] or ["Nothing waiting.\n"]
        (root / "tiktok.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
        commit(f"queue: tiktok handoff ({len(new)} new)")
    except (PublishError, OSError) as exc:
        log(f"error: {exc}")
        return 1
    log(f"TikTok: {len(new)} new clip(s) listed in queue/tiktok.md; {len(ready)} ready to upload")
    return 0


def _env(names: tuple[str, ...], platform: str) -> list[str] | None:
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        print(f"error: {platform} is enabled but these environment variables are not set: {', '.join(missing)}")
        return None
    return [os.environ[name] for name in names]


def _load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = (part.strip() for part in line.split("=", 1))
            if value:
                os.environ.setdefault(key, value)


def _step_summary(text: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="post-next", description="Post the oldest queued clip")
    parser.add_argument("--dry-run", action="store_true", help="check credentials and processing, do not publish")
    parser.add_argument("--tiktok-drafts", action="store_true", help="send posted clips to TikTok instead")
    parser.add_argument("--ids", help="with --tiktok-drafts: comma-separated posted clip ids to send")
    parser.add_argument("--limit", type=int, default=5, help="with --tiktok-drafts: most clips to send")
    parser.add_argument("--no-commit", action="store_true", help="update queue files without committing")
    parser.add_argument("--instagram", choices=("new", "old"), help="post one clip to Instagram instead")
    args = parser.parse_args(argv)
    if args.tiktok_drafts:
        _load_dotenv()
    try:
        cfg = load_publish_config()
        tt = None
        manual = cfg.get("tiktok_mode") == "manual"
        if cfg.get("tiktok") and not manual and not args.instagram and (args.tiktok_drafts or args.dry_run):
            values = _env(TT_ENV, "tiktok")
            if values is None:
                return 2
            tt = TikTokPoster(tiktok.TikTokClient(*values), cfg["tiktok_privacy"], cfg["poll_interval_s"],
                              cfg["poll_timeout_s"], mode=cfg["tiktok_mode"])
        commit = None if args.dry_run or args.no_commit else (
            lambda message: gitops.commit_queue(message, branch=cfg["queue_branch"]))
        delete = lambda asset_id: clips_repo.delete_asset(cfg["clips_repo"], asset_id)  # noqa: E731
        if args.tiktok_drafts:
            if not cfg.get("tiktok"):
                print("TikTok is off in config/publish.yaml; nothing to do")
                return 0
            if manual:
                return tiktok_handoff(queue.QUEUE_ROOT, cfg, delete, dry_run=args.dry_run, commit=commit,
                                      summary=_step_summary)
            return tiktok_drafts(queue.QUEUE_ROOT, cfg, tt, delete, dry_run=args.dry_run, commit=commit,
                                 summary=_step_summary, limit=args.limit,
                                 ids=args.ids.split(",") if args.ids else None)
        if args.instagram:
            if not cfg.get("ig_account_id"):
                print("Instagram is off in config/publish.yaml; nothing to do")
                return 0
            token = os.environ.get("IG_ACCESS_TOKEN")
            if not token:
                print("error: the IG_ACCESS_TOKEN environment variable is not set")
                return 2
            client = InstagramClient(token, cfg["ig_account_id"], cfg["graph_version"])
            return instagram_next(queue.QUEUE_ROOT, client, cfg, delete, slot=args.instagram,
                                  dry_run=args.dry_run, commit=commit)
        youtube = None
        if cfg.get("youtube"):
            values = _env(YT_ENV, "youtube")
            if values is None:
                return 2
            youtube = YouTubePoster(YouTubeClient(*values), cfg.get("youtube_privacy", "private"))
        publer_poster = None
        if cfg.get("publer"):
            values = _env(PUBLER_ENV, "publer")
            if values is None:
                return 2
            publer_poster = PublerPoster(publer.PublerClient(*values), cfg["publer_accounts"],
                                         draft=cfg["publer_mode"] == "draft", tiktok_privacy=cfg["tiktok_privacy"],
                                         interval_s=cfg["poll_interval_s"], timeout_s=cfg["poll_timeout_s"])
        code = post_next(queue.QUEUE_ROOT, None, cfg, delete, dry_run=args.dry_run, commit=commit,
                         youtube=youtube, tiktok_later=bool(cfg.get("tiktok")), publer=publer_poster,
                         ig_later=bool(cfg.get("ig_account_id")))
        if args.dry_run and tt is not None:
            code = max(code, tiktok_drafts(queue.QUEUE_ROOT, cfg, tt, delete, dry_run=True))
        elif args.dry_run and cfg.get("tiktok") and manual:
            code = max(code, tiktok_handoff(queue.QUEUE_ROOT, cfg, delete, dry_run=True))
        return code
    except PublishError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
