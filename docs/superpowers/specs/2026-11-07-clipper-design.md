# Clipper — Design Spec (v1)

**Date:** 2026-11-07
**Status:** Approved in brainstorming; pending written-spec review
**Research basis:** `reports/Podcast clipper build research.md` and `research_notes/Podcast clipper build research/`

## 1. Goal

Paste one YouTube podcast link into Claude Code and get back finished, post-ready 9:16 clips (1080×1920) for Instagram Reels, TikTok, YouTube Shorts and X, each with a ready-to-paste post caption per platform.

Context: the user clips English-language podcasts for **Content Rewards** campaigns (creator-authorized clipping, paid per 1,000 views). Footage comes from **YouTube links**. Each campaign brief has its own rules (required tags/text, length, platforms, banned content); missing required text is an official rejection reason, so campaign rules are first-class config.

### Success criteria
- One prompt ("run the clipper on <link>") produces up to 8 finished clips with no further input in default mode.
- A 2-hour episode completes end-to-end in roughly 30 minutes or less on the user's M1 (to be verified by benchmark).
- Every clip: starts on a hook, ends on a payoff, is understandable without context, 20–90 s, captions inside the cross-platform safe zone, no mid-word cuts, speaker framed correctly.
- Every post caption contains the campaign's required text and ≤ 5 hashtags.

### Out of scope for v1
Auto-posting (Publisher), automatic video discovery (Researcher), before/after and timeline variants, batch/multi-link queue, Google Drive or local-file input, automatic brand-color detection, emoji, B-roll, smooth animated zooms, speaker diarization.

## 2. Environment constraints

| Item | Value | Consequence |
|---|---|---|
| Machine | Apple M1, 16 GB RAM | MLX models run on GPU; no CUDA tools |
| Free disk | ~17 GB (92% full) | Audio-first download, section-only video fetch, auto-cleanup, 5 GB preflight guard |
| System Python | 3.9.6 | Too old for yt-dlp/mlx; use uv-managed Python 3.12 |
| Homebrew ffmpeg | plain formula lacks libass | Use `ffmpeg-full` (keg-only: `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`) |
| yt-dlp | needs JS runtime + EJS solver | Use the installed Node 22 via `--js-runtimes node`; install `yt-dlp[default]` (bundles the EJS solver). Deno not needed |
| Project path | contains a space ("Content Clipping") | All tool invocations pass paths as list args (no shell string building); job dirs use space-free names |

## 3. Architecture

Approach A: a Claude Code skill + a local Python package. **Claude does only judgment work** (clip selection, scoring, copy, visual QA). **Deterministic Python does everything else.** Each stage reads/writes files in a job folder so runs are resumable.

```
Content Clipping/
├── .claude/skills/clipper/SKILL.md     # orchestration instructions Claude follows
├── clipper/                            # Python package (uv, Python 3.12)
│   ├── cli.py          # `clipper <stage> <job>` entry points
│   ├── doctor.py       # environment + disk preflight
│   ├── fetch.py        # audio fetch, metadata, section video fetch
│   ├── transcribe.py   # parakeet-mlx → words.json, sentences.txt
│   ├── clips.py        # validate clips.json, map sentence IDs → times, snap boundaries
│   ├── reframe.py      # shot detection, face/mouth tracking, crop plan
│   ├── captions.py     # caption grouping + ASS generation
│   ├── render.py       # ffmpeg filtergraph build + run
│   ├── package.py      # post files, summary, cleanup
│   └── config.py       # style + campaign + run-override merging
├── assets/fonts/        # Montserrat (OFL)
├── assets/sfx/          # whoosh/pop (Mixkit/Pixabay, commercial use OK)
├── config/style.yaml    # default look
├── config/campaigns/<name>.yaml
├── jobs/<video_id>/     # working files (git-ignored)
├── output/<video_id>/   # finished clips (git-ignored)
└── tests/
```

### Stage pipeline

