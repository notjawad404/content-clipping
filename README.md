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

In Claude Code, in this folder:

> Run the clipper on https://www.youtube.com/watch?v=… for the `<campaign>` campaign

Add tweaks in plain words: "only the best 3", "under 30 seconds", "no zooms", "blue captions", "review first". Clips have no sound effects.

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

The `post-next` workflow posts one clip per run (manual run: Actions → post-next → Run workflow; keep **dry run** on to test).
Queue folders: `queue/pending/`, `queue/posted/` (with the Instagram permalink) and `queue/failed/`.
If a run reports that the token was rejected, generate a new one in the Meta App Dashboard (Use cases → Manage messaging & content on Instagram → Customize → API setup with Unified login → Generate token) and update the `IG_ACCESS_TOKEN` secret.
