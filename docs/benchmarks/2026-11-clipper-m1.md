# Clipper v1 — first real run benchmark (Apple M1, 16 GB)

**Date:** 2026-11-07
**Episode:** "Big Tech Is Facing Lawsuits — Could You or Your Family Qualify? | Anthony Johnson" (Mindful Podcast), YouTube `6uSskUaDL90`, 48.6 min, 682 transcript sentences
**Campaign:** `social-media-justice` (Content Rewards; required tag `#AwesomeLawyer`)
**Clips:** 8 selected by Claude (review-first mode, approved by the user), 8/8 rendered, 0 failures

## Timings

| Stage | Run 1 (CRF 23 sections) | Run 2 (CRF 16 sections, after tuning) |
|---|---|---|
| fetch metadata | 4.5 s | cached |
| fetch audio | 13.3 s | cached |
| transcribe (parakeet-tdt-0.6b-v2, model already cached) | 162.0 s (~18× realtime) | cached |
| fetch 8 sections | 251.3 s | 237.5 s |
| reframe 8 clips | 47.8 s | 48.1 s |
| render 8 clips | 199.4 s | 213.1 s |
| **total** | **≈ 11.5 min** | ≈ 8.5 min (re-render) |

Clip lengths: 22.9–55.4 s (mean ≈ 39 s). Per clip: fetch ≈ 30 s, reframe ≈ 6 s, render ≈ 26 s.

Projection for a 2-hour episode with 8 clips: transcription scales with episode length (≈ 7 min), produce scales with clip count (≈ 8 min) → ≈ 16 min, inside the spec's ~30 min target.

## Output

- 1080×1920, H.264 High, 30 fps, ≈ 5.5 Mb/s; AAC 48 kHz stereo 192 kb/s; integrated loudness −14.5 LUFS (target −14).
- Section intermediates: 1.88 Mb/s at CRF 23 → 3.91 Mb/s at CRF 16 (same 10 s window), visibly sharper after the ~1.8× fill-crop upscale.
- Disk: sections and audio are deleted by `finish`; the job keeps 3 MB of transcripts/JSON; 8 clips = 204 MB.

## QA notes

- Fill crop kept the speaker (AJ) centred in every sampled frame; captions sit on chest/mic, never on the face; hook box visible at 0.5 s in every clip.
- Host reaction shots in wide framing (face too small for MediaPipe at 960 px analysis width) fall back to the `fit` layout (full frame over blur) — acceptable.
- Fixed during this run: a 0.57 s leading camera shot was merged into the next shot and got the wrong crop (now kept as its own segment); section encode quality raised to CRF 16.
