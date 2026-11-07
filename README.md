# Clipper

Local podcast clipper for Claude Code: paste a YouTube link, get finished 1080×1920 clips for Instagram Reels, TikTok, YouTube Shorts and X, with per-platform post captions.

## Setup (once)

```bash
brew install ffmpeg-full
uv sync
bash scripts/setup_assets.sh
uv run clipper doctor
```

## Use

In Claude Code, in this folder, paste a YouTube link:

> https://www.youtube.com/watch?v=…

By default Claude makes up to 5 clips and posts every clip that passes to Instagram, then lists the Reel links. If older clips are already waiting in the queue, new clips are queued behind them and posted by the cron instead of immediately. Add plain-word changes: a count ("only 3", "10 clips"), "schedule them" or "spread them through the day" (queue only; the cron posts 3 a day at 09:00, 13:00 and 19:00 UTC), "campaign `<name>`" (otherwise Claude picks one from the video only on a clear match), "just make the clips" or "don't post" (makes the clips without posting them), "under 30 seconds", "no zooms", "blue captions", "review first". Clips have no sound effects.

Posting needs `gh auth login` and the `master` branch checked out. If posting stops with an error, run `uv run clipper post-now` to continue from the queue (it also posts clips from other videos that are waiting in the queue).

Clips land in `output/<video_id>/`: `clip_XX.mp4`, `clip_XX_post.md` (captions per platform) and `summary.md`.

## Campaigns

Copy `config/campaigns/example.yaml` to `config/campaigns/<name>.yaml` and fill in the brief's creator tag, required text and hashtags, and length limits.

## Manual commands

```bash
uv run clipper prepare "<url>" --campaign <name>   # download audio + transcribe
uv run clipper resolve <video_id>                  # after clips.json is written
uv run clipper produce <video_id> [--only clip_01] [--fast]
uv run clipper finish <video_id>                   # delete downloaded media
uv run pytest                                      # unit tests
uv run pytest -m integration                       # needs ffmpeg-full + assets
```

Design: `docs/superpowers/specs/2026-11-07-clipper-design.md`. Research: `reports/Podcast clipper build research.md`.

## Posting to Instagram

Clips are posted by GitHub Actions from a queue; rendering stays local. Design: `docs/superpowers/specs/2026-11-07-instagram-posting-design.md`.

```bash
uv run clipper queue <video_id> [--only clip_01]   # upload rendered clips, add them to queue/pending/, commit and push
uv run clipper post-next --dry-run                 # needs IG_ACCESS_TOKEN in the environment; never publishes
```

The `post-next` workflow posts one clip per run (manual run: Actions → post-next → Run workflow). Dry run is checked by default; unchecking it, like any scheduled run, publishes live.
Run `clipper queue` on the `master` branch (the `queue_branch` setting in `config/publish.yaml`): the workflow only reads that branch, so the command refuses to commit anywhere else.
Queue folders: `queue/pending/`, `queue/posted/` (with the Instagram permalink) and `queue/failed/`.
If a run reports that the token was rejected, generate a new one in the Meta App Dashboard (Use cases → Manage messaging & content on Instagram → Customize → API setup with Unified login → Generate token) and update the `IG_ACCESS_TOKEN` secret.