| # | Stage | Actor | Input → Output |
|---|---|---|---|
| 0 | doctor | code | — → pass/fail report (ffmpeg-full has libass, node ≥ 20, yt-dlp + EJS, models, ≥ 5 GB free) |
| 1 | fetch-audio | code | URL → `audio.m4a`, `meta.json` (title, channel, duration, chapters, video_id) |
| 2 | transcribe | code | audio → `words.json`, `sentences.txt` |
| 3 | select | **Claude** | `sentences.txt` + `meta.json` + campaign → `clips.json` |
| 3b | validate | code | `clips.json` → `clips.resolved.json` (times snapped, rejects listed) |
| — | *optional review pause* | user | approve/drop/adjust clips |
| 4 | fetch-video | code | resolved clips → `src/clip_XX.mp4` (1080p sections, ±2 s padding) |
| 5 | reframe | code | section video → `crops/clip_XX.json` |
| 6 | render | code | section + crops + words + style → `output/<id>/clip_XX.mp4` |
| 7 | QA | **Claude** | 3–4 still frames per clip → re-render failures (max 1 retry) |
| 8 | package | code + **Claude** copy | → `clip_XX_post.md`, `summary.md`; delete `jobs/<id>/audio*` and `src/` |

Each stage is skipped if its output exists and is newer than its inputs (resume on rerun). `--force <stage>` reruns from a stage.

## 4. Stage details

### 4.1 Fetch
- Audio: `yt-dlp -f bestaudio -x` → m4a (~100 MB for 2 h). Metadata via `--dump-json`.
- Video sections: `yt-dlp -f "bv*[height<=1080]+ba/b" --download-sections "*start-end" --force-keyframes-at-cuts` per clip, with 2 s padding each side (trimmed precisely at render).
- On bot-check failure: Claude asks the user before retrying with `--cookies-from-browser` (Google account risk per yt-dlp docs).

### 4.2 Transcribe
- `parakeet-mlx` with `mlx-community/parakeet-tdt-0.6b-v2` (English-only; word timestamps built in; default 120 s chunking keeps memory ~1.7 GB extra).
- `words.json`: `[{"i": 0, "w": "To", "s": 12.34, "e": 12.51}, …]`
- `sentences.txt`: one line per sentence, `S0412 [1:23:45] text…`. Sentence splitting on terminal punctuation, plus forced break on gaps > 1.2 s.
- `sentences.json` maps sentence ID → first/last word index.

### 4.3 Select (Claude)
Prompt order: transcript first, then metadata + campaign rules, then instructions (long-context best practice).

Process Claude follows (defined in SKILL.md):
1. Generate ~2–3× the target count of candidates; quote each candidate's opening line.
2. Tighten: start exactly on the hook (skip preamble/rambling), end on the payoff.
3. Hard gates (all must pass): standalone (no unresolved references to earlier context), complete thought with payoff, 20–90 s (target 30–60), complies with campaign rules.
4. Score six dimensions 1–5: hook strength (first 3 s), standalone clarity, payoff, emotion/controversy, novelty/value, shareability ("would someone send this?"). Overall = (mean of the six scores ÷ 5) × 10, rounded to one decimal.
5. Rank; drop clips overlapping another by > 50%; prefer topic diversity. Keep top `max_clips` (default 8) with score ≥ `min_score` (default 7.0).

`clips.json` contract (validated against `clipper/schemas/clips.schema.json`):
```json
{
  "video_id": "abc123",
  "clips": [
    {
      "id": "clip_01",
      "start_sentence": "S0412",
      "end_sentence": "S0419",
      "hook_text": "NOBODY TALKS ABOUT THIS",
      "title": "Why going viral means doing what's never been done",
      "score": 8.6,
      "scores": {"hook": 5, "standalone": 4, "payoff": 5, "emotion": 4, "novelty": 4, "shareability": 4},
      "reason": "Bold claim opener, concrete example, punchline at end.",
      "emphasis_words": ["viral", "never", "million"],
      "post": {
        "instagram": "…", "tiktok": "…", "youtube": "…", "x": "…"
      }
    }
  ]
}
```
Claude never writes timestamps; code derives them.

