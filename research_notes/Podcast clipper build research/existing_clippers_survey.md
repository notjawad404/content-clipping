# Existing Open-Source AI Clippers, Claude Code Clipping Skills/MCP Servers, and the Commercial Quality Bar (state as of Nov 2026)

Method note: repo stars, licenses, last-commit dates and issue titles below were pulled directly from the GitHub REST API (via `gh api`) on 2026-11-06/07. "Last commit" = date of most recent commit on the default branch; "pushed" = last push to any branch. READMEs were read from the repos themselves. Commercial pricing is mostly from vendor pages plus third-party roundups (many written by competitors), so treat cross-vendor comparisons with caution.

## Q1. Which open-source clippers exist and are actively maintained in 2025-2026? Which 5 are most worth borrowing from?

### Takeaway
The field consolidated in 2025-2026 around a few active, full-pipeline projects: OpenShorts (MIT, ~7.5k stars), zhouxiaoka/AutoClip (MIT, ~10k stars, Chinese-first), SupoClip (AGPL, ~2.6k), FunClip (MIT, ASR-centric, Chinese-first), and AI-Youtube-Shorts-Generator (MIT, ~5.8k, now under Anil-matcha). Older names (ClipsAI, Reelsfy, ShortGPT, AI-Shorts-Creator) are abandoned, and MoneyPrinter/ShortGPT are topic-to-video generators, not clippers. For a commercial, Claude Code-driven local build on an M1, the best code to borrow is MIT-licensed: artbyjazi/autoclip (architecture), OpenShorts (reframe modes), clipify / joe-jns long-video-to-shorts (skill shape plus Apple Silicon tricks), AI-Youtube-Shorts-Generator (virality prompt plus dedupe), and browser-use/video-use (agent-editing patterns). The AGPL projects (podcli, SupoClip, publikclip) are worth studying but not copying.

### Cited Findings

**Full-pipeline clippers: active (commit within the last ~3 months)**

