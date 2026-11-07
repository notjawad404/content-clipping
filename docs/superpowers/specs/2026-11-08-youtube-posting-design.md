# Post Each Queued Clip to YouTube Shorts Too — Design Spec

**Date:** 2026-11-08
**Status:** Draft, pending review
**Builds on:** `2026-11-07-instagram-posting-design.md` (queue + `post-next` workflow) and the YouTube client already added in `clipper/publish/youtube.py`

## 1. Goal

Every clip in the queue goes to Instagram as a Reel (as today) and to YouTube as a Short, from the same cron run. A failure on one platform never blocks or repeats the other.

### Already done
- Google Cloud project `content-clipping-yt-83611` (account hammadalive2@gmail.com), YouTube Data API v3 enabled, consent screen in Production, Desktop OAuth client.
- Actions secrets `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.
- `clipper/publish/youtube.py` (token refresh + resumable upload, injectable HTTP, unit-tested) and a private test upload confirmed on the right channel.

### Decisions
| Question | Decision |
|---|---|
| One queue or two | One queue; each entry is posted to every enabled platform |
| Instagram state | Untouched. The existing `container_id` / `media_id` / `permalink` fields and the whole crash-recovery logic in `post_next.py` stay as they are |
| YouTube state | A new `youtube` object on the entry: `{video_id, url, attempts, last_error}` |
| Title | The clip's `title` (max 100 chars), plus ` #Shorts` when it fits |
| Description | `post.youtube` from `clips_resolved.json` (already in the schema), with `#Shorts` appended |
| Privacy | `youtube_privacy` in `config/publish.yaml`, default `private`. Flip to `public` once the API audit passes (until then Google forces private) |
| Enable switch | `youtube: true/false` in `config/publish.yaml`; off means today's behaviour exactly |
| Old entries | An entry with no `youtube` object is treated as not-yet-posted on YouTube when the switch is on. Already-posted entries are never touched |

### Out of scope
Duplicate detection on YouTube (see section 4), TikTok/X, thumbnails, scheduled publishing via `publishAt`, changing cron times.

## 2. Entry shape

`queue.new_entry` gains `title` and `youtube_description`, and `youtube: {"video_id": None, "url": None, "attempts": 0, "last_error": None}`. `enqueue` fills the first two from the clip (`title`, `post.youtube`). A missing `post.youtube` falls back to the Instagram caption, so enqueueing never fails because of YouTube.

## 3. `post_next` flow

For the oldest pending entry:
1. **Instagram** runs exactly as today if `media_id` is empty. If Instagram is already done, skip it.
2. **YouTube** (only when enabled and `youtube.video_id` is empty): download `asset_url` with `urllib`, upload with `YouTubeClient`, then immediately set `youtube.video_id`/`url`, save, and commit (`queue: youtube published <id>`).
3. **Finish** when no platform is still retryable:
   - Move to `posted/` if at least one platform succeeded.
   - Move to `failed/` if every platform ran out of attempts without a success.
   - Delete the Release asset only at this point, never while a platform still needs it.

Per-platform attempts are separate: a YouTube failure increments `youtube.attempts` only, and stops at `max_attempts` for YouTube without touching Instagram's count. An exhausted platform is recorded in `last_error` and does not hold the entry open.

Error handling mirrors Instagram:
- `TokenInvalid`: log "regenerate YT_REFRESH_TOKEN", exit 1, no attempt counted.
- `QuotaExceeded`: log and exit 0, retried on the next run, no attempt counted.
- Any other `YtError`: counted as a YouTube attempt.
- Download or git failures: not the platform's fault, never counted.

A dry run downloads the asset and checks the token refresh, and does not upload.

## 4. Known risk: duplicates on YouTube

Instagram avoids double posts by listing recent media. The YouTube scope in use (`youtube.upload`) cannot list videos, so there is no equivalent check. The window is: upload succeeds, then the commit fails before the video id is saved, and the next run uploads again. Mitigations: commit right after the upload, and the workflow's `concurrency: ig-post` group stops overlapping runs. Closing the gap fully would need the `youtube.readonly` scope and a new consent; not worth it unless duplicates actually happen.

## 5. Workflow and config

- `post-next.yml`: pass `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` as env vars. No new dependency.
- `config/publish.yaml`: add `youtube: true` and `youtube_privacy: private`. `load_publish_config` validates `youtube_privacy` is one of `private`, `unlisted`, `public`.
- If `youtube` is on and any `YT_*` variable is missing, exit 2 with a one-line message before posting anything.

## 6. Tests

- `queue.new_entry` has the new fields; old entries without them still load.
- YouTube succeeds, Instagram fails (and the reverse): the successful one is recorded and not repeated on the next run.
- Both exhaust their attempts: entry moves to `failed/`.
- Asset deleted only after all platforms are finished.
- `TokenInvalid` and `QuotaExceeded` do not count attempts.
- Switch off: behaviour identical to today (existing tests unchanged and green).
- Dry run does not upload.

## 7. Rollout

1. Merge with `youtube: true` and `youtube_privacy: private`.
2. Run the workflow with `dry_run` on, then let one real clip go out and check it in YouTube Studio.
3. Submit the YouTube API compliance audit (separate, in the browser).
4. When approved, set `youtube_privacy: public`.
