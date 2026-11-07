---
name: clipper
description: Use when the user gives a YouTube podcast or video link and wants short vertical clips (Reels, TikTok, Shorts, X) found, cut, captioned and edited, and by default posted to Instagram. Runs the local clipper pipeline in this repo; Claude chooses and scores the moments and writes the post copy.
---

# Clipper

Turns one YouTube link into finished 1080×1920 clips plus ready-to-paste post captions, and by default posts them to Instagram. Code downloads, transcribes, reframes, renders and posts. **You** choose the moments, score them, write the hook text and post copy, and check the result visually.

**Default when the user only pastes a link:** make up to 5 clips, then post every clip that passes to Instagram right away (section 7), with no further questions. Only stop for the cases named below: a YouTube bot check, `review first`, or a failed step.

Run every command from the repo root with `uv run`. Commands are resumable: rerunning skips finished work.

## 0. Preflight

Run `uv run clipper doctor`. If anything fails, run the printed fix (`brew install ffmpeg-full`, `uv sync`, `bash scripts/setup_assets.sh`) and run doctor again. Do not continue until every check passes.

Then check, before any download, that posting will work, so a problem shows up in the first minute and not after the render:
- `gh auth status` succeeds. If not, tell the user to run `gh auth login` and stop.
- `git branch --show-current` prints `master` (queueing only works there). If not, run `git checkout master`; if that fails because of local changes, stop and tell the user.

## 1. Read the request

- **URL** (required). One link per run.
- **Count:** if the user names one ("only 3", "10 clips", "just the best clip"), use it (`max_clips: N` in overrides.yaml). Otherwise 5.
- **Mode:** if the user says "schedule them", "spread them out" or "through the day", only queue the clips; the cron posts one clip per run at 09:00, 13:00 and 19:00 UTC (3 a day). Anything else means post now.
- **Campaign:** if the user names one, it must exist as `config/campaigns/<name>.yaml`. If it doesn't, ask for the brief's rules (creator tag, required caption text, required hashtags, length limits, banned topics) and create the file by copying `config/campaigns/example.yaml`. If the user names none, choose from the video after `prepare` has written `meta.json`: read every `config/campaigns/*.yaml` except `example.yaml` and compare each file's creator tag, required text, name and comments with the video's channel, title and description. Pick a campaign only on a clear match (the creator or show is named, or the campaign is plainly about the video's topic); otherwise use none. If one applies, run `uv run clipper prepare "<url>" --campaign <name>` again (everything is cached, so it takes seconds) before selecting clips. Remember which campaign you used, or that you used none, and why; you report it at the end.
- **Tweaks** go into `jobs/<video_id>/overrides.yaml`. Write it after `prepare` creates the folder and before `resolve`:

| User says | overrides.yaml |
|---|---|
| "under 30 seconds" | `length: {max: 30, target_max: 30}` |
| "under 15 seconds" | `length: {min: 8, max: 15, target_min: 8, target_max: 15}` |
| "only the best 3" / "just the best clip" | `max_clips: 3` / `max_clips: 1` |
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

`uv run clipper produce <video_id>`: run it with `run_in_background: true` because a batch of clips can exceed the 10-minute command limit, then wait for it to finish. One clip only: `--only clip_03`. The JSON output lists `results` (`null` = success) and `qa_frames`.

If a result mentions a YouTube bot check, produce has stopped fetching (remaining clips show `skipped: YouTube bot check`). Ask the user, then rerun `uv run clipper prepare "<url>" --cookies-from-browser chrome` (the campaign is remembered and everything else is cached) and rerun produce.

## 6. QA (your job)

Open every QA frame image with the Read tool. For each clip check:
- the speaker's face is in frame and not cut off;
- captions are readable, inside the frame and not covering the face;
- the hook box is visible at the top in the first frame;
- no black or frozen frames.

To fix, edit `overrides.yaml` (e.g. `captions: {y: 1180}`). It is global for the job, so a fix made for one clip also applies to any later re-render of the other clips. Rerun once with `uv run clipper produce <video_id> --only clip_XX --force render` (or `--force reframe render` for framing problems). If it is still wrong, report it. Never hide a failure. A clip that still fails the visual check after that one fix attempt is not posted; note it so it can be reported.

## 7. Queue and post

Only clips that passed QA go forward.

1. `uv run clipper queue <video_id> --only <passing clip ids>` uploads each clip and commits the queue entries. It only works on `master`.
2. **Post now (default):** run `uv run clipper post-now` with `run_in_background: true` (each post takes about two minutes, so five clips take about ten) and wait for it to finish. It prints `posted <id>: <link>` for each clip and stops at the first failure. **Schedule mode:** stop after step 1 and tell the user the cron posts one clip at 09:00, 13:00 and 19:00 UTC.
3. If `post-now` stops with an error, report it with the run link it printed. Do not retry in a loop. Clips already posted stay posted and the rest stay queued; running `uv run clipper post-now` again continues from the queue.
4. If `post-now` also posted clips from older videos (their ids appear in its output), say so.

## 8. Finish

Run `uv run clipper finish <video_id>` (deletes downloaded audio and video, keeps transcripts). Then tell the user:
- each posted Reel link, one per clip with its title and score; in schedule mode, which clips are queued and when the cron will post them;
- the campaign used (or "none") and why;
- how many clips cleared the quality bar if that is fewer than requested, and any clip that was skipped or failed and why (see `summary.md`);
- the folder `output/<video_id>/`, where each `clip_XX_post.md` holds the ready-to-paste caption for every platform;
- Content Rewards reminder: submit the post links within 30 minutes, and don't edit the posts after submitting.
