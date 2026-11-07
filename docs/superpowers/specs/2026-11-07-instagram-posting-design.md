# Instagram Auto-Posting via GitHub Actions — Design Spec

**Date:** 2026-11-07
**Status:** Approved in brainstorming; pending written-spec review
**Builds on:** `2026-11-07-clipper-design.md` (Publisher was out of scope for v1)

## 1. Goal

Clips are still produced locally by the existing clipper. After that, a GitHub Actions workflow posts them to Instagram as Reels on a drip schedule, with no manual upload.

### Success criteria
- `uv run clipper queue <video_id>` makes every finished clip of a job postable with one command.
- A scheduled workflow posts at most one queued clip per run, using the clip's Instagram caption from the existing pipeline unchanged.
- A clip is never posted twice, even if a run fails halfway.
- If the token expires or the API rejects a post, the workflow fails visibly and nothing in the queue is lost.

### Decisions (from brainstorming)
| Question | Decision |
|---|---|
| What runs in Actions | Posting only. Download, transcription, clip selection and rendering stay local |
| Instagram account | Switch the personal account to a free **Creator** account. Official Graph API, "Instagram API with Instagram Login" (no Facebook Page) |
| Where clips live for Instagram to fetch | Release assets in a separate **public** `clips` repo |
| Main repo visibility | **Private** |
| Cadence | Drip: cron runs several times a day, one clip per run |

### Out of scope
TikTok / YouTube Shorts / X posting, analytics, running the clipper in Actions, multiple Instagram accounts, scheduling a specific clip at a specific time, stories and carousels.

## 2. Why two repos

The Reels API accepts a `video_url` that Instagram's servers fetch themselves. A Release asset in a private repo needs authentication, so Instagram cannot fetch it. Resumable upload (pushing the file to `rupload.facebook.com`) appears to require Facebook Login for Business, which needs a Facebook Page; the docs conflict on whether Instagram Login supports it (see §9). The private repo keeps code, configs, captions and the queue private. The public `clips` repo contains only video files for the minutes or hours between queueing and posting, and each is deleted after posting.

Consequence to accept: **a queued clip is publicly downloadable by anyone with the URL until it is posted.** Clips are source footage from creator-authorized campaigns, but the owner should be aware.

## 3. Architecture

```
LOCAL                                   GITHUB (private repo)                  INSTAGRAM
clipper produce → output/<id>/*.mp4
clipper queue <id>
  ├─ upload mp4 ──────────────► public `clips` repo (release asset)
  └─ write queue/pending/*.json ──► git push

                                  post-next.yml (cron, 1 clip/run)
                                    ├─ read oldest pending entry
                                    ├─ GET content_publishing_limit ─────────► quota
                                    ├─ POST /media (REELS, video_url) ───────► container
                                    ├─ poll status_code until FINISHED
                                    ├─ POST /media_publish ──────────────────► live Reel
                                    ├─ move entry → queue/posted/ (media id, permalink)
                                    ├─ delete release asset
                                    └─ commit queue change

                                  refresh-token.yml (monthly) → renews token secret
```

### Queue
Plain JSON files in the repo, one per clip, so history is auditable in git. Directories: `queue/pending/`, `queue/posted/`, `queue/failed/`. A tracked `queue/.gitkeep` keeps them present. Entry (`<video_id>_<clip_id>.json`):

```json
{
  "id": "5pk8HLcAAT0_clip_01",
  "video_id": "5pk8HLcAAT0",
  "campaign": "social-media-justice",
  "caption": "<resolved Instagram caption>",
  "asset_url": "https://github.com/<owner>/<clips-repo>/releases/download/<tag>/<file>.mp4",
  "asset_id": 123456789,
  "queued_at": "2026-11-07T21:30:00Z",
  "attempts": 0,
  "last_error": null,
  "container_id": null,
  "media_id": null,
  "permalink": null
}
```

Order: oldest `queued_at` first; ties broken by clip id.

