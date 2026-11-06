# Let Claude Choose, Let Scripts Render

Build the Clipper as a Claude Code skill. Claude does only the judgment work: it picks moments by sentence ID, scores them against a gated rubric, writes the on-screen hook and the post caption for each platform, and tags the words to emphasize. Tested Python scripts in a uv-managed Python 3.12 environment do everything else. The 2026 stack that fits an M1 with 16 GB of RAM and about 17 GB of free disk uses no PyTorch. It runs in this order:

1. **yt-dlp** downloads the audio only, using the Node 22 you already have as its JavaScript runtime.
2. **parakeet-mlx** transcribes a two-hour episode in a few minutes, with word timestamps built in.
3. Claude picks clips from a compact transcript.
4. yt-dlp downloads only the chosen sections, with a few seconds of padding on each side.
5. **PySceneDetect** and **MediaPipe Tasks** set one fixed crop per camera shot.
6. One pass of Homebrew **`ffmpeg-full`** burns in ASS captions written by Python, applies hard-cut zooms, mixes in free (CC0) sound effects, normalizes loudness to −14 LUFS and encodes a single 1080×1920 H.264 master for all four platforms.

Borrow the architecture from MIT-licensed projects: autoclip, clipify, joe-jns/long-video-to-shorts, OpenShorts and AI-Youtube-Shorts-Generator. The clipper most tightly built around Claude, podcli, is AGPL, so study it but don't copy its code. Use Claude's virality scores only to decide what to review first. They don't predict performance: in the one third-party test of a commercial scorer, the best-performing clip scored 64 and the weakest scored 87 ([BIGVU](https://bigvu.tv/blog/opus-clip-tested-2026-where-ai-wins-40-percent-discard/)).

