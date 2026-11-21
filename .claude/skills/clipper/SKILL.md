---
name: clipper
description: Use when the user gives a YouTube podcast, gaming (e.g. GTA 6 news, trailer breakdowns, gameplay commentary) or other video link and wants short vertical clips (Reels, TikTok, Shorts, X) found, cut, captioned and edited, and by default posted to YouTube Shorts (Instagram too when an account is linked in config/publish.yaml). Runs the local clipper pipeline in this repo; Claude chooses and scores the moments and writes the post copy.
---

# Clipper

Turns one YouTube link into finished 1080×1920 clips plus ready-to-paste post captions, and by default posts them to YouTube Shorts (and Instagram when `ig_account_id` is set in `config/publish.yaml`). Code downloads, transcribes, reframes, renders and posts. **You** choose the moments, score them, write the hook text and post copy, and check the result visually.

**Default when the user only pastes a link:** make up to 5 clips, then post every clip that passes right away (section 7), with no further questions, unless older clips are already waiting in the queue (then section 7 defers posting to the cron) or the user said not to post, or is asking for a change to existing clips (see Mode in section 1; then you stop after QA and post nothing). Apart from those, only stop for the cases named below: a YouTube bot check, `review first`, a named campaign that does not exist, or a failed step.

Run every command from the repo root with `uv run`. Commands are resumable: rerunning skips finished work.

## 0. Preflight

Run `uv run python -m clipper doctor`. If anything fails, run the printed fix (`brew install ffmpeg-full` or `winget install yt-dlp.FFmpeg`, `uv sync`, `bash scripts/setup_assets.sh`) and run doctor again. Do not continue until every check passes.

Then check, before any download, that posting will work, so a problem shows up in the first minute and not after the render:
- `gh auth status` succeeds. If not, tell the user to run `gh auth login` and stop.
- `git branch --show-current` prints `master` (queueing only works there). If not, run `git checkout master`; if that fails because of local changes, stop and tell the user.

## 1. Read the request