### 4.4 Validate & snap (code)
- Map sentence IDs → word indices → times.
- Start = first word start − 0.08 s; end = last word end + tail extended into the following silence (max 0.4 s), never past the next word's start.
- Recheck 20–90 s; out-of-range clips are rejected with a reason (not silently trimmed).
- Inject campaign `required_text` and `required_tags` into every `post.*` if missing; cap hashtags at 5 (campaign-required tags take priority).

### 4.5 Reframe
- Shot detection: PySceneDetect `ContentDetector(threshold=27)`; merge shots < 0.8 s into neighbours.
- Faces: MediaPipe Tasks `FaceLandmarker` (new Tasks API; `mp.solutions` is removed) sampled at 5 fps; mouth-open ratio per face per sample.
- Per shot layout decision:
  - 1 face → **fill**: 9:16 crop centred on face, eyes at ~1/3 from top.
  - 2+ faces, one dominant speaker → **fill** on the speaker (mouth-activity ratio ≥ 1.4× the other). Switch speaker only at a sentence boundary, minimum 1.5 s hold.
  - 2 faces, rapid alternation (within a window of ≥ 3 s, neither face reaches the 1.4× dominance ratio), both faces ≥ 65% of the larger face's size → **split**: two 9:8 crops, each scaled to 1080×960, stacked.
  - 0 faces → **fit**: full frame over blurred background (blur computed at 270×480 and upscaled for speed).
- Static crop within each segment (no panning); hard cut at shot boundaries.
- Output `crops/clip_XX.json`: `[{"start": 0.0, "end": 4.2, "layout": "fill", "boxes": [[x, y, w, h]]}, …]` with even integer dimensions, clamped to frame.

### 4.6 Captions & render
- **Captions (ASS via pysubs2):** all caps, Montserrat Black; groups of 2–3 words, ≤ 15 chars per line; white fill, thick black outline + shadow; the active word and `emphasis_words` in `highlight_color` (default `#FFE500`); each group pops in (scale 85% → 100% over 80 ms via `\t`). Whole-group pop, not per-word scaling (libass reflow limitation).
- **Safe zone (cross-platform):** captions and hook stay within y ∈ [270, 1250] and x ∈ [65, 960] (≥ 120 px right margin for TikTok/Reels action buttons). Default caption centre y ≈ 1130. In split layout, captions sit on the seam (y ≈ 960).
- **Hook text:** top box (y ≈ 330), shown 0–2.5 s.
- **Zooms:** hard-cut punch-ins, scale alternating 1.0 ↔ `zoom_scale` (default 1.18, range 1.12–1.25) centred on the face box; placed at sentence ends or emphasis words, spaced 4–7 s; reset at shot boundaries; never inside split layout.
- **SFX:** whoosh at each zoom, mixed at −18 dB relative to speech; then two-pass `loudnorm` to −14 LUFS integrated, −1 dBTP.
- **Single ffmpeg pass per clip** (ffmpeg-full): trim → per-segment crop/scale (+zoom) → concat → `ass` filter → audio mix + loudnorm → encode.
- **Export:** 1080×1920, 30 fps, H.264 High, yuv420p, `libx264 -crf 18 -preset medium`, AAC 48 kHz 192 kbps, `+faststart`. `fast: true` option uses `h264_videotoolbox -q:v 60`.

### 4.7 QA (Claude)
Extract frames at 0.5 s, 25%, 60%, 90% of each clip. Claude checks: face in frame and not cut off, captions readable and inside safe zone, hook text visible, no black/blank frames. Failures → adjust crop/style override and re-render once; persistent failures are reported in the summary, not hidden.

