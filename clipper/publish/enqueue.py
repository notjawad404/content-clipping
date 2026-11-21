"""Local step: upload a job's rendered clips and write queue entries for the posting workflow."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from clipper.jobs import Job
from clipper.publish import PublishError, clips_repo, queue
from clipper.publish.clips_repo import RepoError


def enqueue_job(job: Job, root: Path, repo: str, *, upload=clips_repo.upload_asset, now: datetime | None = None,
                only: list[str] | None = None, export=None) -> list[tuple[str, str, str]]:
    try:
        resolved = job.read_json(job.clips_resolved)
    except json.JSONDecodeError as exc:
        raise PublishError(f"{job.clips_resolved.name} is not valid JSON: {exc}") from exc
    campaign = job.read_json(job.job_file).get("campaign")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[tuple[str, str, str]] = []
    for clip in resolved["clips"]:
        cid, title = clip["id"], clip["title"]
        if only and cid not in only:
            continue
        video = job.out / f"{cid}.mp4"
        if queue.exists_anywhere(root, f"{job.video_id}_{cid}"):
            rows.append((cid, title, "skipped: already queued"))
        elif not video.exists():
            rows.append((cid, title, "skipped: no rendered mp4"))
        else:
            try:
                caption = clip["post"]["instagram"]
            except KeyError:
                rows.append((cid, title, f"failed: no post.instagram caption in {job.clips_resolved.name}"))
                continue
            try:
                url, asset_id = upload(repo, f"v-{job.video_id}", video)
            except RepoError as exc:
                rows.append((cid, title, f"failed: {exc}"))
                continue
            entry = queue.new_entry(video_id=job.video_id, clip_id=cid, campaign=campaign, caption=caption,
                                    asset_url=url, asset_id=asset_id, queued_at=stamp, title=title,
                                    youtube_description=clip["post"].get("youtube") or caption,
                                    tiktok_caption=clip["post"].get("tiktok") or caption,
                                    youtube_tags=clip.get("youtube_tags"))
            try:
                queue.save(root, "pending", entry)
            except OSError as exc:
                rows.append((cid, title, f"failed: could not write the queue entry ({type(exc).__name__})"))
                continue
            if export is not None:
                try:
                    export(entry, video)
                except OSError as exc:
                    rows.append((cid, title, f"queued (local copy failed: {type(exc).__name__})"))
                    continue
            rows.append((cid, title, "queued"))
    return rows