- **URL** (required). One link per run.
- **Count:** if the user names one ("only 3", "10 clips", "just the best clip"), use it (`max_clips: N` in overrides.yaml). Otherwise 5.
- **Long videos (over 70 min):** pick per hour instead of across the whole video. Split the timeline into hour windows that overlap by 5 min on each side (0:00–1:05, 0:55–2:05, 1:55–3:05, …; the last window ends at the video's end), so a moment that straddles an hour mark is still seen whole. The count above applies to each window, and `max_clips` in overrides.yaml is that count × the number of windows. A clip counts toward the hour its start falls in (the overlap only lets a clip that starts just before an hour mark run past it); never pick the same moment twice. An hour with little speech may get fewer clips.
- **Mode:** if the user says "schedule them", "spread them out" or "through the day", only queue the clips; the cron runs once a day at about 6:40 AM US Eastern (11:41 UTC), uploading the next 5 clips at once as private so the user can schedule them in YouTube Studio. **Do not post** if the user says so ("just make the clips", "don't post", "I'll post it myself"), or if the request is a follow-up change to clips that already exist in `jobs/` (re-render, new captions, different tweaks) rather than a link for a fresh run: then stop after QA (section 6) and run neither `queue` nor `post-now` unless the user asks. Section 8 then reports the clips as made but not posted. If a clip you re-rendered or changed is already in `queue/pending/` (check with `ls queue/pending 2>/dev/null` after `git pull --rebase --autostash`), tell the user the queued OLD version will still be posted by the cron at its slot, and offer to hold it (the hold recipe in section 7, step 5) and then queue the new render; do not hold or re-queue anything unless the user asks. Anything else means post now, unless older clips are already waiting in the queue (see section 7).
- **Campaign:** if the user names one, it must exist as `config/campaigns/<name>.yaml`. If it doesn't, ask for the brief's rules (creator tag, required caption text, required hashtags, length limits, banned topics) and create the file by copying `config/campaigns/example.yaml`. If the user names none, choose from the video after `prepare` has written `meta.json`: read every `config/campaigns/*.yaml` except `example.yaml` and compare each file's creator tag, required text, `brief:` (if present), name and comments with the video's channel, title and description. A campaign matches ONLY when the video's channel, creator or show is the one the campaign names or is about. A match on topic alone does not count. If exactly one campaign matches, use it; if none or more than one match, use none (and if more than one matched, say so in the final report, naming them). If a campaign file names a specific episode, title or link ("only clips from this video/link"), it matches ONLY that exact video (same URL or title), never other episodes of the same show. The user naming a campaign always wins. If one applies, run `uv run python -m clipper prepare "<url>" --campaign <name>` again (everything is cached, so it takes seconds) before selecting clips. After `prepare`, report the campaign actually in force by reading the `campaign` field of `jobs/<video_id>/job.json` (a previous run of the same video keeps its campaign, so do not assume "none" if job.json says otherwise). Remember which campaign is in force, and why; you report it at the end.
- **Genre:** after `prepare`, decide from `meta.json` (title, channel, description, chapters) and the first lines of `sentences.txt` whether this is a **gaming** video: gameplay, a game trailer or trailer breakdown, game news, leaks/rumours coverage, a streamer or let's-play, a review or a guide (GTA 6 videos are the typical case). The user saying "gaming" always wins. For gaming, start `overrides.yaml` from the contents of `config/genres/gaming.yaml` (whole-frame framing, captions below the gameplay, 15–60 s clips) and put any user tweaks after them, so the user's values win. Select with the gaming rules in section 3. Anything else uses the default podcast rules.
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

If a campaign applies, see the Campaign rule in section 1; apply it right after `prepare` and before selecting clips.

`uv run python -m clipper prepare "<url>" [--campaign <name>]`: run it with `run_in_background: true` (a 1-2 hour episode needs audio download plus transcription, and the first run also downloads the transcription model, ~1.2 GB Parakeet on macOS or ~1.5 GB Whisper elsewhere, so it can exceed the Bash timeout), then wait for it to finish.

It prints JSON with `video_id`, the transcript path and where to write `clips.json`. The campaign and cookies choice are remembered in `job.json`, so rerunning `prepare` without those flags keeps them. If the error mentions a YouTube bot check, STOP and ask the user whether to retry with `--cookies-from-browser chrome` (YouTube may flag the Google account).

## 3. Select clips (your job)

Read `jobs/<video_id>/meta.json`, the campaign file (if any), `overrides.yaml` (if any) and the WHOLE `sentences.txt`. Read all of it, in chunks if needed. Never sample. Each line is `S0412 [1:23:45] text`.

1. **Candidates:** list 2–3× `max_clips` candidate moments (for long videos, 2–3× the per-window count in each window). For each, quote its opening line and name its hook type: bold claim, surprising fact or number, story opener, contrarian take, direct question, emotional confession, practical tip.
2. **Tighten:** start exactly on the hook sentence (skip preamble, "so", "yeah", throat-clearing). End on the payoff or punchline sentence. Aim for 30–60 s; allowed range is `length.min`–`length.max` (default 20–90 s). Estimate length from the timestamps.
3. **Hard gates.** Drop the candidate if any fails:
   - Standalone: a stranger understands it with zero context (no unresolved "he", "that thing", "like I said").
   - Complete thought with a payoff.
   - Length within range.
   - Respects the campaign (no banned topics).
4. **Score** each survivor 1–5 on `hook` (first 3 s), `standalone`, `payoff`, `emotion` (emotion or controversy), `novelty` (new information or value), `shareability` (would someone send this to a friend?). `score` = (mean of the six ÷ 5) × 10, one decimal.
5. **Rank and pick:** highest score first, no two clips overlapping by more than half, prefer topic variety, keep at most `max_clips` with `score` ≥ `min_score` (for long videos, at most the per-window count from each window).

### Gaming videos

Use these in place of steps 1–4 above when the genre is gaming. Steps 5 and the `clips.json` format stay the same.

- **Speech check first.** You only see what is said, not the picture. If `sentences.txt` averages fewer than one sentence per 20 s of video (a music-only trailer, silent gameplay), STOP and tell the user this video has too little commentary to pick moments from, before writing `clips.json`.
- **Candidates and hook types:** reveal or news drop ("Rockstar just confirmed…"), hidden detail ("nobody noticed this in the trailer"), hype or shock reaction (a streamer losing it, "NO WAY"), hot take or prediction (price, release date, map size), comparison (GTA 6 vs GTA 5 / RDR2), rumour check (true or fake?), fail or clutch moment the commentator calls out, tip or secret (easter egg, money glitch, hidden location). Quote the opening line for each.
- **Tighten harder than for podcasts.** Gaming viewers swipe in about 1 s: start on the reveal, the reaction or the claim itself, never on "so guys", "what's up", intros, sponsor reads, "like and subscribe" or channel plugs. End right after the payoff (the reveal shown, the reaction peak, the verdict). Aim for 20–45 s within `length.min`–`length.max`.
- **Hard gates.** Drop the candidate if any fails:
  - Standalone: a gamer who did not watch the video gets it (name the game and the thing being shown; no unresolved "this one", "over here", "like I said earlier").
  - Something is shown or said that pays off: a reveal, a reaction peak, a verdict, a tip.
  - Not a sponsor segment, giveaway, merch or channel plug, and not a "what's up guys" intro.
  - Not presented as leaked or unreleased footage, and does not rely on clearly leaked material (publishers such as Rockstar take these down); speculation about leaks in the creator's own words is fine.
  - Length within range, and respects the campaign (no banned topics).
- **Score** the same six keys, read for gaming: `hook` (first 1–3 s grabs a gamer), `standalone`, `payoff` (the reveal or reaction lands), `emotion` (hype, shock, outrage, laughter), `novelty` (new info, detail or take most fans have not seen), `shareability` (would a fan send it to their group chat or argue in the comments?). Same formula.
- **Hook text:** 3–7 words in gamer language that tease the payoff without giving it away ("GTA 6 MAP IS HUGE", "YOU MISSED THIS DETAIL", "ROCKSTAR CONFIRMED IT"). Never claim something the clip does not show (no "LEAKED GAMEPLAY" or "RELEASE DATE CONFIRMED" unless it really is).
- **`emphasis_words`:** game and character names, numbers (prices, dates, map sizes), and reaction words.
- **`post.*`:** name the game in the first line, tease the moment, end with up to 3 hashtags such as `#GTA6 #gaming #gta`. Never present the post as official or as coming from the game's publisher, and credit the creator when a campaign requires it.

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

`uv run python -m clipper resolve <video_id>` prints `OK`/`SKIP` per clip.
- Schema error: fix `clips.json` and rerun.
- Clips skipped and you have strong unused candidates: add them with new ids and rerun.
- If every clip is skipped, read the SKIP reasons, adjust boundaries or picks in `clips.json`, and resolve again.
- If it prints `review_first: true`: show the user a table (id, score, length, title, hook text, source time) and STOP until they approve or edit. Say that approving means the clips will then be posted publicly (unless the user asked to schedule or not to post). Apply edits to `clips.json` and resolve again.

## 5. Produce

`uv run python -m clipper produce <video_id>`: run it with `run_in_background: true` because a batch of clips can exceed the 10-minute command limit, then wait for it to finish. One clip only: `--only clip_03`. The JSON output lists `results` (`null` = success) and `qa_frames`.

If a result mentions a YouTube bot check, produce has stopped fetching (remaining clips show `skipped: YouTube bot check`). Ask the user, then rerun `uv run python -m clipper prepare "<url>" --cookies-from-browser chrome` (the campaign is remembered and everything else is cached) and rerun produce.

## 6. QA (your job)

Open every QA frame image with the Read tool. For each clip check:
- the speaker's face is in frame and not cut off (gaming: the whole gameplay frame is visible instead);
- captions are readable, inside the frame and not covering the face (gaming: not covering the gameplay, the HUD or the minimap);
- gaming: the frames actually show what the hook text promises; if they don't, fix `hook_text` or drop the clip;
- the hook box is visible at the top in the first frame;
- no black or frozen frames.

To fix, edit `overrides.yaml` (e.g. `captions: {y: 1180}`). It is global for the job, so a fix made for one clip also applies to any later re-render of the other clips. Rerun once with `uv run python -m clipper produce <video_id> --only clip_XX --force render` (or `--force reframe render` for framing problems). If it is still wrong, report it. Never hide a failure. A clip that still fails the visual check after that one fix attempt is not posted; note it so it can be reported.

## 7. Queue and post

Skip this section if the user asked not to post or is asking for a change to existing clips (section 1, Mode). Only clips that passed QA go forward.

0. If no clip passed QA (or none cleared the quality bar), STOP: do not run `queue` or `post-now`. Still run `finish` and give the section 8 report (nothing posted, with the reason).
1. Run `git pull --rebase --autostash` (the workflow's bot keeps moving queue entries), then list pending entries with `ls queue/pending 2>/dev/null` (the directory does not exist until something is queued; a missing or empty directory means no older entries, N=0). Entries are named `<video_id>_clip_NN.json`. "Older entries" = any file there whose name does not start with `<video_id>_` (entries of THIS video from an earlier partial run do not count as older). Note the count N.
2. Run `uv run python -m clipper queue <video_id> --only <passing clip ids>`; it uploads each clip and commits the queue entries, and only works on `master`. If it refuses (wrong branch) or exits non-zero, report exactly what it printed. If some clips were queued and others failed, rerun the same `queue` command ONCE (it is idempotent: already-queued clips are skipped and the push is retried); if it still fails, report exactly what it printed and say which clips are queued and which are missing. Do not run `post-now` after a partial failure unless every clip that passed QA is queued; otherwise the user gets a partial set posted silently. If `queue` prints `skipped: already queued` for a clip that is already in `queue/posted/` (posted earlier), tell the user that clip was NOT re-posted.
3. **Mode.** Post now ONLY IF the user did not ask to schedule AND there were no older entries: run `uv run python -m clipper post-now` with `run_in_background: true` (each post takes about two minutes, so five clips take about ten; a foreground run would be killed by the default 2-minute timeout while the workflow still posts) and wait for it to finish. It prints `posted <id>: <link>` for each clip and stops at the first failure.
   Otherwise (the user asked to schedule, OR older entries exist) stop after `queue`. If older entries exist, tell the user the clips are queued behind N older entries and that the cron runs once a day at about 6:40 AM US Eastern (11:41 UTC), uploading the next 5 clips at once as private so the user can schedule them in YouTube Studio (oldest first), so the new clips go out after the older ones, and say explicitly: "posting is deferred to the cron because N older clips are already waiting; say 'post everything now' if you want them all posted immediately." If N = 0 (schedule mode only), do not mention older entries: say the clips are queued and the cron runs once a day at about 6:40 AM US Eastern (11:41 UTC), uploading the next 5 clips at once as private so the user can schedule them in YouTube Studio. Queued clips are publicly downloadable from the clips repo until they post. If the user then says "post everything now", run `uv run python -m clipper post-now` with `run_in_background: true` and wait for it to finish.
4. If `post-now` stops with an error, report it with the run link it printed. Do not retry in a loop. Clips already posted stay posted and the rest stay queued; running `uv run python -m clipper post-now` again (with `run_in_background: true`, waiting for it to finish) continues from the queue.
5. Whenever you stop while entries from this run are in `queue/pending/` (partial failure, a `post-now` error, deferral), name those entries and say the cron uploads up to 5 clips per daily run (once a day at about 6:40 AM US Eastern (11:41 UTC), uploading the next 5 clips at once as private so the user can schedule them in YouTube Studio), oldest first, starting at the next run, so these go out after any older entries, unless the user asks to hold them. Holding means, on `master` only: `git pull --rebase --autostash` (the workflow bot moves queue entries), then `git rm queue/pending/<id>.json`, commit, push. Do this only if the user asks.

## 8. Finish

Run `uv run python -m clipper finish <video_id>` (deletes downloaded audio and video, keeps transcripts). Then tell the user:
- each posted link (YouTube Shorts, plus the Reel when Instagram is linked), one per clip with its title and score; if posting was deferred (schedule mode or older clips waiting), which clips are queued and when the cron will post them;
- the campaign used (or "none") and why;
- how many clips cleared the quality bar if that is fewer than requested, and any clip that was skipped or failed and why (see `summary.md`);
- the folder `output/<video_id>/`, where each `clip_XX_post.md` holds the ready-to-paste caption for every platform;
- if the clips were made but not posted (the user said not to post, or it was a follow-up change), say so: they are made, not posted. If a changed clip is still in `queue/pending/`, say that the queued OLD version will still be posted by the cron at its slot, and offer to hold it and queue the new render (do nothing unless the user asks);
- Content Rewards reminder: for clips posted right away, submit the post links within 30 minutes, and don't edit the posts after submitting. When posting was deferred or scheduled, posts go out unattended at the cron slots, so check `queue/posted/` (or the profile) after each slot and submit each link promptly once it is live.
