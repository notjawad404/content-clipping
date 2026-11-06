---
name: clipper
description: Use when the user gives a YouTube podcast or video link and wants short vertical clips (Reels, TikTok, Shorts, X) found, cut, captioned and edited. Runs the local clipper pipeline in this repo; Claude chooses and scores the moments and writes the post copy.
---

# Clipper

Turns one YouTube link into finished 1080×1920 clips plus ready-to-paste post captions. Code downloads, transcribes, reframes and renders. **You** choose the moments, score them, write the hook text and post copy, and check the result visually.

Run every command from the repo root with `uv run`. Commands are resumable: rerunning skips finished work.

## 0. Preflight

Run `uv run clipper doctor`. If anything fails, run the printed fix (`brew install ffmpeg-full`, `uv sync`, `bash scripts/setup_assets.sh`) and run doctor again. Do not continue until every check passes.

## 1. Read the request

- **URL** (required). One link per run.
- **Campaign:** if the user names one, it must exist as `config/campaigns/<name>.yaml`. If it doesn't, ask for the brief's rules (creator tag, required caption text, required hashtags, length limits, banned topics) and create the file by copying `config/campaigns/example.yaml`.
- **Tweaks** go into `jobs/<video_id>/overrides.yaml`. Write it after `prepare` creates the folder and before `resolve`:

| User says | overrides.yaml |
|---|---|
| "under 30 seconds" | `length: {max: 30, target_max: 30}` |
| "under 15 seconds" | `length: {min: 8, max: 15, target_min: 8, target_max: 15}` |
| "only the best 3" / "just the best clip" | `max_clips: 3` / `max_clips: 1` |
| "no sound effects" | `sfx: {enabled: false}` |
| "no zooms" | `zoom: {enabled: false}` |
| "blue captions" (any colour) | `captions: {highlight_color: "#2D9CFF"}` (pick a fitting hex) |
| "review first" / "let me approve" | `review_first: true` |
| "fast render" | pass `--fast` to `produce` |

## 2. Prepare

`uv run clipper prepare "<url>" [--campaign <name>]`: run it with `run_in_background: true` (a 1-2 hour episode needs audio download plus transcription, and the first run also downloads the ~1.2 GB Parakeet model, so it can exceed the Bash timeout), then wait for it to finish.

It prints JSON with `video_id`, the transcript path and where to write `clips.json`. The campaign and cookies choice are remembered in `job.json`, so rerunning `prepare` without those flags keeps them. If the error mentions a YouTube bot check, STOP and ask the user whether to retry with `--cookies-from-browser chrome` (YouTube may flag the Google account).

## 3. Select clips (your job)

Read `jobs/<video_id>/meta.json`, the campaign file (if any), `overrides.yaml` (if any) and the WHOLE `sentences.txt`. Read all of it, in chunks if needed. Never sample. Each line is `S0412 [1:23:45] text`.

1. **Candidates:** list 2–3× `max_clips` candidate moments. For each, quote its opening line and name its hook type: bold claim, surprising fact or number, story opener, contrarian take, direct question, emotional confession, practical tip.
2. **Tighten:** start exactly on the hook sentence (skip preamble, "so", "yeah", throat-clearing). End on the payoff or punchline sentence. Aim for 30–60 s; allowed range is `length.min`–`length.max` (default 20–90 s). Estimate length from the timestamps.
3. **Hard gates.** Drop the candidate if any fails:
   - Standalone: a stranger understands it with zero context (no unresolved "he", "that thing", "like I said").
   - Complete thought with a payoff.
   - Length within range.
   - Respects the campaign (no banned topics).
4. **Score** each survivor 1–5 on `hook` (first 3 s), `standalone`, `payoff`, `emotion` (emotion or controversy), `novelty` (new information or value), `shareability` (would someone send this to a friend?). `score` = (mean of the six ÷ 5) × 10, one decimal.
5. **Rank and pick:** highest score first, no two clips overlapping by more than half, prefer topic variety, keep at most `max_clips` with `score` ≥ `min_score`.

Write `jobs/<video_id>/clips.json`:

```json
{
  "video_id": "<video_id>",
  "clips": [
    {
      "id": "clip_01",
      "start_sentence": "S0412",
      "end_sentence": "S0419",
      "hook_text": "NOBODY TALKS ABOUT THIS",
      "title": "Why going viral means doing what's never been done",
      "score": 8.7,
      "scores": {"hook": 5, "standalone": 4, "payoff": 5, "emotion": 4, "novelty": 4, "shareability": 4},
      "reason": "Bold claim opener, concrete example, punchline at the end.",
      "emphasis_words": ["viral", "never", "million"],
      "post": {
        "instagram": "He spent $1M to learn this 👀 #podcast #business",
        "tiktok": "The $1M lesson nobody tells you #podcast",
        "youtube": "The $1M lesson nobody tells you",
        "x": "Spent $1M to learn this one thing."
      }
    }
  ]
}
```

Field rules:
- `start_sentence` / `end_sentence`: IDs from `sentences.txt`. Never write timestamps.
- `id`: `clip_01`, `clip_02`, … in rank order.
- `hook_text`: 3–8 punchy words shown on screen for the first 2.5 s. Not the same as the first spoken words.
- `emphasis_words`: 2–6 single lowercase words from the clip worth highlighting (numbers, names, emotional words).
- `post.*`: one caption per platform: a short hook line, one sentence of context, up to 3 hashtags. Put hashtags only at the end of each caption. Code appends the campaign's required text, creator tag and required hashtags and caps hashtags at 5, so don't repeat them. X must fit 280 characters.

## 4. Resolve

`uv run clipper resolve <video_id>` prints `OK`/`SKIP` per clip.
- Schema error: fix `clips.json` and rerun.
- Clips skipped and you have strong unused candidates: add them with new ids and rerun.
- If every clip is skipped, read the SKIP reasons, adjust boundaries or picks in `clips.json`, and resolve again.
- If it prints `review_first: true`: show the user a table (id, score, length, title, hook text, source time) and STOP until they approve or edit. Apply edits to `clips.json` and resolve again.

## 5. Produce

`uv run clipper produce <video_id>`: run it with `run_in_background: true` because 8 clips can exceed the 10-minute command limit, then wait for it to finish. One clip only: `--only clip_03`. The JSON output lists `results` (`null` = success) and `qa_frames`.

If a result mentions a YouTube bot check, produce has stopped fetching (remaining clips show `skipped: YouTube bot check`). Ask the user, then rerun `uv run clipper prepare "<url>" --cookies-from-browser chrome` (the campaign is remembered and everything else is cached) and rerun produce.

## 6. QA (your job)

Open every QA frame image with the Read tool. For each clip check:
- the speaker's face is in frame and not cut off;
- captions are readable, inside the frame and not covering the face;
- the hook box is visible at the top in the first frame;
- no black or frozen frames.

To fix, edit `overrides.yaml` (e.g. `captions: {y: 1180}`). It is global for the job, so a fix made for one clip also applies to any later re-render of the other clips. Rerun once with `uv run clipper produce <video_id> --only clip_XX --force render` (or `--force reframe render` for framing problems). If it is still wrong, report it. Never hide a failure.

## 7. Finish

Run `uv run clipper finish <video_id>` (deletes downloaded audio and video, keeps transcripts). Then tell the user:
- the folder `output/<video_id>/` and, per clip: score, length, title; plus any failed or skipped clips and why (see `summary.md`);
- each `clip_XX_post.md` holds the ready-to-paste caption for every platform;
- Content Rewards reminder: post natively on each platform, submit the post link within 30 minutes, and don't edit the post after submitting.
