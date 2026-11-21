# Clipper

Local podcast clipper for Claude Code: paste a YouTube link, get finished 1080×1920 clips for Instagram Reels, TikTok, YouTube Shorts and X, with per-platform post captions.

## Setup (once)

macOS (Apple Silicon, transcribes with parakeet-mlx):

```bash
brew install ffmpeg-full
uv sync
bash scripts/setup_assets.sh
uv run python -m clipper doctor
```

Windows (transcribes with faster-whisper on the CPU, or CUDA with `CLIPPER_WHISPER_DEVICE=cuda`):

```powershell
winget install astral-sh.uv yt-dlp.FFmpeg OpenJS.NodeJS.LTS Python.Python.3.12
uv venv --python "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
uv sync
bash scripts/setup_assets.sh        # from Git Bash
uv run python -m clipper doctor
```

The venv is built from the python.org Python because Smart App Control blocks uv's own unsigned Python and the `clipper.exe`/`pytest.exe` wrappers; that is also why every command here uses `python -m`. The Whisper model defaults to `distil-large-v3` (override with `CLIPPER_WHISPER_MODEL`) and is downloaded on the first `prepare`.

## Use

In Claude Code, in this folder, paste a YouTube link:

> https://www.youtube.com/watch?v=…

By default Claude makes up to 5 clips (for videos over 70 min, up to 5 per hour, read in hour windows that overlap by 5 min) and posts every clip that passes to YouTube Shorts (and Instagram, when an account is linked), then lists the links. If older clips are already waiting in the queue, new clips are queued behind them and posted by the cron instead of immediately. Add plain-word changes: a count ("only 3", "10 clips"), "schedule them" or "spread them through the day" (queue only; the cron posts 2 a day, around 3 PM and 9 PM US Eastern), "campaign `<name>`" (otherwise Claude picks one from the video only on a clear match), "just make the clips" or "don't post" (makes the clips without posting them), "under 30 seconds", "no zooms", "blue captions", "review first". Clips have no sound effects.

Posting needs `gh auth login` and the `master` branch checked out. If posting stops with an error, run `uv run python -m clipper post-now` to continue from the queue (it also posts clips from other videos that are waiting in the queue).

Clips land in `output/<video_id>/`: `clip_XX.mp4`, `clip_XX_post.md` (captions per platform) and `summary.md`.

## Gaming videos

Gaming links (GTA 6 news, trailer breakdowns, gameplay commentary, streamers) are detected from the video's metadata, or say "gaming". Claude then picks moments with gaming rules (reveals, hidden details, reactions, hot takes; no intros, sponsor reads or leaked footage) and starts the job from `config/genres/gaming.yaml`: the whole gameplay frame over a blurred fill (`framing: {mode: fit}`) instead of cropping to a face or facecam, captions below the gameplay, and 15–60 s clips. Moments are found from what is said, so videos with no commentary (music-only trailers, silent gameplay) are not clipped.

## Campaigns

Copy `config/campaigns/example.yaml` to `config/campaigns/<name>.yaml` and fill in the brief's creator tag, required text and hashtags, and length limits.

## Manual commands

```bash
uv run python -m clipper prepare "<url>" --campaign <name>   # download audio + transcribe
uv run python -m clipper resolve <video_id>                  # after clips.json is written
uv run python -m clipper produce <video_id> [--only clip_01] [--fast]
uv run python -m clipper finish <video_id>                   # delete downloaded media
uv run python -m pytest                                      # unit tests
uv run python -m pytest -m integration                       # needs ffmpeg-full + assets
```

Design: `docs/superpowers/specs/2026-11-07-clipper-design.md`. Research: `reports/Podcast clipper build research.md`.

## Posting

Clips are posted by GitHub Actions from a queue; rendering stays local. Design: `docs/superpowers/specs/2026-11-07-instagram-posting-design.md`.

```bash
uv run python -m clipper queue <video_id> [--only clip_01]   # upload rendered clips, add them to queue/pending/, commit and push
uv run python -m clipper post-next --dry-run                 # needs the YT_* (and IG_ACCESS_TOKEN, if linked) variables; never publishes
```

The `post-next` workflow posts one clip per run (manual run: Actions → post-next → Run workflow). Dry run is checked by default; unchecking it, like any scheduled run, publishes live.
Run `clipper queue` on the `master` branch (the `queue_branch` setting in `config/publish.yaml`): the workflow only reads that branch, so the command refuses to commit anywhere else.
Queue folders: `queue/pending/`, `queue/posted/` (with the post links) and `queue/failed/`.
Instagram is off while `ig_account_id` is absent from `config/publish.yaml`; add the account id back (and the `IG_ACCESS_TOKEN` secret) to post Reels again.
If a run reports that the token was rejected, generate a new one in the Meta App Dashboard (Use cases → Manage messaging & content on Instagram → Customize → API setup with Unified login → Generate token) and update the `IG_ACCESS_TOKEN` secret.