The hardest constraints are not technical. The campaign brief is the contract: posting to the wrong platform, missing tags or disclosure, or editing a post after you submit it all forfeit payment ([Content Rewards](https://contentrewards.com/creators)). The creator's permission also does nothing for reach. YouTube applies its reused-content policy "even if you have permission from the original creator" ([YouTube Help](https://support.google.com/youtube/answer/1311392?hl=en)), and Instagram stops recommending accounts that mostly repost other people's content ([TechCrunch](https://techcrunch.com/2026/04/30/instagram-restricts-reach-of-content-aggregators-in-new-crackdown/)). So v1 needs two things built in from the start: the brief stored as a config that a script checks before export, and real originality (unique on-screen text, genuine editorial cuts, and a slot for an optional voiceover).

## Five MIT-licensed projects already show how to structure the skill

Almost every clipper built in 2025–2026 runs the same stages in order. It downloads the video, extracts audio, transcribes with word timestamps, has an LLM pick highlights as JSON, analyzes shots and faces, computes a crop path, burns in captions and encodes. The ones that work well save each stage's output under a job ID, so a failed run resumes where it stopped instead of starting over ([autoclip](https://github.com/artbyjazi/autoclip); [joe-jns](https://github.com/joe-jns/long-video-to-shorts)).

The Claude Code clipping skills have settled on a similar structure:

- a `SKILL.md` that holds the rules, the flow and the approval gates
- deterministic scripts for intake, transcription, cutting, reframing, captions and rendering
- `references/*.md` files for the selection rubric, reframe math and caption style
- a JSON contract between the model and the renderer, such as a `clips.json` checked against a schema

Examples are [clipify](https://github.com/louisedesadeleer/clipify), [joe-jns](https://github.com/joe-jns/long-video-to-shorts) and [mihm88](https://github.com/mihm88/long-video-to-shorts).

Eddie's "Long-Form Clipper" skill splits the work the same way. A third-party transcript of his tutorial says "the LLM's only job is picking moments plus writing the titles and captions", and deterministic Python renders the 1080×1920 output ([tutorial notes](https://github.com/aryan1429/clipping-edit/blob/main/skill/references/02_eddie_claude_clipping_tutorial.md)). The official files are behind a Skool login and could not be inspected, so everything known about the skill is second-hand.

The most useful practical lesson comes from the author of a Claude clipping plugin: **the tool got faster once pre-built Python tools replaced scripts the agent wrote on every run** ([Didier Lopes](https://didierlopes.com/blog/i-built-a-claude-skill-that-turns-podcasts-into-shareable-clips/)). Ship scripts that are already tested, and let Claude coordinate them and make the judgment calls.

| Project (license) | What to take |
|---|---|
| [artbyjazi/autoclip](https://github.com/artbyjazi/autoclip) (MIT) | Per-stage artifacts with resume; the LLM returns word indices instead of timestamps; crop paths that never pan across a camera cut; tuned 1€-filter constants; libass captions; a `doctor` environment check; −14 LUFS export |
| [louisedesadeleer/clipify](https://github.com/louisedesadeleer/clipify) (MIT) | The Claude Code skill layout; speaker detection without a model (motion energy in mouth regions); hard-cut pan expressions for ffmpeg; an ASS builder; VideoToolbox decode |
| [joe-jns/long-video-to-shorts](https://github.com/joe-jns/long-video-to-shorts) (MIT per README; GitHub reports NOASSERTION) | `clips.schema.json` as the shortlist contract; `config.json` for brand settings and safe zones; 8 ASS caption styles; an approval gate |
| [mutonby/OpenShorts](https://github.com/mutonby/openshorts) (MIT) | Per-scene TRACK / GENERAL / SPLIT / SCREENCAST reframe modes; `active_speaker.py` |
| [Anil-matcha/AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) (MIT) | The `VIRALITY_CRITERIA` prompt; a first pass that classifies the content type; score + hook + reason output; dropping candidates that overlap a better one by more than 50%; caching keyed on file modification time |
| [browser-use/video-use](https://github.com/browser-use/video-use) (MIT) | A compact phrase-level transcript as the main input; filmstrip and waveform PNGs generated on demand; an edit list, then render, then a self-check (at most 3 re-renders) |
| [mihm88/long-video-to-shorts](https://github.com/mihm88/long-video-to-shorts) (MIT) | Rights check first; audio-only download first; full-quality video downloaded only for approved segments |

podcli, the clipper most tightly built around Claude Code, is AGPL ([podcli](https://github.com/nmbrthirteen/podcli)). It scores clips using your Claude Code login, exposes 32 MCP tools and a `/produce-shorts` command, keeps a record of published moments so it never suggests them again, and supports cuts made of several segments that drop filler and tangents. Copy those ideas, not its code. Under AGPL, running a tool privately to make videos is fine, but putting AGPL code into a tool you distribute is not.

Two other AGPL projects have ideas worth borrowing:

- [publikclip](https://github.com/Blueturboguy07/publikclip) lowers the LLM's humor score when no laughter is detected in the audio.
- [SupoClip](https://github.com/FujiwaraChoki/supoclip) feeds platform performance metrics back into clip selection.

Avoid these:

- **[ClippedAI](https://github.com/Shaarav4795/ClippedAI):** licensed CC BY-NC 4.0, which forbids commercial use.
- **Repos with no license**, such as egoist/ffmpeg-mcp, which means all rights are reserved.
- **[ClipsAI](https://github.com/ClipsAI/clipsai):** no commits since January 2024, and a community fork already needed patches for pyannote 4.x ([issue #19](https://github.com/ClipsAI/clipsai/issues/19)).
- **[ai-clipper](https://github.com/Rembr4nt/ai-clipper):** requires NVIDIA CUDA.
- **The gooseworks video-clipper skill:** a skills directory flagged it for "exfiltrates credentials via HTTP", and it sends each clip through paid APIs at about $2–3 per clip ([Skills Directory](https://www.skillsdirectory.com/skills/gooseworks-ai-video-clipper)).

Give each episode its own job folder with fixed file names:

- `info.json` and `audio16k.wav`
- `transcript.json`, which holds word timings for the code
- `sentences.txt`, the compact view Claude reads
- `candidates.json` and `clips.json`
- per clip: `shots.json`, `crop.json`, `captions.ass` and `clip_NN.mp4`
- `manifest.md`

Skip any stage whose output is newer than its inputs, as Anil-matcha and autoclip do. That makes an interrupted Claude Code session resumable.

Put the job root on a path without spaces. The project currently lives in "Content Clipping", and that space matters. TalkNet-style scripts break on unquoted paths ([ai-clipper](https://github.com/Rembr4nt/ai-clipper)), and joe-jns runs ffmpeg from a temporary folder with relative paths because the `subtitles` filter breaks on certain path characters ([joe-jns](https://github.com/joe-jns/long-video-to-shorts)).

A skill plus command-line scripts is enough for a single user. An MCP server, such as the Apache-2.0 [kinocut](https://github.com/KyaniteLabs/kinocut), only pays off if other agents later need to drive the tool.

## A stack without PyTorch fits in 16 GB of RAM and 17 GB of disk

The system Python 3.9.6 can't run any of this:

- yt-dlp 2026.10.26 raised its minimum to **Python 3.11** ([release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.10.26)).
- mlx and parakeet-mlx need 3.10 or later ([PyPI](https://pypi.org/project/parakeet-mlx/)).

Use one uv project pinned to Python 3.12. MediaPipe now ships a single arm64 wheel that supports Python 3.9 through 3.14 ([PyPI](https://pypi.org/project/mediapipe/)), so autoclip's warning that it doesn't support Python 3.13 is out of date. Installing everything into one project environment, rather than a separate `uv tool` environment per tool, avoids installing MLX more than once.

The biggest install trap is ffmpeg. Homebrew's plain `ffmpeg` 9.0.2 formula **does not include libass, freetype, harfbuzz or fontconfig**, so it installs cleanly and then can't burn in a single caption. The `ffmpeg-full` formula includes all four, plus rubberband, libvidstab, zimg and libplacebo ([ffmpeg.rb](https://github.com/Homebrew/homebrew-core/blob/HEAD/Formula/f/ffmpeg.rb); [ffmpeg-full.rb](https://github.com/Homebrew/homebrew-core/blob/HEAD/Formula/f/ffmpeg-full.rb); [autoclip](https://github.com/artbyjazi/autoclip)). It is keg-only, meaning Homebrew doesn't add it to your PATH, so put its `bin` folder first on PATH, because yt-dlp and parakeet-mlx both call ffmpeg. To save disk space, don't install the plain formula as well.

| Stage | v1 choice | Why | Fallback or later upgrade |
|---|---|---|---|
| Download | `yt-dlp[default]` + Node 22 via `--js-runtimes node` | YouTube now requires an external JS runtime to solve its challenges; Node ≥22 is supported | `yt-dlp -U`; the `web_safari` client; the bgutil PO-token provider; a throwaway account's cookies |
| Transcription | parakeet-mlx, `parakeet-tdt-0.6b-v2` (English) or `-v3` | Native word timings with start, end and confidence | mlx-whisper `large-v3-turbo` for languages Parakeet doesn't cover |
| Speaker labels (diarization) | None in v1 | Pulls in torch/torchcodec and a gated Hugging Face model; reframing is a visual problem anyway | pyannote community-1, or FluidAudio's CoreML diarizer |
| Clip selection | Claude via Claude Code | Picks track model quality closely | — |
| Shot detection | PySceneDetect `ContentDetector(27)` | Tuned for talking-head footage | `AdaptiveDetector(3.0)` for handheld cameras |
| Faces | MediaPipe Tasks FaceLandmarker at 5 fps | Lip landmarks show who is talking | OpenCV YuNet |
| Captions, zooms, SFX, encoding | `ffmpeg-full` + ASS subtitles | Fastest and free | A Remotion or HyperFrames overlay for richer motion |

**Download.** yt-dlp now has to solve YouTube's JavaScript challenges with an external runtime running the "EJS" solver scripts. **Deno (2.3 or later) is the default**, and **Node 22 or later works with `--js-runtimes node`**. `pip install "yt-dlp[default]"` pulls in the matching `yt-dlp-ejs` package ([yt-dlp EJS wiki](https://github.com/yt-dlp/yt-dlp/wiki/EJS)). Your Node 22 already meets that minimum, so you can skip installing Deno.

The default player clients are now `tv_samsung,visionos,web`, and yt-dlp's wiki says to avoid cookies unless a video requires an account, because "you run the risk of [the account] being banned" ([README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md); [Extractors wiki](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)). The guest limit is about **300 videos per hour**, which is far beyond one link per run.

The sources disagree about whether cookies are needed. autoclip's README claims that in 2026 YouTube blocks most anonymous downloads and that cookies are required ([autoclip](https://github.com/artbyjazi/autoclip)). yt-dlp's own documentation says the default clients avoid PO-token requirements. Run without cookies by default. If downloads start failing, work through this ladder:

1. Update yt-dlp.
2. Try the `web_safari` client.
3. Install the bgutil PO-token provider ([bgutil](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)).
4. Only then pass cookies, from a throwaway account.

**Download audio first and video last.** Audio is all you need to transcribe and select clips, and it's what lets the review pause happen before any video is downloaded (mihm88's pattern). After selection, `--download-sections "*START-END"` fetches only the approved ranges ([README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)). Exact cuts need re-encoding, and `--force-keyframes-at-cuts` is slow ([FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ)). Because the final render re-encodes anyway, a reasonable approach is to download sections with 5–10 seconds of padding, skip that flag, and trim exactly during the render. This is untested: check audio/video sync on a sample. Each section is a separate extraction request, so if a run approves more than about 8 clips, it can be simpler to download the full 1080p file once and delete it after rendering.

**Transcription.** parakeet-mlx running `parakeet-tdt-0.6b-v3`:

- scores **6.34% average WER** on the Open ASR Leaderboard
- returns word-, segment- and character-level timestamps
- covers 25 European languages
- is licensed CC BY 4.0

Source: [model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3).

On a base 8 GB M1 Air it transcribed **11 minutes of audio in about 14 seconds (~47x realtime)** ([issue #4](https://github.com/senstella/parakeet-mlx/issues/4)), which works out to roughly 2.5 minutes for a two-hour episode. Other reported speeds conflict, ranging from 37x on an M2 Air to a vendor claim of 300x ([parakeet-redux](https://huggingface.co/suryatmodulus/parakeet-redux); [MacParakeet](https://macparakeet-website.pages.dev/blog/whisper-to-parakeet-neural-engine)). Benchmark it on your machine.

Three settings matter:

- Keep the default 120-second chunks.
- Call `mx.clear_cache()` or run each stage in a separate subprocess, because memory isn't released between calls ([issue #34](https://github.com/senstella/parakeet-mlx/issues/34)).
- Switch to `--decoding beam` if timestamps jump ([issue #43](https://github.com/senstella/parakeet-mlx/issues/43)).

For languages Parakeet doesn't cover, mlx-whisper with large-v3-turbo ran about **2x faster than whisper.cpp** in a January 2026 benchmark ([Bill Mill](https://notes.billmill.org/dev_blog/2026/01/updated_my_mlx_whisper_vs._whisper.cpp_benchmark.html)). WhisperX is a poor fit for a Mac: it runs on CPU only ([README](https://github.com/m-bain/whisperX)), and it pins torchcodec below 0.8, which conflicts with Homebrew's FFmpeg 9 ([PyPI](https://pypi.org/project/whisperx/)).

YouTube's own auto-captions return only segment-level timing through youtube-transcript-api ([README](https://github.com/jdepoix/youtube-transcript-api)). They can serve as an instant preview while transcription runs, but not as the basis for word-by-word captions.

```bash
brew install ffmpeg-full                         # keg-only; plain `ffmpeg` lacks libass
export PATH="/opt/homebrew/opt/ffmpeg-full/bin:$PATH"
uv python install 3.12 && uv init --python 3.12 clipper && cd clipper
uv add "yt-dlp[default]" parakeet-mlx mediapipe scenedetect
mkdir -p ~/.config/yt-dlp && echo "--js-runtimes node" >> ~/.config/yt-dlp/config

# per run: audio → 16 kHz mono WAV → word-level transcript
uv run yt-dlp --no-playlist --write-info-json -f "ba[ext=m4a]/ba" -o "$JOB/audio.%(ext)s" "$URL"
ffmpeg -i "$JOB/audio.m4a" -ac 1 -ar 16000 -c:a pcm_s16le "$JOB/audio16k.wav"
uv run parakeet-mlx "$JOB/audio16k.wav" --output-format json --output-dir "$JOB"
# after selection: padded sections only
uv run yt-dlp -t mp4 -S "res:1080,vcodec:h264,acodec:aac" \
  --download-sections "*00:41:02-00:42:15" -o "$JOB/sec_%(section_start)s.%(ext)s" "$URL"
```

**Disk budget.** The main way to stay within it is to avoid installs that bring large dependencies:

- **PyTorch:** WhisperX and pyannote both pull it in.
- **Playwright's Chromium:** about 150 MB or more for pycaps ([pycaps](https://github.com/francozanardi/pycaps)).
- **Large local model bundles**, like publikclip's 4–5 GB ([publikclip](https://github.com/Blueturboguy07/publikclip)).

Per-run files are small:

- **16 kHz mono 16-bit WAV** is 32 KB/s, about **115 MB per hour of audio**.
- **A 60-second master** is at most about **120 MB** under the 16 Mbps cap used below.
- **A full 1080p H.264 copy of a two-hour episode** is the big one. It was not measured, but expect several GB. That's why downloading sections is the default.

After a successful render, delete the WAV and the downloaded sections. Keep `transcript.json`, `clips.json`, `manifest.md` and the final clips.

## Claude should cite sentence IDs, never type timestamps

The most important design rule for selection: **never ask the model for raw timestamps**. autoclip puts it this way: "Models are unreliable at arithmetic and completely reliable at copying a number they can see," so the LLM returns word indices that code maps back to measured timings ([autoclip](https://github.com/artbyjazi/autoclip)). imgly's clipper has Gemini return text selections and matches them to word timestamps for the same reason ([imgly](https://github.com/imgly/videoclipper)).

Current Claude models have **1M-token context windows** at roughly 1.8 tokens per word ([Claude models](https://platform.claude.com/docs/en/models/overview)). A two-hour transcript of 25–30k words is therefore only about 45–55k tokens, so you don't need to chunk it. Don't feed Claude raw word-level JSON, which would be five to ten times larger. Have a script build `sentences.txt` with one line per sentence, like `S0412 [01:02:13.4–01:02:17.9] text… ⏸1.2s`, marking pauses of 0.7 seconds or more. Keep the word timings in code. Claude Code's file reader returns long files a page at a time, so either split the sentence file into two to four time-ordered parts or tell the skill to read every page before selecting anything.

Follow Anthropic's long-context guidance ([prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)):

- Put the transcript at the top and the instructions at the end, which "can improve response quality by up to 30 percent".
- Ask Claude to quote the relevant passages before judging them.
- Include three to five `<example>` blocks.
- Validate the JSON in code instead of relying on prefill.

Run selection as a series of passes:

1. **Find candidates, with the full transcript in context.** Ask for two to three times as many candidates as you want to keep (the SamurAIGPT pattern from [highlights.py](https://raw.githubusercontent.com/SamurAIGPT/AI-Youtube-Shorts-Generator/main/shorts_generator/highlights.py)). Each candidate gives a verbatim hook quote, a verbatim payoff quote, start and end sentence IDs, a hook type and a one-line reason. Hook types come from a fixed list: bold claim, contrarian take, surprising stat, story opener, confession, conflict, framework promise, emotional peak, quotable line. Forcing a label makes clips without a real hook obvious.
2. **Refine each candidate's boundaries.** Give Claude the 60–90 seconds on either side. It moves the start to the earliest line that needs no earlier context, extends the end to the payoff, and can optionally drop a tangent in the middle (podcli's multi-segment cuts).
3. **Score each candidate in a fresh context** so it isn't anchored by the others. Claude Code subagents can do this. On a subscription that costs usage, so the cheaper option is to score in a randomized order within one context.
4. **Rank the top 10–15 head to head.** Compare each pair in both orders, and count a win only if both orders agree.

**Code then checks the results.** It confirms each quote actually appears in the transcript (fuzzy match). It snaps the start to the first word's onset minus about 150 ms and the end to the last word's offset plus about 300 ms, enforces the length limits, and drops any candidate that overlaps a higher-scoring one by more than 50%. These millisecond values are engineering estimates, not sourced figures.

Use pass/fail gates first and scores second:

- **Gates:** a stranger understands the clip with no prior context; it ends on a payoff; it starts and ends on sentence boundaries; its length fits the brief; and nothing in it would break Instagram's recommendation guidelines or the campaign's banned-claims list.
- **Scores:** each dimension below is rated 1–5 against written descriptions of what each level looks like, and must come with a verbatim evidence quote.

The weights are a starting guess to calibrate, not values derived from data. Each dimension is tied to something Instagram says it predicts. Its published ranking predicts reshares, watching to the end and likes ([Instagram](https://about.instagram.com/blog/announcements/instagram-ranking-explained)). Mosseri's 2025 list of top signals was **watch time, likes per reach and sends per reach**, and sends matter most for reaching people who don't follow you ([Fanpage Karma](https://www.fanpagekarma.com/insights/instagram-reels-algorithm/)).

| Dimension | Weight | What a 5 looks like | Platform signal it targets |
|---|---|---|---|
| Hook (first ~3 s) | 25% | A specific, surprising claim, stat or question that opens a curiosity loop | Early retention |
| "Send" test | 20% | A viewer would DM it to a specific person | Sends per reach (reaching non-followers) |
| Payoff | 15% | A punchline, number or lesson lands in the last 3 s | Watching to the end |
| Novelty / contrarian | 15% | A non-obvious, counter-consensus or insider point | Shares, comments |
| Emotional intensity | 10% | Laughter, anger, vulnerability, a host-guest clash | Likes |
| Retention density | 10% | Every sentence moves it forward | Total watch time |
| Quotability | 5% | A line that works as on-screen text | Rewatches, hook text |

Write two corrections into the prompt.

**AI selectors prefer loud moments.** A 2026 test of OpusClip found it "favors loud words, emotional tone, and keywords, and struggles with slow-building content" ([BIGVU](https://bigvu.tv/blog/opus-clip-tested-2026-where-ai-wins-40-percent-discard/)). Tell Claude that quiet stories with a strong payoff qualify, and that the best hook often sits in the middle of an answer.

**Rubric judges are biased by the order the options are listed in.** A Findings of EMNLP 2026 paper found that shuffling that order across a few runs and averaging reduces the bias and improves agreement with human judges ([arXiv 2602.02219](https://arxiv.org/abs/2602.02219v1)).

The evidence on hook length is mixed. Most guides say to front-load the hook in the first three seconds, but one creator test found that 6–10 seconds of context won on completion rate and on views after seven days ([AutoClip](https://autoclip.dev/blog/why-3-second-hooks-are-overrated)). Keep "hook first" as the default and treat it as something to A/B test.

**Length.** Socialinsider's study of 9.8 million Reels from January–June 2026 found **45–60-second Reels had the highest median views (10,374)**. Clips under 30 seconds got 4,700, and clips over 3 minutes got 4,428 ([Socialinsider](https://socialinsider.io/blog/instagram-reels-length/)). Instagram's 2026 creator guide calls 15–60 seconds the "primary sweet spot" ([iPhone in Canada](https://www.iphoneincanada.ca/2026/09/28/instagram-shares-ultimate-blueprint-for-viral-reels-in-2026/)).

Target **30–60 seconds** and allow 20–90 seconds, which is safe on all four platforms. The campaign's length rules override this. One caveat: TikTok's Creator Rewards pays only for videos over one minute ([TT Calculator](https://ttcalculator.net/guides/creator-rewards-program/)). Socialinsider's 60–90-second bucket (9,790 median views) is only about 6% below the peak, so a 61–75-second cut costs little on Instagram if you ever need both.

**Treat the scores as a ranking, not a prediction.**

- OpusClip claims a score of 70 or more predicts above-median performance "about 75% of the time", but even OpusClip advises using scores "to rank candidates rather than approve them" ([OpusClip](https://www.opus.pro/blog/viral-moment-detection-api)).
- The BIGVU test of 76 clips found 62% publishable as-is and 13% unusable. Its weakest clip scored 87 ([BIGVU](https://bigvu.tv/blog/opus-clip-tested-2026-where-ai-wins-40-percent-discard/)). The sample is tiny and the test was run by a competitor.
- The best engagement predictors in the research literature use video as well as text ([arXiv 2508.02516](https://www.emergentmind.com/papers/2508.02516)), so transcript-only scoring is a triage aid.

Log each clip's per-dimension scores and its actual results (average watch time, sends per reach), and periodically re-fit the weights against them.

In the same pass, Claude writes the text for each clip:

- **On-screen hook:** 3–8 words that add to the first spoken line rather than repeat it.
- **Short title.**
- **Per-platform post captions:** for Instagram, the hook phrase, one to three lines of context, a credit to the original creator and **no more than 5 hashtags**, which is Instagram's limit since December 2025 ([Business Today](https://www.businesstoday.in/technology/news/story/no-more-hashtag-stuffing-instagram-limits-hashtag-usage-to-just-5-per-reel-and-post-507444-2025-12-19)).
- **Emphasis tags** for the caption renderer.

The review-first pause goes right after `candidates.json` passes validation and before any video is downloaded. It shows rank, duration, hook type, on-screen hook, first and last lines, score and reason, and lets you approve, edit or reorder. In fully automatic mode, the run renders the top N candidates that pass every gate and lists the rest in the manifest.

Keep a `published.json` across runs, like podcli does, so the tool never suggests the same moment twice. If you can fetch the source channel's own Shorts, exclude those moments too: when two posts are identical, Instagram recommends only the original.

## Fixed crops per shot beat smooth tracking on podcast footage

Podcast footage is mostly hard cuts between fixed cameras, and the open-source reframers that look professional handle it the way a human editor would: **hold one fixed crop for each shot, cut to a new crop at each camera change or accepted speaker change, and never pan**. autoclip's rule is that "crop paths never interpolate across a cut… Panning through an edit is the most obvious sign of an auto-reframed video" ([autoclip](https://github.com/artbyjazi/autoclip)). ClippyMe's camera "does not move within a shot", because a zoom that "breathes" feels "seasick" ([ClippyMe](https://github.com/fralapo/clippyme/blob/HEAD/docs/architecture/reframe.md)). Google's AutoFlip has been unsupported since March 2023 and builds only against OpenCV 3, so borrow its ideas but not its code ([AutoFlip docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/autoflip.md)).

Run the analysis on each clip's range only, never the whole episode.

1. **Detect shots.** Use PySceneDetect's `ContentDetector` at its default threshold of **27**, which autoclip says "holds up well on talking-head and podcast footage". Merge shots shorter than **0.8 s** into a neighbor, because reframing across one "looks frantic" ([scenes.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/scenes.py)). TransNetV2 gives inconsistent results on Apple's GPU backend (MPS): 66 versus 108 scenes on the same video ([PyPI](https://pypi.org/project/transnetv2-pytorch/)). Skip it.
2. **Detect faces.** MediaPipe removed the old `mp.solutions` API, so new code must use the Tasks API ([issue #6200](https://github.com/google-ai-edge/mediapipe/issues/6200)). Run FaceLandmarker at **5 fps** on frames scaled to about 960 px wide. autoclip calls the sample rate "the main cost lever", since faces don't move fast enough to need more. Lip landmarks 13/14 and 61/291 give mouth openness, and eye landmarks set headroom ([faces.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/faces.py)). Pin the MediaPipe version and its model files: this API removal shows the package can break without warning.
3. **Build face tracks.** Link detections greedily by box overlap (IoU 0.25) with a maximum gap of 0.8 s ([tracker.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/tracker.py)).

**Choosing the speaker without diarization.** autoclip's best method ties diarized speaker turns to face tracks using mouth-movement variance, measured once per clip ([speaker.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/speaker.py)). v1 skips diarization, so use mouth movement alone:

- A face counts as speaking only if its mouth movement beats the runner-up by **1.6x** (autoclip's dominance margin), measured only while the audio has speech.
- Switch subjects only on turns of at least 1–1.5 s, with a 1.25x hysteresis margin ([ClippyMe config](https://github.com/fralapo/clippyme/blob/HEAD/docs/reference/configuration.md); [ClipsAI](https://www.clipsai.com/references/resize)).
- If nothing is clear, fall back to the largest or most central face.

When multicam podcasts cut to whoever is talking, this mostly reduces to "frame the one face in the shot". The method only has to work in two-person wide shots.

**v2 upgrades for active-speaker detection.** The proper fix is a real audio-visual speaker detector. Light-ASD reaches **94.1% mAP on the AVA benchmark with only 1.0 million parameters**, about 23 times fewer than the previous best model ([arXiv 2303.04439](https://arxiv.org/abs/2303.04439)). It is small enough to run on a CPU, but its research code assumes CUDA, so porting it is about a day of work and is untested. TalkNet integrations require NVIDIA ([ai-clipper](https://github.com/Rembr4nt/ai-clipper)).

**Layouts.** Choose a layout for each shot:

- **Fill:** one face, or one person clearly doing the talking.
- **Split:** two faces stacked top and bottom, each 1080×960, when both are in a wide shot and turns are rapid. ai-clipper's thresholds: each side appears in at least 20% of frames, or a silent second face is at least 65% the size of the speaker's ([talknet_speaker_detection.py](https://github.com/Rembr4nt/ai-clipper/blob/HEAD/scripts/talknet_speaker_detection.py)).
- **Fit:** the full 16:9 frame over a blurred copy of itself, for zero faces or three or more. Blurring at 270×480 and scaling up is about 14x faster ([auto_reframe.py](https://github.com/Rembr4nt/ai-clipper/blob/HEAD/scripts/auto_reframe.py)).

OpusClip notes that split layouts work only "when the speakers appear together in the original video frame" ([OpusClip help](https://help.opus.pro/docs/article/layout-and-reframing)).

**When a guest drifts within a shot.** If the face moves more than about 5–12% of the frame width, smooth the crop with autoclip's chain ([smoothing.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/smoothing.py)):

- a **1€ filter** (min_cutoff 0.6, beta 0.02)
- a **12-pixel dead zone**, because "a frame that micro-corrects reads as broken"
- a **260 px/s speed limit**

**Applying the crop.** Keep the pixels in ffmpeg. Build each shot segment as `trim → crop → scale=1080:1920:flags=lanczos`, with panning (if any) written as a piecewise-linear expression in time. Join the segments in one `filter_complex` so the video is encoded once ([croppath.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/croppath.py)). Use even crop sizes, and keep time values to at least 4 decimal places to avoid rounding errors ([ClipsAI](https://www.clipsai.com/references/resize)).

**Resolution.** A 9:16 crop of a 1080p frame is **608×1080, scaled up about 1.78x**, and each split-screen half is scaled up about 2x. Downloading 4K sections instead of 1080p ones improves sharpness at little disk cost, because only the clips are downloaded.

**Acceptance test.** Use autoclip's own bar, which it hasn't yet validated: "no visible jitter, no cut-off faces, speaker on screen ≥95% of speaking time" ([autoclip](https://github.com/artbyjazi/autoclip)).

## One ffmpeg-full pass finishes captions, zooms and sound

**The default renderer is ffmpeg-full with ASS subtitles generated by Python.** It's free, it runs in one native pass, and it handles everything a podcast clip needs. Remotion is the premium option for smooth per-word "pop" animation, color emoji and sub-pixel zooms:

- **License:** free for an individual or a company of up to 3 employees ([LICENSE.md](https://raw.githubusercontent.com/remotion-dev/remotion/main/LICENSE.md)). Above that, the Automators plan costs **$0.01 per render with a $100/month minimum** ([Remotion terms](https://www.remotion.dev/docs/terms)).
- **Captions:** its `createTikTokStyleCaptions` already groups word tokens into caption pages ([docs](https://www.remotion.dev/docs/captions/create-tiktok-style-captions)).
- **Speed:** much slower, because it renders in headless Chrome.

HyperFrames (Apache-2.0, built for agents) is an HTML-to-MP4 alternative without Remotion's company license ([hyperframes](https://github.com/heygen-com/hyperframes)). pycaps has the right idea, with CSS-styled captions and tags that can come from AI, but it is "very alpha", not on PyPI, and needs Chromium ([pycaps](https://github.com/francozanardi/pycaps)).

| Approach | Est. M1 render, 60 s clip | Strength | Cost |
|---|---|---|---|
| ffmpeg-full + ASS | ~20–60 s (libx264), ~10–25 s (VideoToolbox) | One native pass, no extra dependencies | Free |
| Remotion overlay + ffmpeg composite | ~1–2.5 min | Per-word pop without pushing neighbors, emoji, smooth zooms | Free for ≤3 people |
| Remotion full composition | ~1.5–5 min | Everything in React | Same |
| MoviePy 2 | ~3–10 min | Simple | Free |

All of these timings are engineering estimates. No M1 benchmark exists, and ffmpeg isn't installed on the target Mac yet, so the first spike task is `ffmpeg -benchmark` on a real clip.

**Caption style.** The current podcast-clip look, per caption-tool vendors:

- heavy sans-serif in ALL CAPS
- one to three words on screen, at most about 15 characters per line
- white text with a thick black outline and a drop shadow
- the active word or keyword in yellow or green
- a quick pop-in

Submagic's "new Hormozi" style uses Anton with a pop-in from the bottom ([Submagic](https://www.submagic.co/blog/how-to-make-alex-hormozi-captions)). Use **Montserrat Black** (OFL-licensed, [google/fonts](https://github.com/google/fonts/blob/main/ofl/montserrat/METADATA.pb)) or Anton. Avoid Komika Axis, which DaFont lists as "free for personal use" only ([DaFont](https://www.dafont.com/komika-axis.font)).

ASS details that cause bugs:

- **Colors are in BGR order**, so #FFE600 yellow is written `&H00E6FF&`.
- `\t` animates scale, color and border but **cannot animate `\pos` or `\move`**.
- Karaoke timings are in centiseconds.

Source for all three: [Aegisub](https://aegisub.org/docs/latest/ass_tags/).

ASS can't scale one word without shoving its neighbors sideways. Pop the whole chunk in (80% → 108% → 100% over about 140 ms) and only recolor the active word. libass historically doesn't render color emoji, so overlay emoji as Twemoji or Noto PNGs. That's unverified, so test it once.

**Safe zones.** No platform publishes margins for organic posts. Ad-oriented guides put Instagram's unsafe areas at about **270 px at the top, 670 px at the bottom and 65 px on the sides** ([Revid](https://www.revid.ai/instagram-reels-safe-zone); [AdManage](https://admanage.ai/instagram-reels-safe-zone)), plus **120 px on the right** for the action buttons ([FirstPier](https://www.firstpier.com/resources/instagram-ad-safe-zones)). The cross-platform box is therefore **x 90–960, y 270–1250**:

- **Captions:** centered at **y ≈ 1100–1200**, or on the seam at y ≈ 960 in split layouts.
- **Hook title:** in the top third (y ≈ 300–520), visible from the very first frame so it works as the scroll-stopper and the thumbnail ([Captions.ai](https://captions.ai/help/guides/creators/hook-repurposed-clip)).

TikTok, Shorts and X margins were not researched. Before locking the template, overlay each app's UI screenshot on a test render.

**Keyword highlights.** Combine simple rules with one Claude call per clip. Rules flag numbers, money, percentages, named entities, superlatives and contrast words like "but", "actually" and "nobody". Claude then returns word indices with a tier (primary, secondary, negative) and an optional emoji. Cap it at one keyword per chunk and about 15–25% of chunks. pycaps uses the same "tags as selectors" pattern ([pycaps](https://github.com/francozanardi/pycaps)). Map primary to yellow plus a 110–115% scale, secondary to green and negative to red. Keep the "word being spoken" color separate from the keyword color, or drop active-word coloring altogether so keywords stand out.

**Zooms.** ffmpeg's `zoompan` produces shaky output on moving zooms because of sub-pixel rounding, and the bug (trac #4298) was still open in 2025 ([ffmpeg-trac](https://ffmpeg.org/pipermail/ffmpeg-trac/2025-April/073180.html)). Use **hard-cut punch-ins** instead: a fixed scale for each segment, switching between 1.0 and 1.10–1.25 at sentence or idea boundaries. They have no jitter and read as a second camera angle. For an eased zoom, keep the ramp short (≤250–400 ms) using `scale` with `eval=frame` ([vf_scale.c](https://github.com/FFmpeg/FFmpeg/blob/fa469545ba0782a9245474ecca873aa8984f506e/libavfilter/vf_scale.c)). Apply zooms to the 16:9 source before the 9:16 crop, so the zoom crops into real pixels instead of scaling up an already-cropped frame.

Eddie's skill reportedly uses **13–19 subtle punch-ins of 1.04–1.22x per clip**, placed at sentence ends ([tutorial notes](https://github.com/aryan1429/clipping-edit/blob/main/skill/references/02_eddie_claude_clipping_tutorial.md)). That density matches the rule of thumb of a visual change every 3–6 seconds.

**Sound effects.** Use sounds free for commercial use:

- **Mixkit:** commercial use, no attribution ([Mixkit](https://mixkit.co/llm-info/)).
- **Pixabay:** commercial use, but you can't redistribute the files on their own ([SFX Engine](https://sfxengine.com/blog/free-sound-effects-download)).
- **Freesound:** only sounds marked CC0, never CC-BY-NC ([Soundly](https://getsoundly.com/faq/how-can-i-use-the-freesound-library)).

Placement:

- a whoosh about 100 ms before each zoom or cut
- a pop only on primary keywords, at most one every 2–4 s
- a riser into the payoff
- everything about 10–15 dB below the dialogue

Mix with `amix=normalize=0`, then run `loudnorm` in two passes to reach **−14 LUFS integrated, −1 dBTP**. The single-pass default compresses the audio ([video-use](https://instagit.com/browser-use/video-use/social-media-loudness-normalization-targets/)). −14 LUFS is a social-media convention, not a published Meta spec.

**Encoding the master.** Use 1080×1920, 30 fps, H.264 High at level 4.2, yuv420p and AAC at 48 kHz with `+faststart`, encoded with `libx264 -preset slow -crf 18 -maxrate 16M`. The spec comes from consistent third-party sheets, not Meta ([SocialPilot](https://www.socialpilot.co/instagram-marketing/instagram-video-size)). Use `h264_videotoolbox` for previews: it measured about **2.58x faster** on an M1 ([ffmpeg-user](https://ffmpeg.org/pipermail/ffmpeg-user/2021-October/053727.html)), but it needs more bitrate for the same quality, and its `-q:v` quality setting works only on Apple Silicon ([FFmpeg commit](https://lists.ffmpeg.org/pipermail/ffmpeg-cvslog/2021-March/126704.html)).

Close the loop with an automatic quality check, adapted from video-use (at most 3 re-renders, [video-use](https://github.com/browser-use/video-use)) and podcast-shorts-factory, whose QC agent catches "captions over faces, black or frozen frames and dead air" ([podcast-shorts-factory](https://github.com/krakonjac300-pixel/podcast-shorts-factory)). Render a contact sheet of the finished clip for Claude to inspect.

Render one clean master and upload it natively to each platform. Instagram makes reels carrying other apps' watermarks, borders or low resolution less visible ([Instagram](https://about.instagram.com/blog/announcements/instagram-ranking-explained)), so never re-upload a file downloaded from TikTok.

## Creator permission settles copyright, not reach or payment

**How Content Rewards works.** It is a marketplace run by Whop. A creator funds a campaign with at least $1,000 and sets a rate per 1,000 views, a minimum payout and a cap. The brief's "Requirements" field covers quality standards, brand mentions, prohibited content, length and format, and required messaging, and the brief also supplies the approved footage, usually through a Google Doc or Drive link ([Whop Docs](https://docs.whop.com/memberships-and-access/third-party-apps/content-rewards.md)).

The posting rules:

- Post to the platform the brief names.
- **Submit the link within 30 minutes.**
- Nothing is approved automatically.
- An approved clip **earns for 7 days, followed by a 3-day hold**.
- The official rejection reasons are "wrong platform, missing tags or disclosure, reused content, or editing or deleting the post after submitting" ([Content Rewards](https://contentrewards.com/creators)).
- Every submission gets a bot-likelihood score, and the fee is **10%** ([FAQ](https://contentrewards.com/faqs)).
- If you post on several platforms, check whether each post counts as its own submission ([clip farming](https://contentrewards.com/articles/what-is-clip-farming)).

Real briefs add requirements such as a set bio, link-in-bio and creator tags. One brand reported that "most submissions broke the rules" ([Tanner Chidester](https://tannerchidester.com/i-spent-3000-on-whop-an-honest-review-of-clipping/)). Rates run about **$0.20–$6 per 1,000 views, averaging around $1** ([ClipSpeed](https://www.clipspeed.ai/blog/whop-content-rewards-clipping-guide.html)). After the 10% fee, a clip at that average needs about **111,000 approved views to net $100**. It also has to clear the minimum-payout threshold; in Whop's example, a $6 minimum at $3 per 1,000 views means about 2,000 views before the clip is even reviewed.

**Permission doesn't protect reach.** The creator's permission covers copyright, but each platform still decides how widely to distribute the clip:

- **YouTube.** Its reused-content policy "applies even if you have permission from the original creator". It excludes "clips of moments… edited together with little or no narrative" and accepts footage where "you add a storyline and commentary" ([YouTube Help](https://support.google.com/youtube/answer/1311392?hl=en)). Since October 1, 2026, Shorts has prioritized original content, and channels "primarily aggregating" others' videos get less distribution in the feed ([Tbreak](https://tbreak.com/youtube-shorts-clipping-original-content/)).
- **Instagram.** Since April 30, 2026, accounts that regularly repost content they didn't create are no longer eligible for recommendations. "Unique text, creative edits, and voiceover" count as original; adding a watermark or changing the speed does not ([TechCrunch](https://techcrunch.com/2026/04/30/instagram-restricts-reach-of-content-aggregators-in-new-crackdown/)). Eligibility is judged over a rolling 30-day window ([Engadget](https://engadget.com/2160560/instagrams-recommendation-algorithm-will-penalize-unoriginal-photo-and-carousel-posts)), and **75% of U.S. recommendations now come from posts Instagram's system considers original** ([MediaPost](https://www.mediapost.com/publications/article/414773/instagram-algorithm-update-discourages-reposted-co.html)). Less established outlets report an exemption for accounts that have permission, along with Mosseri's suggestion of a Collab post with the creator ([BrandSpur](https://brandspurng.com/2026/05/04/instagram-restricts-algorithmic-reach-for-content-aggregator-accounts-in-major-policy-update/)). TechCrunch didn't mention an exemption, so don't count on it. Instagram has no way to know a clipper has permission unless the post is a Collab.
- **TikTok.** It can make an entire account temporarily ineligible for the For You feed ([TechCrunch via Yahoo](https://www.yahoo.com/tech/tiktok-block-users-feed-repeatedly-155549425.html)).

Because campaigns pay per view, losing recommendation reach cuts income directly, even though the account isn't banned.

**Design responses.**

**1. Store the brief as a campaign config the tool enforces.** The fields:

| Group | Fields |
|---|---|
| Platforms and pay | `platforms[]`, rate, minimum and maximum payout |
| Footage | footage source and approved episodes |
| Clip rules | minimum and maximum length |
| Required text | required caption text, hashtags and mentions; disclosure tag; bio and link-in-bio |
| Restrictions | banned claims; whether watermarks are allowed; music rules; allowed countries |
| Process | whether drafts need pre-approval; whether each platform is a separate submission; end date |

A pre-publish linter blocks export when required strings or disclosure are missing, the length is out of range, or the caption contains a banned claim. Those checks map directly onto the official rejection reasons. Paid clips also need ad disclosure, which many clipping posts leave out ([ContentGrip](https://www.contentgrip.com/clipping-creator-marketing-strategy/)).

**2. Check the footage source.** The brief defines which footage you may use, and YouTube's Terms forbid downloading without permission from YouTube itself, separate from the creator's permission ([YouTube ToS](https://www.youtube.com/static?template=terms)). So the run should confirm the link's video ID is in the brief's approved list, and add an ingest path for local or Drive files for campaigns that supply their own footage.

**3. Make `manifest.md` the posting checklist.** It holds:

- the post text for each platform, with the required strings locked and the hook line free so each post reads differently
- a reminder of the 30-minute submission window
- a "do not edit after submitting" warning

**4. Make originality features standard.** That means the on-screen hook text, editorial cuts that drop filler and tangents, and a slot for a voiceover or commentary intro in v2. Vendor guidance says a network of accounts posting the same exported files with matching captions on a schedule is what gets flagged ([OpenClip](https://openclip.app/clipping/running-multiple-clipping-accounts)). Make each account's cut genuinely different, and don't build features whose purpose is to make identical uploads look different to duplicate detection. Content Rewards itself separates real clipping from "attempts to manipulate engagement" ([clip farming](https://contentrewards.com/articles/what-is-clip-farming)).

## Conclusion

On this Mac, compute is not the bottleneck. Transcription, framing and encoding take minutes. The limits are whether the platforms will recommend the clips and whether the brief is followed. The few-percent framing improvements a heavier speaker detector would buy matter less than whether a clip carries unique text, cuts that show real editing, and every required tag, because a single missed tag or a slide into "aggregator" status wipes out a clip's payout entirely. Choosing the clips is the other place to invest. English caption accuracy is now about 98% across the major tools ([Reap](https://reap.video/reports/state-of-top-ai-video-clipping-tools-2026)), so the remaining quality differences come from which moments get picked. A Claude subscription makes multi-pass judging nearly free at the margin, which SaaS tools charging by the source minute can't match.

Two things follow for the build. First, run the measurements the research couldn't find before writing any pipeline code: parakeet-mlx speed on your M1, ffmpeg-full render time, A/V sync on padded section downloads, and libass emoji support. Second, treat the review pause as more than a quality gate. It is where checking the brief and adding originality cost the least: no video has been downloaded yet, every clip's text can still be edited, and some campaigns require draft approval anyway. "Fully automatic" should therefore mean automatic up to that gate, until three to five episodes with hand-picked best moments, plus a log of real outcomes, show that Claude's choices agree with yours.