Caption source: `jobs/<id>/clips.resolved.json` → `clips[].post["instagram"]`, which already has the campaign's required text and capped hashtags applied. The video is `output/<id>/<clip_id>.mp4`. `queue` skips clips whose render failed or whose `.mp4` is missing, and refuses to queue a clip already present in any queue directory.

## 4. Components

New package `clipper/publish/`, each module one job:

- **`queue.py`** — load, save and move entries between `pending`, `posted`, `failed`; pick the next entry. Pure file operations, no network.
- **`clips_repo.py`** — upload a file as a release asset in the clips repo, return `(asset_url, asset_id)`; delete by asset id. Uses the `gh` CLI locally and `GITHUB_TOKEN`/PAT in Actions. One release per `video_id` (tag `v-<video_id>`), created on demand.
- **`instagram.py`** — thin Graph API client over `https://graph.instagram.com/<version>/`: `create_reel_container`, `container_status`, `publish`, `publishing_limit`, `permalink`, `refresh_token`. Takes token and user id as arguments. Knows nothing about GitHub or the queue. Maps API errors to typed exceptions: `QuotaExceeded`, `TokenInvalid`, `ProcessingFailed`, `ApiError`.
- **`post_next.py`** — orchestrator called by the workflow: choose entry, check quota, create container, poll, publish, record, clean up. Supports `--dry-run`.
- **`cli.py`** — new subcommands `queue <video_id> [--only clip_01]` and `post-next [--dry-run]`.

### Config: `config/publish.yaml`
```yaml
clips_repo: <owner>/<clips-repo>
graph_version: v23.0        # confirm current at build time
max_attempts: 3
poll_interval_s: 10
poll_timeout_s: 300
```
Cron times are not configurable at runtime (Actions requires literal cron in the workflow YAML). Default `0 9,13,19 * * *` UTC, edited directly in `post-next.yml`.

### Workflows
- **`post-next.yml`** — triggers: `schedule` and `workflow_dispatch` (manual post-now, with a `dry_run` input). `concurrency: {group: ig-post, cancel-in-progress: false}`. `permissions: contents: write`. Installs with `uv`, runs `uv run clipper post-next`, commits queue changes. Needs only the `publish` dependencies, not ffmpeg or whisper.
- **`refresh-token.yml`** — monthly; calls the refresh endpoint and writes the new token to the `IG_ACCESS_TOKEN` secret. Writing a secret from a workflow needs a PAT (or GitHub App) with permission to manage Actions secrets, stored as `GH_ADMIN_TOKEN`.

### Secrets (private repo, Actions)
`IG_ACCESS_TOKEN`, `IG_USER_ID`, `CLIPS_REPO_TOKEN` (PAT with contents write on the public clips repo only), `GH_ADMIN_TOKEN` (for the refresh workflow).

## 5. `post-next` algorithm

1. Take the oldest entry in `queue/pending/`. If none, exit 0 ("nothing to post").
2. If the entry has a `media_id`, a previous run published it but did not finish cleanup: skip to step 8.
3. `GET /<ig-user-id>/content_publishing_limit`. If used ≥ total, exit 0 with a notice. This is not a failure and does not count as an attempt.
4. If the entry has a `container_id` from an earlier attempt, reuse it only if its status is not `ERROR`/`EXPIRED`; otherwise create a new one.
5. `POST /<ig-user-id>/media` with `media_type=REELS`, `video_url=<asset_url>`, `caption=<caption>`, `share_to_feed=true`. Save `container_id` to the entry and commit it before continuing.
6. Poll `GET /<container_id>?fields=status_code` every `poll_interval_s` until `FINISHED`. `ERROR`/`EXPIRED` or `poll_timeout_s` exceeded → failure.
7. `POST /<ig-user-id>/media_publish?creation_id=<container_id>`. Save `media_id` to the entry immediately and commit. Fetch `permalink`.
8. Move the entry to `queue/posted/`, delete the release asset, commit.