### 4.8 Package & cleanup
- `output/<video_id>/clip_XX.mp4` and `clip_XX_post.md` (title, hook, score, reason, one section per platform with ready-to-paste caption).
- `output/<video_id>/summary.md`: clips produced with scores, rejected/failed clips with reasons, stage timings.
- Delete `jobs/<id>/audio*` and `jobs/<id>/src/` after success; keep transcripts/JSON (small) so re-cutting is fast.

## 5. Configuration

`config/style.yaml` (defaults):
```yaml
max_clips: 8
min_score: 7.0
length: {min: 20, target_min: 30, target_max: 60, max: 90}
captions: {font: Montserrat-Black, words_per_group: [2, 3], max_chars: 15, uppercase: true,
           color: "#FFFFFF", highlight_color: "#FFE500", outline: 8, shadow: 3}
hook_text: {enabled: true, duration: 2.5}
zoom: {enabled: true, scale: 1.18, min_gap: 4, max_gap: 7}
sfx: {enabled: true, gain_db: -18}
render: {fast: false}
review_first: false
```

`config/campaigns/<name>.yaml`:
```yaml
name: example-campaign
creator_tag: "@creator"
required_text: "Clip from @creator's podcast"
required_tags: ["#creatorpodcast"]
banned_topics: []
length: {min: 15, max: 60}        # overrides style.length
captions: {highlight_color: "#00E5FF"}
```

Merge order: `style.yaml` ← campaign file ← run overrides (from natural-language tweaks such as "under 30 s, no SFX, blue captions", which Claude translates into a temporary `jobs/<id>/overrides.yaml`).

## 6. Error handling

| Failure | Behaviour |
|---|---|
| doctor fails | Stop with exact fix commands |
| < 5 GB free | Stop before download |
| yt-dlp bot check | Stop and ask user about `--cookies-from-browser` |
| Transcription error | Stop; job resumable |
| Clip fails validation | Skip with reason; others continue |
| No face in a segment | `fit` layout fallback |
| ffmpeg error on one clip | Log stderr to `jobs/<id>/logs/`, skip clip, continue |
| Run interrupted | Rerun resumes from first stage without valid output |

## 7. Testing

- **Unit (pytest):** sentence-ID → time mapping; boundary snapping; caption grouping (2–3 words, ≤ 15 chars); ASS output (styles, timings, highlight tags); crop math (even dims, in-frame, safe-zone bounds); `clips.json` schema validation; config merge precedence; required-text injection and hashtag cap.
- **Integration:** end-to-end smoke test on a short (1–2 min) fixture clip, from the fetch stage through packaging.
- **Golden set:** 2–3 real campaign episodes reviewed by eye for selection and framing; record per-stage timings on the M1 (research found no M1 benchmarks for these tools).

## 8. Key dependencies

| Need | Choice |
|---|---|
| Python | 3.12 via uv |
| Download | `yt-dlp[default]` + Node 22 (already installed) |
| ASR | `parakeet-mlx` (parakeet-tdt-0.6b-v2) |
| Shots | `scenedetect[opencv]` |
| Faces | `mediapipe` (Tasks API) + face_landmarker.task model |
| Captions | `pysubs2` |
| Render | Homebrew `ffmpeg-full` |
| Config/schema | `pyyaml`, `jsonschema` |
| Tests | `pytest` |

Borrowed patterns (MIT): artbyjazi/autoclip (resumable stages, index-based selection, no panning across cuts, doctor command), OpenShorts (reframe layouts/active speaker), clipify (skill layout + JSON contract).

## 9. Future phases (separate specs)
1. Publisher — scheduled cross-platform posting via official APIs, cloud-hosted, with Content Rewards 30-minute submission reminders and 7-day view tracking.
2. Researcher — discovers new episodes for active campaigns.
3. Variants — before/after and timeline versions (possibly a Remotion renderer behind the same render interface).
4. Batch queue and Google Drive/local input.