- **mutonby/OpenShorts**: about 7,522 stars, MIT, Python, last commit 2026-11-06, 10 open issues. [GitHub](https://github.com/mutonby/openshorts)
  - **Clip selection:** Gemini 3.1 Flash-Lite reads the transcript plus scene boundaries and picks 3-15 "viral moments". Setting `LLM_BASE_URL` points selection at Ollama, LM Studio, vLLM or any OpenAI-compatible server.
  - **Captions:** faster-whisper word-level timestamps, burned in.
  - **Reframing:** chosen per scene from four modes:
    - TRACK: MediaPipe + YOLOv8 face tracking.
    - GENERAL: blurred background.
    - SPLIT: two speakers stacked, captions on the seam.
    - SCREENCAST.
  - **Extras:** ElevenLabs dubbing, posting through Upload-Post, and an MCP endpoint.
  - **Setup and speed:** Docker with 8GB+ RAM. It takes 5-8 minutes per 8-minute video on CPU, versus about 50 s on the vendor's NVIDIA GPU.
  - **Hosted version:** from $12/mo, or a free tier with a watermark (20 min/mo).
  - **Code layout:** the source tree contains `active_speaker.py`, `clip_selection.py`, `burned_subtitles.py`, `camera_inset.py` and `cli/openshorts_cli.py`, plus a large `cloud/` billing and SaaS package. [README](https://github.com/mutonby/openshorts)
- **zhouxiaoka/AutoClip**: about 10,052 stars, MIT, Python, last commit 2026-11-03, 32 open issues. [GitHub](https://github.com/zhouxiaoka/autoclip)
  - **Packaging:** Tauri desktop app (FastAPI + React). The installer for macOS Apple Silicon (.dmg) and Windows x64 bundles Python and FFmpeg. Docker and a CLI/MCP are also provided, and an Agent skill lives at `skills/autoclip/SKILL.md`.
  - **LLM:** your choice of OpenAI-compatible cloud API, or Ollama / LM Studio.
  - **Transcription:** author subtitles, local Whisper / SenseVoice, or Alibaba Bailian cloud ASR (about ¥0.1 per audio hour).
  - **Reframing:** frame follows the speaker.
  - **Measured run:** an old-pipeline run on a 2h06m MrBeast video took 65 min and about ¥0.64 of qwen-plus tokens on an Apple Silicon Mac (2026-10-01).
  - **Target platforms:** Chinese-first (Douyin, Xiaohongshu, Bilibili), plus TikTok, Reels and Shorts. [README](https://github.com/zhouxiaoka/autoclip)
- **FujiwaraChoki/SupoClip**: about 2,619 stars, AGPL-3.0, last commit 2026-11-06, 29 open issues. [GitHub](https://github.com/FujiwaraChoki/supoclip)
  - **Clip selection:** an LLM (Gemini, GPT, Claude or Ollama) picks 3-7 segments, each scored on hook / engagement / value / shareability.
  - **Reframing and captions:** face-detection crop. Word-synced subtitles use AssemblyAI (cloud) by default; local Whisper is optional.
  - **Extras:** AI hook title, Pexels B-roll, a built-in editor, direct posting to YouTube / TikTok / IG, and a "performance loop" that feeds platform metrics back into selection. MCP server plus REST API.
  - **Stack:** Next.js 15 / React 19 / FastAPI / ARQ worker / Redis / Postgres.
  - **Licensing note:** a CLA lets the owner relicense contributions. [README](https://github.com/FujiwaraChoki/supoclip), [architecture.md](https://github.com/FujiwaraChoki/supoclip/blob/main/docs/architecture.md)
- **modelscope/FunClip (Alibaba Tongyi)**: about 6,503 stars, MIT code (model weights under their own licenses), last commit 2026-11-01. [GitHub](https://github.com/modelscope/FunClip)
  - **Transcription:** FunASR Paraformer ASR (Chinese-first; an English Paraformer is available via `-l en`). It also supports SenseVoice, Fun-ASR-Nano and MOSS-Transcribe-Diarize (v2.2.0, 2026-08-30).
  - **Clip selection:** LLM-assisted (OpenAI-compatible gateways). An optional TwelveLabs Pegasus path reasons over the video itself.
  - **Interface:** Gradio UI plus a 2-stage CLI (`--stage 1` recognize, `--stage 2` clip) that outputs SRT.
  - **Whisper:** still listed as "coming soon". [README](https://github.com/modelscope/FunClip)
- **Anil-matcha/AI-Youtube-Shorts-Generator** (formerly SamurAIGPT/AI-Youtube-Shorts-Generator, which now redirects): about 5,777 stars, MIT, last commit 2026-11-06. [GitHub](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator)
  - **Two modes:**
    - `--mode api` uses the paid MuAPI service (gpt-5-mini plus `/autocrop`). The README is heavily oriented toward selling MuAPI.
    - `--mode local` uses yt-dlp + faster-whisper (CPU/CUDA) + OpenAI `gpt-4o-mini` or Gemini `gemini-2.5-flash` + OpenCV face tracking with motion smoothing.
  - **Selection pipeline:**
    - An LLM first classifies content type (podcast, interview, ...) to tune the prompt.
    - Highlights are ranked against a `VIRALITY_CRITERIA` list (hook moments, emotional peaks, "opinion bombs", revelations, conflict, quotables, story peaks, practical value).
    - Each clip comes with score + hook + reason, and overlapping candidates (>50% overlap) are deduped by score.
  - **Caching and output:** the transcript is cached as `.srt` and the download is cached; `--output-json` dumps everything. [README](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator)
- **artbyjazi/autoclip** (different project from zhouxiaoka's): about 232 stars, MIT, last commit 2026-08-01, pre-1.0. [GitHub](https://github.com/artbyjazi/autoclip)
  - **Stack:** local-first (Whisper + Ollama), or BYO key for Anthropic / OpenAI / Gemini / any OpenAI-compatible endpoint. MediaPipe reframe (requires Python 3.11/3.12), optional WhisperX diarization for active-speaker cuts, four caption styles via libass.
  - **Doctor command:** `autoclip doctor` checks the environment.
  - **Pipeline:** the documented stages are `ingest → prepare → transcribe → highlights → reframe → captions → export`. Artifacts go to `~/.autoclip/work/{job_id}/` so a retry resumes at the failed stage.
  - **Design rules:**
    - The LLM returns word indices, not timestamps.
    - Crop paths never interpolate across a cut (shot detection runs first).
    - Output is normalized to −14 LUFS.
  - **Honest caveat:** "A 7B model returns valid JSON full of mediocre picks; a frontier model is noticeably better at spotting a real hook." [README](https://github.com/artbyjazi/autoclip)
- **nmbrthirteen/podcli**: about 84 stars, AGPL-3.0 (a commercial license is available by email), last commit 2026-11-03. [GitHub](https://github.com/nmbrthirteen/podcli)
  - **Selection and transcription:** whisper.cpp transcription. Scoring uses your local Claude Code or Codex login, or `ANTHROPIC_API_KEY`.
  - **Reframing and audio:** face tracking with split-screen layouts. Active-speaker following needs AssemblyAI or openai-whisper + HF_TOKEN. Multi-segment cuts drop filler, pauses and tangents. Four caption styles (branded / hormozi / karaoke / subtle), loudness normalization.
  - **Platform:** VideoToolbox hardware encoding. Supports macOS Apple Silicon; Intel Macs are not supported.
  - **Agent integration:** 32 MCP tools plus SKILL.md plus "PodStack" Claude Code slash commands (`/produce-shorts`). A knowledge base keeps titles in the show's voice and avoids re-suggesting published moments.
  - **Extras:** FCPXML export for DaVinci. [README](https://github.com/nmbrthirteen/podcli)
- **Blueturboguy07/publikclip**: about 72 stars, AGPL-3.0, last commit 2026-11-06.
  - **Packaging:** Tauri desktop app with a Python pipeline. Supports macOS Apple silicon and Windows.
  - **Local models:** ASR, forced alignment, diarization, laughter detection, audio tagging, face detection and active-speaker detection all run locally (about 4-5 GB of models). Only 2-3 small LLM calls go out (publik API by default, or Gemini, or Ollama "at reduced scoring quality").
  - **Auditable virality score:** subscores plus the detectors that fired. LLM humor scores are discounted when no laughter is detected.
  - **Extras:** punch-ins triggered by laughter or vocal energy, a CC0 music/SFX library with speech ducking.
  - **Telemetry:** sends usage telemetry unless `DO_NOT_TRACK=1`. [GitHub](https://github.com/Blueturboguy07/publikclip)
- **krakonjac300-pixel/podcast-shorts-factory**: about 134 stars, MIT, last commit 2026-07-22.
  - **Agents:** ten cooperating agents (Finder, Editor, ..., a "Finishing Editor" QC gate that checks for captions over faces, black or frozen frames and dead air).
  - **Pipeline details:** faster-whisper, chunked scoring of long episodes, 24 "skill playbooks" loaded into prompts.
  - **LLM:** Groq / Gemini / Ollama / Anthropic ("paid, best quality"). [GitHub](https://github.com/krakonjac300-pixel/podcast-shorts-factory)

**Smaller or less active clippers**

| Repo | Stars | License | Last commit | Stack | Source |
|---|---|---|---|---|---|
| SamurAIGPT/Clip-Anything | 314 | MIT | 2026-07-21 | Prompt-based clipping with GPT-4V + Whisper | [GitHub](https://github.com/SamurAIGPT/Clip-Anything) |
| alexfazio/viral-clips-crew | 770 | MIT | 2026-02-16 | CrewAI + OpenAI + Gemini | [GitHub](https://github.com/alexfazio/viral-clips-crew) |
| Andreaswt/ai-podcast-clipper-saas | 189 | MIT | push 2025-05-22 | TypeScript SaaS template | [GitHub](https://github.com/Andreaswt/ai-podcast-clipper-saas) |
| faris-sait/openshorts | 173 | MIT | 2026-04-17 | JavaScript | [GitHub](https://github.com/faris-sait/openshorts) |

- The viral-clips-crew author states it was "99% vibe coded… not going to support it in any way". [GitHub](https://github.com/alexfazio/viral-clips-crew)
- Many 0-10-star 2026 clones also exist ("fluxclip", "Steezy-code/clipper", "ClipPulse-AI", "video-podcast-clipper"). These are not worth tracking individually. [GitHub search](https://github.com/search?q=opusclip+alternative&type=repositories)

**Abandoned or stale**

- **ClipsAI/clipsai**: 564 stars, MIT, last commit 2024-01-17.
  - **Stack:** WhisperX transcription; clip finding by TextTiling over the transcript; resizing via pyannote diarization + face detection.
  - **State of the repo:**
    - Issue #17 "Is this project abandoned?" (Mar 2026) reports install failure on Python 3.14 (Pillow pin).
    - Issue #13 reports "lot of dependency issues".
    - Issue #19 announces a community fork, EricksonLOOP/clipsai, with pyannote 4.x fixes and the unsafe `eval()` removed.
  - [GitHub](https://github.com/ClipsAI/clipsai), [issue #19](https://github.com/ClipsAI/clipsai/issues/19)
- **eddieoz/reels-clips-automator ("Reelsfy")**: 232 stars, MIT, last commit 2023-09-23. Stack: GPT-3.5-turbo-16k (about 20-minute video limit), OpenCV face tracking, Whisper captions. [GitHub](https://github.com/eddieoz/reels-clips-automator)
- **NisaarAgharia/AI-Shorts-Creator**: 773 stars, no license, last commit 2024-02-14. Stack: GPT-4 + OpenCV. [GitHub](https://github.com/NisaarAgharia/AI-Shorts-Creator)
- **RayVentura/ShortGPT**: 8,118 stars, MIT, last commit 2025-02-10, 86 open issues. It is a framework for "youtube shorts / tiktok channel automation" (faceless content), not a long-form clipper. Its issues are dominated by MoviePy, Whisper and numpy dependency errors, plus a macOS requirements install hanging for 1000+ seconds (#149). [GitHub](https://github.com/RayVentura/ShortGPT)
- **The MoneyPrinter family:** topic or keyword to stock-footage + TTS short. These generate videos; they do not clip podcasts.
  - harry0703/MoneyPrinterTurbo: about 140k stars, MIT, active. [GitHub](https://github.com/harry0703/MoneyPrinterTurbo)
  - FujiwaraChoki/MoneyPrinter: 14k stars, MIT. [GitHub](https://github.com/FujiwaraChoki/MoneyPrinter)
  - MoneyPrinterV2: 32k stars, AGPL-3.0. [GitHub](https://github.com/FujiwaraChoki/MoneyPrinterV2)
- **zhouxiaoka/autoclip_mvp** (1,183 stars, MIT, last push 2025-09-15) was superseded by zhouxiaoka/autoclip. [GitHub](https://github.com/zhouxiaoka/autoclip_mvp)

**License traps for commercial use**

- **Shaarav4795/ClippedAI**: 231 stars, last commit 2026-09-04, marketed as an "open-source alternative to OpusClip". Its license is **CC BY-NC 4.0, which is non-commercial**. Stack: clipsai + pyannote + Groq titles. [GitHub](https://github.com/Shaarav4795/ClippedAI)
- **No license (all rights reserved by default):**
  - NisaarAgharia/AI-Shorts-Creator. [GitHub](https://github.com/NisaarAgharia/AI-Shorts-Creator)
  - burningion/video-editing-mcp. [GitHub](https://github.com/burningion/video-editing-mcp)
  - egoist/ffmpeg-mcp. [GitHub](https://github.com/egoist/ffmpeg-mcp)
  - aryan1429/clipping-edit. [GitHub](https://github.com/aryan1429/clipping-edit)
- **Remotion** is not OSI open source. It is free for individuals, non-profits, for-profit orgs with up to 3 employees, and for evaluation; larger companies need a paid Company License. [Remotion LICENSE.md](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)
- **Model weights:**
  - FunClip's model weights are "governed by the terms on their model pages". [FunClip README](https://github.com/modelscope/FunClip)
  - pyannote diarization models are gated on HuggingFace and require accepting their terms. [ClippedAI README](https://github.com/Shaarav4795/ClippedAI); [artbyjazi/autoclip README](https://github.com/artbyjazi/autoclip)

**Apple Silicon compatibility signals**

- **Explicit macOS Apple Silicon support:**
  - zhouxiaoka/AutoClip ships a .dmg; there is no Intel Mac desktop build. [README](https://github.com/zhouxiaoka/autoclip)
  - podcli. [README](https://github.com/nmbrthirteen/podcli)
  - publikclip. [README](https://github.com/Blueturboguy07/publikclip)
  - clipify uses VideoToolbox; "~20s of work for a 20s clip on Apple Silicon". [README](https://github.com/louisedesadeleer/clipify)
- **artbyjazi/autoclip:**
  - Says "NVIDIA or Apple Silicon speeds up transcription several-fold". [README](https://github.com/artbyjazi/autoclip)
  - On macOS you need `brew install ffmpeg-full`, because the plain Homebrew ffmpeg lacks libass and fails to burn captions. [README](https://github.com/artbyjazi/autoclip)
  - Open issue #2: `autoclip serve` crashes on macOS with "MediaPipe GPU service unavailable". [Issue #2](https://github.com/artbyjazi/autoclip/issues/2)
- **WhisperX** documents CPU-only use on macOS (`--device cpu --compute_type int8`); its GPU acceleration path is CUDA. [whisperX README](https://github.com/m-bain/whisperX)
- **OpenShorts:** self-hosting is Docker (5-8 min per 8-min video on CPU), and GPU acceleration is documented for NVIDIA only. [README](https://github.com/mutonby/openshorts)

### Inferences

**Top 5 to borrow from, for a commercial, local, Claude Code-driven M1 build:**

1. **artbyjazi/autoclip (MIT).** It has the cleanest, best-documented architecture to copy:
   - per-stage artifacts and resume
   - LLM returns word indices instead of timestamps
   - shot-aware crop paths
   - −14 LUFS loudness
   - a `doctor` environment check
   - macOS libass gotchas already solved

   Its weakness is that it is small and pre-1.0, so treat it as a design reference more than a dependency.
2. **mutonby/OpenShorts (MIT, the most-starred active MIT clipper).** It has the richest reframing logic: TRACK / GENERAL / SPLIT / SCREENCAST per scene, MediaPipe + YOLOv8, and a separate `active_speaker.py`. Its LLM endpoint is OpenAI-compatible. `active_speaker.py`, `clip_selection.py` and `burned_subtitles.py` can be lifted under MIT terms. Its weaknesses: Docker and SaaS cruft, and it is Gemini-first.
3. **clipify + joe-jns/long-video-to-shorts (both MIT).** These are the closest to the target shape: a Claude Code skill with SKILL.md, deterministic scripts, references and a JSON schema contract, with a human approval gate.
   - Clipify's model-free speaker detection (motion energy in mouth ROIs, hard-cut pans) plus VideoToolbox is ideal for M1 podcasts with static cameras.
   - joe-jns contributes `clips.schema.json`, `config.json`, safe zones and 8 ASS caption styles.
4. **Anil-matcha/AI-Youtube-Shorts-Generator (MIT).** Copy its virality criteria prompt, content-type pre-classification, score + hook + reason output, >50% overlap dedupe and cache-by-mtime pattern. Ignore the MuAPI upsell.
5. **browser-use/video-use (MIT, about 30.6k stars).** Not a clipper, but the best agent-editing pattern:
   - a packed phrase-level transcript as the primary surface
   - on-demand filmstrip + waveform PNGs (`timeline_view`) instead of frame dumps
   - an EDL, then render, then a self-eval loop (max 3)
   - `project.md` session memory

**Study but don't copy (AGPL):**

- **podcli:** the most Claude Code-native clipper. It has an MCP + SKILL.md + slash commands, and scores with Claude Code login. A commercial license is offered.
- **publikclip:** laughter-corroborated scoring and an auditable virality score.
- **SupoClip:** the performance feedback loop and the multi-dimension scores.
- **What AGPL means here (not legal advice):** running AGPL tools privately to produce client videos generally does not force you to open-source anything, since the videos are output, not derived code. Incorporating AGPL code into a tool you distribute or offer as a network service would.

**FunClip and zhouxiaoka/AutoClip** are strongest for Chinese ASR and Chinese platforms, and less relevant for English podcasts. FunClip has no evident 9:16 reframing in its README.

### Gaps
- I did not inspect source code quality, test coverage or real output quality for any repo. Rankings are based on READMEs, architecture docs, licenses and issue trackers.
- Star counts can be inflated. One zhouxiaoka/AutoClip issue (#59, "这么多Star是咋刷出来的。数不清的错误。" — "how were so many stars faked? countless errors") alleges this. It is unverified. [Issue list](https://github.com/zhouxiaoka/autoclip/issues/59)
- I did not verify whether FunClip has any reframe or vertical-crop feature beyond what its README shows.
- I could not verify the EricksonLOOP/clipsai fork's activity level or stars.

## Q2. Are there published Claude Code skills, plugins, or MCP servers for clipping and editing? How are they structured?

### Takeaway
Yes, and there are many by late 2026. The dominant pattern is a `SKILL.md` "doctrine" file plus deterministic Python or Bash scripts, plus `references/*.md` for selection, reframe and caption rules, plus a JSON contract (`clips.json` / schema), with human approval gates between "pick" and "render". The LLM only picks moments and writes titles; everything else is deterministic. Eddie's (Eddie | AI) "Long-Form Clipper" skill is free behind a Skool community login. It is not public on GitHub, and its structure is known only from third-party notes. Separately, several MCP servers expose ffmpeg and clipping tools (Kinocut, podcli, SupoClip, OpenShorts, autoclip, plain ffmpeg-mcp servers).

### Cited Findings

**Claude Code clipping skills**

- **louisedesadeleer/clipify**: 627 stars, MIT, last push 2026-08-24. [GitHub](https://github.com/louisedesadeleer/clipify)
  - **Layout:** `SKILL.md`, then `scripts/` containing `analyze.py` (speaker timeline from ROI motion), `build_pan.py` (ffmpeg crop x-expression with hard cuts), `build_ass.py` (opus/karaoke/minimal ASS from whisper JSON), `audio_align.py` and `detect_transients.py`.
  - **Interactive flow:** propose 3-5 candidates, ask which to cut, ask aspect ratio, ask pan vs split-screen, ask caption style (or match a pasted reference image), then render.
  - **Stack:** local openai-whisper; "No cloud APIs… No OpenCV"; VideoToolbox decode on macOS.
- **joe-jns/long-video-to-shorts**: README says MIT, though the GitHub API reports NOASSERTION; last commit 2026-07-15. [GitHub](https://github.com/joe-jns/long-video-to-shorts)
  - **Stages:** `INTAKE → PROBE (ffprobe + 1fps contact sheet) → TRANSCRIBE (faster-whisper → work/transcript.json) → PICK (agent proposes shortlist; you approve) → BUILD (cut → reframe → captions → hook → shorts/NN.mp4) → DELIVER (manifest.md)`.
  - **Layout:**
    - `SKILL.md`, `DESIGN.md`, `PLAN.md`
    - `clips.schema.json` ("the shortlist contract") and `config.json`
    - `references/{highlight-selection,reframe,captions-gameplay,troubleshooting}.md`
    - `scripts/{intake,probe,cut,reframe_facecam,reframe_gameplay,captions_burn,hook_title,build_clip}.sh`, plus `transcribe.py` and `ass_from_words.cjs`
    - a companion config skill
  - **Reframing:** the face is located by Claude vision on the contact sheet, with no ML model. [README](https://github.com/joe-jns/long-video-to-shorts)
- **mihm88/long-video-to-shorts**: MIT, last commit 2026-10-22. [GitHub](https://github.com/mihm88/long-video-to-shorts)
  - **Pipeline:** 12 steps with 3 approval gates:
    - rights check
    - audio-only download first
    - word-timed transcription (AssemblyAI)
    - LLM pick (Gemini)
    - approval gate
    - transcript correction
    - download only the approved segments
    - one proof clip
    - approval gate
    - the remaining clips
    - caption review
    - delivery gate; it never auto-publishes
  - **Languages:** Arabic and RTL captions.
- **Eddie | AI "Long-Form Clipper" (`Claude-Video-Clipper-main.zip`):**
  - **Access:** free behind the Skool "AI Builders Club". A YouTube walkthrough is titled "Claude Code Can Now Clip ANY Video (Free Skill)". [YouTube](https://www.youtube.com/watch?v=IY08-3TS2o8); [Skool post](https://www.skool.com/ai-automation-society/built-a-free-opusclip-alternative-as-a-claude-code-skill?p=493d37df)
  - **Third-party notes:** a third party's transcription of the tutorial (not the official files) describes the following. [aryan1429/clipping-edit reference notes](https://github.com/aryan1429/clipping-edit/blob/main/skill/references/02_eddie_claude_clipping_tutorial.md)
    - **Layout:** `.claude/`, `CLAUDE.md`, `assets/` (sfx/whoosh files), a `clipper/` Python package (`cut.py`, `reframe.py`, `edit.py`, `sfx.py`), optional `remotion/`, `output/` and `install.py`. The installer builds a `.venv` with yt-dlp, faster-whisper `small` and OpenCV.
    - **Division of labour:** runs on a Claude Pro plan. "The LLM's only job is picking moments plus writing the titles and captions," and the rest is deterministic Python rendering 1080×1920.
    - **Selection:** Claude reads a `mm:ss` speaker-labelled transcript. It tags WARM-UP / HOOK / PAYOFF lines and requires a hook type (contrarian, surprising fact, novel claim, story opener). Clips must stand alone with zero context. Each gets a score out of 10 and they are ranked, spread across the whole source.
    - **Demo output:** 7 clips of 29-76 s from a 1h43m MrBeast podcast.
    - **Edit style:** camera-cut detection with re-centring on the active speaker once per shot (static, no jitter); 13-19 subtle 1.04-1.22× punch-in zooms per clip at sentence ends; whoosh SFX; word-by-word ALL-CAPS karaoke captions.
    - **Re-edits:** done by prompt without re-download.
  - **Status of this account:** these details are second-hand. I did not see the official files, and Skool membership may be required (one commenter reported a payment issue joining). [Search summary of Skool posts](https://www.skool.com/ai-automation-society/built-a-free-opusclip-alternative-as-a-claude-code-skill?p=493d37df)
- **aryan1429/clipping-edit**: no license, 0 stars, last push 2026-11-01.
  - A clone-style skill with `skill/SKILL.md`, then `skill/references/01..06_*.md` (style ref, Eddie tutorial, HyperFrames media pipeline / captions / QC, background music) and `skill/scripts/{cutlist,cuts,splice,mix_audio,grade_gate,finalize_mux,preflight,probe_source,find_music}.py`.
  - It ships unit tests per script. [GitHub](https://github.com/aryan1429/clipping-edit)
- **gooseworks-ai video-clipper skill** (in gooseworks-ai/goose-skills). [Skills Directory listing](https://www.skillsdirectory.com/skills/gooseworks-ai-video-clipper)
  - **Pipeline:** a single about 12 KB SKILL.md plus `skill.meta.json`. Local Whisper, then Claude scores 15-60 s segments on five criteria (hook, quotability, emotional intensity, self-containedness, surprise), then user approval, then FFmpeg cut, then **Klap API** reframe, then **Captions.ai API** captions.
  - **Cost:** about $2-3 per clip.
  - **Security:** the directory flagged a critical "exfiltrates credentials via HTTP" finding.
- **DidierRLopes/get-y2b-clips:** a Claude Code plugin installed via marketplace (blog dated 2025-12-22).
  - **Output:** per-clip folders containing `metadata.json` (title, start/end, rationale, timestamped URL), `transcript.txt` and `clip.mp4`.
  - **Lesson:** "speed improved once pre-built Python tools replaced scripts the agent wrote on every run". [Blog](https://didierlopes.com/blog/i-built-a-claude-skill-that-turns-podcasts-into-shareable-clips/)
- **2boysfromtown/2bft-video-editor**: MIT, last commit 2026-10-28. [GitHub](https://github.com/2boysfromtown/2bft-video-editor)
  - **Contents:** 14 Claude Code skills, installable via `npx skills add` or `claude plugin marketplace add`.
  - **Reframing:** `reframe.py` uses the OpenCV YuNet face model with a "camera operator" smoothing chain (gap fill, median, Gaussian, deadzone).
  - **Local tools:** DeepFilterNet denoise, Demucs stems, TransNetV2 shot detection, MediaPipe tracking.
  - **Speed:** a 5 s 1080p clip renders to a face-tracked 9:16 in 5.7 s on CPU.
- **Other skills:**
  - lianglandan/podcast-shorts-editor- (MIT, Chinese interview → Douyin Claude Skill). [GitHub](https://github.com/lianglandan/podcast-shorts-editor-)
  - dominicCyrano/cyrano-clips. [GitHub](https://github.com/dominicCyrano/cyrano-clips)
  - SamurAIGPT "ai-clipping" skill listing. [getclaudeskills](https://www.getclaudeskills.com/skills/ai-clipping-samuraigpt)

**General agent video-editing toolkits (not clippers, but reusable patterns)**

- **browser-use/video-use**: 30,642 stars, MIT, last commit 2026-10-08. [GitHub](https://github.com/browser-use/video-use)
  - **Layout:** `SKILL.md` plus `helpers/{transcribe,transcribe_batch,pack_transcripts,timeline_view,render,grade}.py`, symlinked into `~/.claude/skills/`.
  - **Transcription:** ElevenLabs Scribe (cloud) for word timestamps, diarization and audio events such as `(laughter)`.
  - **Pipeline:** `Transcribe → Pack → LLM Reasons → EDL → Render → Self-Eval (max 3 re-renders)`; outputs go to `<videos_dir>/edit/`. "The LLM never watches the video. It reads it."
- **digitalsamba/claude-code-video-toolkit**: 2,463 stars, MIT, last commit 2026-11-05. A Remotion-based production toolkit with skills, slash commands (`/video`, `/scene-review`, `/publish`) and per-project `project.json`. It is for producing videos, not clipping. [GitHub](https://github.com/digitalsamba/claude-code-video-toolkit)
- **heygen-com/hyperframes**: about 80,021 stars, Apache-2.0. Renders HTML to deterministic MP4 and is "built for agents", with a Claude Code plugin (`claude plugin marketplace add heygen-com/hyperframes`). A possible alternative to Remotion for caption and overlay rendering without Remotion's company-license terms. [GitHub](https://github.com/heygen-com/hyperframes)
- **Remotion:**
  - remotion-dev/skills: 6,476 stars. [GitHub](https://github.com/remotion-dev/skills)
  - remotion-dev/template-tiktok ("TikTok-style captions with Whisper.cpp"): 303 stars. [GitHub](https://github.com/remotion-dev/template-tiktok)
  - Both fall under the Remotion license terms above.

**MCP servers**

- **KyaniteLabs/kinocut** (formerly mcp-video): 252 stars, Apache-2.0, last commit 2026-11-03, v1.16.5. [GitHub](https://github.com/KyaniteLabs/kinocut)
  - Listed in the official MCP Registry as `tech.kyanitelabs/kinocut`.
  - Tool counts: 20 default MCP tools, 205 full, 177 CLI commands.
  - "Primary job: turn a local interview or podcast into captioned vertical clips with a Video Receipt". Typed operations produce provenance receipts, quality gates and a human release approval.
- **ffmpeg MCP servers:**

  | Repo | Stars | License | Last push | Source |
  |---|---|---|---|---|
  | video-creator/ffmpeg-mcp | 153 | MIT | 2026-05-20 | [GitHub](https://github.com/video-creator/ffmpeg-mcp) |
  | egoist/ffmpeg-mcp | 122 | none | 2025-03-29 (stale) | [GitHub](https://github.com/egoist/ffmpeg-mcp) |
  | kevinwatt/ffmpeg-mcp-lite | 28 | MIT | 2026-05-08 | [GitHub](https://github.com/kevinwatt/ffmpeg-mcp-lite) |

  These are thin wrappers (trim, convert, subtitles). [GitHub search: "ffmpeg mcp"](https://github.com/search?q=ffmpeg+mcp&type=repositories)
- **burningion/video-editing-mcp**: 295 stars, no license, last push 2025-10-09. An interface to the cloud Video Jungle service. [GitHub](https://github.com/burningion/video-editing-mcp)
- **Clipper apps that expose MCP:**
  - podcli (32 tools; `rank_clip_candidates` returns a shortlist "so the agent does not have to read the whole transcript"; `process_episode` plus `job_status` polling). [README](https://github.com/nmbrthirteen/podcli)
  - SupoClip (`mcp/`). [README](https://github.com/FujiwaraChoki/supoclip)
  - OpenShorts (`/mcp`). [README](https://github.com/mutonby/openshorts)
  - zhouxiaoka/AutoClip (CLI/MCP). [README](https://github.com/zhouxiaoka/autoclip)
  - OpusClip Pro also offers an "MCP connector". [OpusClip pricing](https://www.opus.pro/pricing)

### Inferences
- **Convergent skill design:**
  - SKILL.md holds doctrine, the flow and the approval gates.
  - Deterministic scripts do intake, probe, transcribe, cut, reframe, captions, hook and render.
  - `references/` holds selection rubric, reframe math, caption style and troubleshooting.
  - A JSON contract sits between the LLM and the renderer (`clips.json` + schema).
  - A config file holds brand fonts, colours and safe zones.
  - Output is a manifest with titles and hashtags.

  The user's build should adopt this. The Claude subscription replaces paid LLM API calls for selection, which is Eddie's and podcli's main selling point.
- **Pre-built scripts beat agent-written scripts** for speed and reliability (Didier Lopes's lesson). Ship tested scripts, and let Claude orchestrate and judge.
- **Approval gates** reduce wasted renders. Typical placement is after the shortlist and after one proof clip (mihm88, joe-jns, clipify).
- **MCP vs skill:** a skill plus CLI scripts is simpler for a single-user local tool. MCP is useful if the user later wants Claude Desktop or other agents to drive it, or job polling for long renders (podcli pattern).

### Gaps
- Eddie's official skill files could not be inspected (Skool-gated), so the structure above relies on third-party notes from a single tutorial video.
- I did not check anthropics/skills (188k stars) or the large awesome-claude-code lists for an official video-clipping skill. None surfaced in searches.
- I did not survey mcp.so or glama.ai directly. The MCP servers listed came from GitHub search.

## Q3. How do these projects structure the pipeline (stages, intermediate files, caching, resumability)? What are the common failure points?

### Takeaway
Nearly every project uses the same 6-8 stage linear pipeline: ingest/download, then audio extract, then word-level ASR, then LLM highlight selection (JSON), then shot/face analysis, then reframe crop path, then ASS caption burn, then encode/export with metadata. The better ones persist per-stage artifacts keyed by job ID for resume. The recurring failures are mostly not AI problems:

- YouTube download blocks (403 / bot check)
- cloud ASR API changes
- LLM rate limits and timeouts
- ffmpeg builds missing libass
- Python and ML dependency rot (MediaPipe, pyannote, Pillow, Python 3.13/3.14)
- GPU/CUDA assumptions breaking on Mac

### Cited Findings

**Pipeline structures**

| Project | Stages | Intermediate files / state | Source |
|---|---|---|---|
| artbyjazi/autoclip | `ingest → prepare → transcribe → highlights → reframe → captions → export` | Artifacts in `~/.autoclip/work/{job_id}/`; resume at the failed stage. LLM returns word indices mapped back to measured word timings. Shots are detected first, each framed independently. | [README](https://github.com/artbyjazi/autoclip) |
| joe-jns | intake, probe, transcribe, pick, build, deliver | `work/source.mp4`, `work/transcript.json`, `clips.json` (validated by `clips.schema.json`), `shorts/NN.mp4`, `manifest.md` | [README](https://github.com/joe-jns/long-video-to-shorts) |
| Anil-matcha/AI-Youtube-Shorts-Generator | download, transcribe, classify content type, rank highlights, dedupe, crop | Download and `.srt` transcript cached and reused if newer than the source; `--output-json` dumps transcript + all candidates + final clips | [README](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) |
| FunClip | stage 1: recognize; stage 2: clip | Explicit 2-stage CLI (`--stage 1`, `--stage 2`) emitting full and per-segment SRT | [README](https://github.com/modelscope/FunClip) |
| SupoClip | task creation, then out-of-band processing | Next.js → FastAPI → Redis queue → ARQ worker → Postgres + file storage; task creation is fast and generation runs in the worker, with progress streamed to the browser | [architecture.md](https://github.com/FujiwaraChoki/supoclip/blob/main/docs/architecture.md) |
| browser-use/video-use | Transcribe → Pack → Reason → EDL → Render → Self-Eval | Phrase-packed transcript (about 12 KB of text) plus on-demand `timeline_view` PNGs; `project.md` persists session memory | [README](https://github.com/browser-use/video-use) |
| podcli | transcribe, score, render; multicam edits | Transcript cache, clip history with duplicate detection, presets; re-running reuses sync and cut so only changed steps re-run | [README](https://github.com/nmbrthirteen/podcli) |
| mihm88 | audio-only first; full-quality video only for approved segments | Saves bandwidth on long sources | [README](https://github.com/mihm88/long-video-to-shorts) |
| podcast-shorts-factory | chunked scoring, then render, then QC | Long episodes are scored in chunks "so nothing" is missed; a dedicated QC agent checks renders for captions covering faces, black/frozen frames and dead air | [README](https://github.com/krakonjac300-pixel/podcast-shorts-factory) |

**Common failure points from issue trackers and READMEs**

- **YouTube download blocks:**
  - "As of 2026, YouTube blocks most anonymous downloads and proof-of-origin tokens no longer clear it". You need cookies from a signed-in browser. [artbyjazi/autoclip README](https://github.com/artbyjazi/autoclip)
  - AI-Youtube-Shorts-Generator issue #60, "HTTP Error 403: Forbidden" (Jul 2026). [Issues](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator/issues/60)
  - Eddie's tutorial notes `--cookies-from-browser chrome` for the "not a bot" error. [notes](https://github.com/aryan1429/clipping-edit/blob/main/skill/references/02_eddie_claude_clipping_tutorial.md)
  - zhouxiaoka/AutoClip #163, "下载到5%就停了" ("the download stops at 5%"). [Issue](https://github.com/zhouxiaoka/autoclip/issues/163)
- **Cloud ASR API drift:** SupoClip's most-discussed issues are AssemblyAI's `speech_model` parameter deprecation breaking transcription (#11, Mar 2026; #56, Jun 2026), plus "Videos stay queued" (#2). [#11](https://github.com/FujiwaraChoki/supoclip/issues/11), [#56](https://github.com/FujiwaraChoki/supoclip/issues/56), [#2](https://github.com/FujiwaraChoki/supoclip/issues/2)
- **LLM provider limits and timeouts:**
  - OpenShorts #27, "Gemini High Demand Issue while clipping". [Issue](https://github.com/mutonby/openshorts/issues/27)
  - AI-Youtube-Shorts-Generator #55, MuAPI timeouts. [Issue](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator/issues/55)
  - artbyjazi #3, "Ollama highlight detection times out on Windows". [Issue](https://github.com/artbyjazi/autoclip/issues/3)
  - zhouxiaoka #175: DeepSeek token consumption too high on 1-2 hour videos, and clip previews show a black screen. [Issue](https://github.com/zhouxiaoka/autoclip/issues/175)
  - ShortGPT #48, OpenAI rate limits. [Issue](https://github.com/RayVentura/ShortGPT/issues/48)
- **Demand for local models:** this is a top request in several repos. OpenShorts #17 led to the `LLM_BASE_URL` addition. [Issue](https://github.com/mutonby/openshorts/issues/17); AI-Youtube-Shorts-Generator #69. [Issue](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator/issues/69)
- **ffmpeg without libass:** "It installs cleanly, then fails to burn a single caption." The macOS fix is `brew install ffmpeg-full`. [artbyjazi/autoclip README](https://github.com/artbyjazi/autoclip)
- **ffmpeg path quoting:** the ffmpeg `subtitles` filter chokes on Windows drive-colon paths, so scripts run ffmpeg from a temp dir with relative paths. [joe-jns README](https://github.com/joe-jns/long-video-to-shorts)
- **Dependency rot in Python/ML stacks:**
  - MediaPipe has no Python 3.13 wheels. [artbyjazi README](https://github.com/artbyjazi/autoclip)
  - ClipsAI fails on Python 3.14 because of the Pillow pin, and needs a pyannote 4.x API rename. [#17](https://github.com/ClipsAI/clipsai/issues/17), [#19](https://github.com/ClipsAI/clipsai/issues/19)
  - ShortGPT: "module 'whisper' has no attribute '__version__'", "Numpy is not available", and the MoviePy duration error. [ShortGPT issues](https://github.com/RayVentura/ShortGPT/issues/34)
- **Local Whisper failures in desktop packaging:** zhouxiaoka #247. [Issue](https://github.com/zhouxiaoka/autoclip/issues/247)
- **Quality complaints:**
  - zhouxiaoka #59 (complaint of "countless errors"). [Issue](https://github.com/zhouxiaoka/autoclip/issues/59)
  - OpenShorts #18: generated clips not loading, and "Auto Edit" fails after analysis. [Issue](https://github.com/mutonby/openshorts/issues/18)
- **Reframe and active-speaker complexity:**
  - Diarization-based active-speaker cutting needs a HuggingFace token plus acceptance of gated pyannote licenses, and pulls a large PyTorch install. [artbyjazi README](https://github.com/artbyjazi/autoclip)
  - podcli needs AssemblyAI, or openai-whisper + HF_TOKEN, to follow the active speaker. [podcli README](https://github.com/nmbrthirteen/podcli)
  - artbyjazi's own unmet acceptance bar is "no visible jitter, no cut-off faces, speaker on screen ≥95% of speaking time". [README](https://github.com/artbyjazi/autoclip)
- **LLM timestamp errors:** "Models are unreliable at arithmetic and completely reliable at copying a number they can see." This is the reason artbyjazi uses word indices. [README](https://github.com/artbyjazi/autoclip)
- **Context-window limits on long sources:**
  - Reelsfy limited input to about 20-minute videos because of the gpt-3.5-turbo-16k context. [README](https://github.com/eddieoz/reels-clips-automator)
  - viral-clips-crew: under 15 minutes for OpenAI, up to 1 hour for Gemini. [README](https://github.com/alexfazio/viral-clips-crew)

### Inferences
- **Stage design for the user's build:** use a job directory per episode with fixed artifact names:
  - `source.mp4`, `audio.wav`
  - `transcript.json` (word-level)
  - `shots.json`, `faces.json` / `speakers.json`
  - `candidates.json` (LLM) and `clips.json` (approved)
  - per-clip `crop_path.json`, `captions.ass`, `clip_NN.mp4`, `manifest.md`

  Each stage should be skipped if its output exists and is newer than its inputs (the Anil-matcha / artbyjazi pattern). This makes Claude Code sessions resumable after interruptions.
- **Selection contract:** have Claude select by word or segment index (or quote the exact first and last words) rather than free-typed timestamps. Snap boundaries to word ends and sentence boundaries, and dedupe overlapping candidates.
- **Mac setup checks:** use a `doctor` script checking for ffmpeg with libass and videotoolbox, the Python version, model files and yt-dlp cookies. That addresses the most common setup failures before any long job runs.
- **Avoid fragile cloud dependencies** (AssemblyAI, MuAPI, Gemini quotas) where possible. Several projects' top issues are vendor API changes, not their own bugs.

### Gaps
- Issue analysis covered only the top roughly 10-12 issues by comment count for 8 repos. Closed-issue root causes were not read in full.
- No repo published a quantitative failure-rate or quality evaluation. artbyjazi explicitly says its reframe golden-set validation is not done yet.

## Q4. Commercial landscape 2026: pricing, features, and user praise and complaints (the quality bar)

### Takeaway
Mainstream AI clippers cost about $10-$40/month at entry tiers. Most meter by source minutes (about $0.05-$0.10 per source minute on OpusClip) or by clips/videos. The 2026 feature bar includes:

- multimodal moment detection with a virality score
- AI reframe with speaker and object tracking plus split-screen layouts
- animated word-level captions (about 97-98% English accuracy)
- B-roll (stock, AI image and AI video)
- filler/silence removal
- brand templates
- scheduling and auto-posting
- APIs or MCP

Users praise the time savings. They complain about credit burn on long videos, billing and cancellation friction, stalled jobs, and clip picks that still need human curation.

### Cited Findings

**OpusClip** (opus.pro pricing page, captured Nov 2026)

- **Plans:**

  | Plan | Price | Key limits |
  |---|---|---|
  | Free | $0 | Watermarked animated captions; 3-day storage; no text/timeline editing |
  | Starter | $15/mo | Virality score; spoken-word AI clipping; 9:16 reframe; posting to YT Shorts / TikTok / IG without scheduler; 3 B-roll clips/mo |
  | Pro | $29/mo | Clipping on "spoken words, visual objects, sound, emotion, genre curation"; reframe to 9:16/1:1/16:9 with moving-object tracking; AI image B-roll 50 clips/day, unlimited stock, AI video B-roll; scheduler; Video Editing API, Scheduler API, MCP connector, Zapier; up to 4 brand templates; 2 users per pack |
  | Business | Custom | — |

  [OpusClip pricing](https://www.opus.pro/pricing)
- **Credits (third-party):** Free 60 credits/mo; Starter 150 credits/mo, monthly billing only; Pro $14.50/mo billed annually ($174/yr, 3,600 credits up front). 1 credit ≈ 1 minute of source video. That works out to about $0.10 per source minute on monthly plans, versus about $0.048 per minute on annual Pro. Sources disagree on the X-posting credit cost. [Creatify](https://creatify.ai/blog/opusclip-pricing-plans-and-what-you-ll-actually-pay-in-2026); [Castmagic](https://www.castmagic.io/es/blog/opus-clip-pricing); [Quso (competitor)](https://quso.ai/blog/opus-clip-pricing)
- **Complaints:**
  - Billing and cancellation; charges after cancelling.
  - Failed tasks not refunding credits.
  - Stalled or glitchy processing.
  - Output needing heavy editing, with caption and audio errors.
  - Trustpilot is reported at about 4.0/5 over about 300 reviews, about 22% 1-star.
  - Reddit users report "low-scoring clips beating the tool's 'winners'", and that the AI "gives decent ideas but often misses the point".

  All of these are second-hand via review aggregators. [eesel.ai](https://www.eesel.ai/blog/opusclip-reviews); [Trustpilot](https://www.trustpilot.com/review/opus.pro?page=2); [Smart Remote Gigs](https://smartremotegigs.com/software/opusclip/)

**Vizard**

- **Plans (vizard.ai):**
  - Free: 60 credits/mo, uploads up to 60 min / 1 GB, 720p export with a 10-minute max, 3-day storage, 1 social account.
  - Creator: from 600 credits/mo (7,200-74,400/yr), 4K, no watermark, scheduled posts, 6 social accounts.
  - Business: 20 accounts, brand kit, team workspace.
  - The page lists "Auto reframe" and "AI B-rolls" with API rate limits per plan. Prices did not render on the page.

  [Vizard pricing](https://vizard.ai/pricing)
- **Prices (third-party):** Creator $29/mo or $14.50/mo yearly; Business $39/mo or $19.50/mo yearly; billed per minute uploaded. [Ssemble roundup](https://www.ssemble.com/blog/best-ai-clipping-tools-2026); [OpenShorts README comparison table](https://github.com/mutonby/openshorts)

**Klap**

- Has "AI Reframe 2" (split-screen, screencast and gaming layouts), virality scoring and 52 transcription languages. [Ssemble](https://www.ssemble.com/blog/best-ai-clipping-tools-2026)
- **Pricing conflicts between sources:**
  - Basic $14 / Pro $39 / Pro+ $94 per month billed yearly, for 100 / 300 / 1,000 clips per month. [Quso blog (competitor), Sep 2026](https://quso.ai/blog/klap-ai-review-pros-cons-alternatives)
  - Basic $29 / Pro $79 / Pro+ $189. [CostBench, Oct 2026](https://costbench.com/software/ai-video-editing-saas/klap/)
- No free plan beyond a trial. [SaaSworthy](https://www.saasworthy.com/product/klap-app/pricing)

**Submagic**

- Starter $19/mo ($12 yearly; 15 videos, max 2 min each), Pro $39 ($23 yearly; 40 videos, max 5 min), Business $69 ($41 yearly; 100 videos, max 30 min).
- "Magic Clips" long-form clipping is a +$19/mo add-on.
- Known for the strongest caption styling and AI auto-edit (zooms, silence and bad-take removal). [Ssemble](https://www.ssemble.com/blog/best-ai-clipping-tools-2026); [Reap report](https://reap.video/reports/state-of-top-ai-video-clipping-tools-2026)

**Captions / Mirage** (rebranded from Captions to Mirage in 2025)

- Sources disagree: about $10/mo entry and about $25-30/mo Pro, with conflicting free-tier claims. [Toolradar](https://toolradar.com/compare/captions-vs-descript); [xpay](https://www.xpay.sh/saas-pricing/captions-ai)

**Descript**

- Free tier with about 60 media minutes; Hobbyist about $12-16/mo; Creator about $24/mo. Sources are inconsistent and pricing changes often. [dev.to](https://dev.to/techsifted/descript-pricing-2026-hobbyist-creator-or-business-which-is-right-for-you-3p55); [Toolradar](https://toolradar.com/tools/descript-platform/pricing)
- Took about 20 min to first clip in Reap's test. [Reap](https://reap.video/reports/state-of-top-ai-video-clipping-tools-2026)

**Munch**

- The standalone clipper is flagged as discontinued, folded into "Munch Studio". [Reap report, Oct 2026](https://reap.video/reports/state-of-top-ai-video-clipping-tools-2026)

**Quso (formerly vidyo.ai)**

- Free: 75 credits, 720p, quso.ai watermark.
- Lite: $29/mo ($19/mo yearly, 100 credits).
- Essential: $39/mo.
- Growth: $49/mo.

These figures come from Quso's own comparison page. [Quso](https://quso.ai/alternative/2short-ai-alternative)

**2short.ai**

- Free Starter (30 min of analysis per month), Lite $9.90, Pro $19.90, Premium $49.90 per month. [Quso comparison, Oct 2026](https://quso.ai/alternative/2short-ai-alternative); [SaaSworthy](https://www.saasworthy.com/product/2short-ai/pricing)

**Riverside Magic Clips**

- **Plans:**
  - Free includes Magic Clips.
  - Pro: $29/mo ($24/mo annual): "Magic clips & show notes", unlimited transcriptions, AI B-roll, eye contact, silence and filler removal.
  - Grow: $39/mo ($34/mo annual): adds AI thumbnails.
- Magic Clips do not consume AI credits.
- The fetched page appeared to be a staging version, so verify these figures. [Riverside pricing](https://riverside.com/pricing)
- Clipping "works mainly on Riverside recordings". [Ssemble](https://www.ssemble.com/blog/best-ai-clipping-tools-2026)

**Others (vendor-authored sources)**

- Reap: Creator $9.99/mo annual (10 h/mo clipping). [Reap](https://reap.video/reports/state-of-top-ai-video-clipping-tools-2026)
- Choppity: $15/mo ($7.50 yearly) for 3 h uploads. [Ssemble](https://www.ssemble.com/blog/best-ai-clipping-tools-2026)
- Ssemble: $7.50-$50/mo yearly. [Ssemble](https://www.ssemble.com/blog/best-ai-clipping-tools-2026)

**The open-source projects' own framing**

- SupoClip: "OpusClip is genuinely good at what it does — AI clip selection, accurate captions, virality scoring. But your usage is metered by plan, some exports carry platform branding, and your content and workflows live on their s[ervers]". [SupoClip README](https://github.com/FujiwaraChoki/supoclip)
- AI-Youtube-Shorts-Generator targets people who "don't want to pay $20–$300/month or be capped on minutes processed". [README](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator)

### Inferences
- **Cost the local tool replaces:** for an editing-services business processing, say, 20 hours of podcasts a month (1,200 source minutes), OpusClip Pro monthly would need about 4 credit packs. That is roughly $120/mo, or about $58/mo annual, plus seat constraints. This is arithmetic from the about $0.10 and about $0.048 per-minute figures above, not a quoted price. The marginal cost of a local Claude Code-driven tool is the Claude subscription the user already pays, plus electricity.
- **Minimum quality bar to match:**
  - accurate word-level captions with animated / karaoke styles and brand fonts
  - hook-first clips that stand alone, 20-90 s
  - a ranked score with a reason
  - face or active-speaker reframing that handles two-person podcasts (split-screen) and camera cuts without jitter
  - filler and silence trimming
  - safe-zone-aware caption placement
  - per-clip titles, captions and hashtags

  B-roll, auto-posting and analytics feedback loops are differentiators, not table stakes, for a services business.
- **Where local tools can beat SaaS:**
  - no credit metering
  - no watermark
  - human-in-the-loop selection by a frontier model reading the full transcript (Eddie's / podcli's approach)
  - per-client brand presets

### Gaps
- Klap, Captions/Mirage and Descript pricing could not be confirmed from primary vendor pages. Third-party figures conflict (monthly vs annual billing confusion).
- I found no primary Vizard prices (the page rendered `$0`).
- Riverside's fetched pricing page appeared to be a staging copy.
- Direct Reddit threads (r/NewTubers, r/podcasting) were not reachable through search. User sentiment above comes via review aggregators and Trustpilot summaries.

## Q5. Are there benchmarks or blog posts comparing clip quality between tools?

### Takeaway
No independent, blind clip-quality benchmark exists as of Nov 2026. The only quantitative multi-tool test is Reap's vendor-authored report. It measures speed and caption accuracy, not clip-selection quality, and finds English caption accuracy roughly equal (about 97-98%) across major tools. Everything else is affiliate or competitor roundups.

### Cited Findings
- **Reap's report:**
  - **Method:** tested 9 tools on paid plans (about $3,000 spend) with 6 source videos: 90-minute bilingual podcast, 45-minute webinar, 30-minute interview, 12-minute talking head, 45-minute gaming stream, 5-minute sports reel. Measured April 2026; pricing re-verified 27 Oct 2026.
  - **Time to first clip on the 90-minute podcast:**

    | Tool | Time to first clip |
    |---|---|
    | Reap | 4-5 min |
    | Submagic | 8-12 min |
    | Vizard | about 10 min |
    | Veed | about 10-12 min |
    | Munch | 12-15 min |
    | Klap | about 15 min |
    | Descript | about 20 min |
    | OpusClip | about 25 min |

  - **English caption accuracy:** about 98% (OpusClip, Vizard, Submagic, Descript, Reap) and about 97% (Klap).
  - **Gaps in the report:** no independent per-tool clip-quality score; reframing not benchmarked. Reap's only quality figure ("about 1 in 5 generated clips" meets an engagement threshold) is self-reported.

  [Reap report](https://reap.video/reports/state-of-top-ai-video-clipping-tools-2026)
- **Ssemble's "11 Best AI Clipping Tools in 2026"** (Mar 2026) is written by Ssemble's CEO, who ranks Ssemble #1. It contains no test videos or accuracy measurements, and has internal price inconsistencies. [Ssemble](https://www.ssemble.com/blog/best-ai-clipping-tools-2026)
- **Secondhand quality reputations (roundups disagree):**
  - Klap's visuals called "more polished".
  - Klap and Submagic said to lead on caption polish; Submagic's caption styling called the strongest.
  - OpusClip favoured for visual-heavy gaming and sports footage.
  - Vizard recommended for long or transcript-heavy backlogs.

  [Highstyle](https://highstyle.ai/insights/opusclip-vs-submagic-vs-vizard); [Choppity](https://www.choppity.com/blog/best-opus-clip-alternatives/); [Castmagic](https://www.castmagic.io/blog/opus-clip-alternatives)
- **Within open source:**
  - artbyjazi/autoclip: clip quality "tracks model quality closely" (7B local models give mediocre picks; frontier models are better). [README](https://github.com/artbyjazi/autoclip)
  - publikclip says Ollama scoring runs "at reduced scoring quality". [README](https://github.com/Blueturboguy07/publikclip)
- **Eddie's demo:** reports 7 clips of 29-76 s from a 1h43m podcast with no human touch, and claims the skill runs his Instagram at 20 reels/day. These are creator claims, not a benchmark. [Third-party notes](https://github.com/aryan1429/clipping-edit/blob/main/skill/references/02_eddie_claude_clipping_tutorial.md)

### Inferences
- **Selection quality is the real differentiator,** since commodity ASR has converged at about 98% English accuracy. A frontier model (Claude via Claude Code) reading the whole transcript with a strong rubric should be competitive with SaaS "virality scores". Users already report SaaS scores mis-rank clips.
- **Build an in-house eval:** the user should create a small golden set (3-5 episodes with human-picked "best moments") and score recall/precision of picks plus reframe quality. Use artbyjazi's proposed bar: no jitter, no cut-off faces, speaker on screen at least 95% of speaking time. No public benchmark exists to lean on.

### Gaps
- I found no independent (non-vendor) side-by-side test of clip-selection quality, virality-score calibration or reframing quality across OpusClip, Vizard, Klap, Submagic and others.
- I found no published comparison between open-source clippers and commercial tools on the same footage.