Failure handling:
- A failure at steps 5–7 increments `attempts`, records `last_error`, leaves the entry in `pending`, and exits non-zero so GitHub emails a failure notice. At `max_attempts` the entry moves to `queue/failed/`.
- `TokenInvalid` exits non-zero without incrementing `attempts` (the clip is fine; the credential is not).
- The double-post guard is step 2: `media_id` is committed immediately after publish, before any other work. If that commit itself fails, the next run sees no `media_id` and could post the clip again. To narrow that window, step 7 first lists the account's 5 most recent media (`GET /<ig-user-id>/media?limit=5&fields=caption,timestamp`) and, if one has an identical caption and was created within the last 24 hours, records it as the published media instead of publishing. This reduces but cannot fully remove the double-post risk; it is a known limitation.

Secrets are never printed; captions are not logged beyond the first 40 characters.

## 6. Local `queue` command

`uv run clipper queue <video_id> [--only clip_01]`:
1. Read `jobs/<id>/clips.resolved.json`; for each clip with an existing `output/<id>/<clip_id>.mp4` and no existing queue entry:
2. Upload the mp4 via `clips_repo.py`; create the entry with the Instagram caption.
3. After all clips: `git add queue/ && git commit && git push` (prints the commit; fails clearly if the working tree has unrelated staged changes, so it never sweeps in other files).
4. Print a table: clip, title, duration, queued/skipped (reason).

Run it after `clipper produce`. `clipper finish` only deletes downloaded source media, not `output/`, so it can be run before or after `queue`.

## 7. Testing

- Unit (pytest, `responses`-style HTTP mocking, no network): queue transitions and ordering; `instagram.py` for success, still-processing, ERROR, quota, invalid-token and malformed responses; `post_next.py` for each failure/retry path including the `media_id` guard and attempts counting; `queue` command skipping missing mp4s and duplicates; caption selection.
- `post-next --dry-run`: runs steps 1–4 and 5–6 with real API calls except it never calls `media_publish`. Unpublished containers expire on their own.
- Manual verification gate before enabling the cron: one real end-to-end post of a throwaway clip through `workflow_dispatch`.
- Workflow YAML validated with `actionlint` if available.

## 8. Owner setup guide (manual, one time)

1. Instagram: Settings → Account type and tools → switch to **Creator**.
2. developers.facebook.com: create an app, add the **Instagram** product with **Instagram API setup with Instagram login**; add the Instagram account as an Instagram Tester and accept the invite in the Instagram app; request the `instagram_business_basic` and `instagram_business_content_publish` permissions. While the app is in development mode, posting to your own tester account should work without app review (verify at build time).
3. Generate a token for the account, exchange it for a long-lived token (60 days).
4. Create the private repo for this project and the public `clips` repo (empty, with a README).
5. Create fine-grained PATs for `CLIPS_REPO_TOKEN` and `GH_ADMIN_TOKEN`; add the four secrets to the private repo.
6. Run `post-next.yml` manually with `dry_run` on, then once for real.

## 9. Risks and items to verify while building

- **Resumable upload on Instagram Login** — Meta's docs conflict. If it is supported, the public clips repo becomes unnecessary and a follow-up could drop it.
- **Daily publishing cap** — Meta's pages say both 100 and 50 per 24 hours. The code reads the live value from `content_publishing_limit` and never hardcodes it.
- **Token lifecycle** — long-lived tokens last about 60 days and refresh needs the token to be at least 24 hours old and not expired. Confirm exact endpoint and rules in the current docs. If the monthly refresh fails and the token lapses, posting stops until a new token is generated by hand.
- **Graph API version** — pin to the current stable version at build time.
- **Reel specs** — the clipper's output (1080×1920, H.264/AAC, 20–90 s) is believed to meet Reels requirements, but the exact API length and file-size limits were not checked. Confirm them in the current docs and inspect the first real post in the feed.
- **Instagram may reject or reduce reach** for reposted third-party content or watermarked clips; that is a platform-policy matter outside this system.
- **Public exposure** of queued clips (see §2).
- **Cron behaviour** — GitHub scheduled workflows can run several minutes late, and GitHub disables them after 60 days without repository activity. If you stop queueing clips for two months the schedule must be re-enabled by hand in the Actions tab.
