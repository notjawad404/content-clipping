# Download + Transcription Layer for a Local Podcast Clipper (Apple Silicon M1, late 2026)

Research date: 2026-11-07. Versions were checked live against GitHub Releases, PyPI and Homebrew on that date. Anything dated before 2025 is marked **[STALE?]**.

Version snapshot (checked 2026-11-07):

| Component | Latest version (date) | Python req. | Source |
|---|---|---|---|
| yt-dlp | 2026.10.26 (2026-10-26) | **>=3.11** | [GitHub release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.10.26), [PyPI](https://pypi.org/project/yt-dlp/) |
| yt-dlp-ejs (JS challenge solver scripts) | 0.8.0 (2026-03-17) | >=3.10 | [yt-dlp/ejs](https://github.com/yt-dlp/ejs), [PyPI](https://pypi.org/project/yt-dlp-ejs/) |
| Homebrew: yt-dlp / deno / ffmpeg / whisper-cpp | 2026.10.26 / 2.9.8 / 9.0.2 / 1.9.5 | n/a | [formulae.brew.sh](https://formulae.brew.sh/formula/yt-dlp) (`brew info` output) |
| bgutil-ytdlp-pot-provider | 2.0.2 (2026-10-07) | >=3.8 | [GitHub](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) |
| youtube-transcript-api | 1.2.5 (2026-11-05) | >=3.8,<3.16 | [GitHub](https://github.com/jdepoix/youtube-transcript-api) |
| parakeet-mlx | 0.7.0 (2026-11-04) | >=3.10 | [PyPI](https://pypi.org/project/parakeet-mlx/) |
| mlx | 0.32.4 (2026-10-14) | >=3.10 | [PyPI](https://pypi.org/project/mlx/) |
| mlx-whisper | 0.4.3 (2025-08-29) | >=3.8 (but mlx needs >=3.10) | [PyPI](https://pypi.org/project/mlx-whisper/) |
| whisper.cpp | v1.9.5 (2026-10-06) | n/a (C++) | [GitHub](https://github.com/ggml-org/whisper.cpp) |
| pywhispercpp | 1.5.1 (2026-08-22) | >=3.8 | [PyPI](https://pypi.org/project/pywhispercpp/) |
| faster-whisper | 1.2.1 (2025-10-31) | >=3.9 | [GitHub](https://github.com/SYSTRAN/faster-whisper) |
| WhisperX | 3.8.6 (2026-05-25) | **>=3.10,<3.14** | [PyPI](https://pypi.org/project/whisperx/) |
| pyannote.audio | 4.0.7 (2026-06-30) | >=3.10 | [GitHub](https://github.com/pyannote/pyannote-audio) |
| sherpa-onnx | v2.0.1 (2026-10-26) | n/a | [GitHub](https://github.com/k2-fsa/sherpa-onnx) |
| WhisperKit (Swift/CoreML) | v1.1.1 (2026-10-08) | n/a | [GitHub](https://github.com/argmaxinc/WhisperKit) |
| FluidAudio (Swift/CoreML/ANE) | v0.18.2 (2026-11-01) | n/a | [GitHub](https://github.com/FluidInference/FluidAudio) |
| lightning-whisper-mlx | 0.0.10 (2024-04-02), last push 2024-05 **[STALE]** | none declared | [GitHub](https://github.com/mustafaaljadery/lightning-whisper-mlx) |
| insanely-fast-whisper | 0.0.15 (2024-05-27) **[STALE]** | >=3.8 | [GitHub](https://github.com/Vaibhavs10/insanely-fast-whisper) |

---

## 1. yt-dlp in 2025–2026: anti-bot measures (PO tokens, SABR, JS runtime/EJS, cookies) and reliable flags for 1080p 1–3 h podcasts

### Takeaway
On a home (residential) Mac IP, yt-dlp 2026.10.x works without cookies or PO tokens once you have **(1) Python >=3.11 or the standalone binary, (2) a JS runtime (Deno >=2.3.0 is the default; Node >=22 works with `--js-runtimes node`), and (3) the `yt-dlp-ejs` solver scripts**, which are bundled in the standalone binaries and in `pip install "yt-dlp[default]"`. YouTube has moved the `web` client to SABR-only streaming and requires PO tokens for some clients. yt-dlp works around this by defaulting to the `tv_samsung,visionos,web` clients. Cookies and PO-token plugins are fallbacks, and using cookies puts the Google account at risk of a ban.

### Cited Findings
**JS runtime / EJS (new hard requirement since late 2025)**
- To download from YouTube, yt-dlp must solve YouTube's JavaScript challenges with an external JS runtime running the "EJS" solver scripts from `yt-dlp-ejs`. This replaces the old JSInterp/PhantomJS approach for YouTube. — [yt-dlp wiki: EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
- Supported runtimes: **Deno (recommended, enabled by default, min 2.3.0)**, Node (enable with `--js-runtimes node`, **min v22.0.0**), QuickJS/QuickJS-NG (`--js-runtimes quickjs`), and Bun (deprecated, only 1.2.11–1.3.14 supported). Deno runs the code with no filesystem or network access. — [yt-dlp wiki: EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
- How to get the EJS scripts depends on the install: the official PyInstaller binaries (`yt-dlp_macos`) and the zipimport `yt-dlp` executable bundle them. PyPI installs need `pip install -U "yt-dlp[default]"`, which pulls `yt-dlp-ejs`. Third-party packages such as **brew** may or may not ship it, and if they don't you add `--remote-components ejs:npm` (Deno/Bun only) or `--remote-components ejs:github`. The `yt-dlp-ejs` version **must match** what that yt-dlp version's `pyproject.toml` pins, or yt-dlp ignores it. — [yt-dlp wiki: EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
- Some old QuickJS versions (before 2025-4-26, or QuickJS-NG before 0.12.0) can take "several minutes" per challenge. — [yt-dlp wiki: EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
- An experimental Apple WebKit JS challenge provider plugin, `yt-dlp-apple-webkit-jsi`, is maintained by a yt-dlp maintainer. It is an alternative to installing Deno on macOS. — [yt-dlp wiki: EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
- Release 2026.06.09 raised the minimums to Deno v2.3.0 and Node v22+ and deprecated Bun. — [yt-dlp 2026.06.09 release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.06.09)
- Release 2026.10.26 raised the **minimum required Python to 3.11** (Python 3.10 reached EOL in October 2026). — [yt-dlp 2026.10.26 release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.10.26); README: "Python versions 3.11+ (CPython and PyPy) are supported" — [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)

**Player clients / SABR / PO tokens**
- The default `player_client` is now **`tv_samsung,visionos,web`**. Without a JS runtime, `web` and `tv_samsung` are dropped. With logged-in cookies, the defaults become `web_embedded,tv_samsung,web` (free account) or `web_creator,tv_samsung,web` (Premium). — [yt-dlp README, YouTube extractor args](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- Recent changes: `tv_samsung` became a default client in 2026.10.21, and `android_vr` was removed from the defaults in 2026.08.19. — [yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases)
- SABR: YouTube removed the `adaptiveFormats` playback URLs for the `web` client, leaving only SABR (YouTube's custom streaming protocol) URLs. Issue #12482, "`web` only has SABR formats", was opened Feb 2025 and is **still OPEN** (last updated 2026-08-18). — [yt-dlp issue #12482](https://github.com/yt-dlp/yt-dlp/issues/12482)
- PO token enforcement by client: `web` needs PO tokens for Subs and GVS and has only SABR formats. `web_safari` provides HLS (m3u8) formats that need no GVS PO token "at this time". `mweb` needs a GVS token. `tv` needs no token, but all formats are DRM'd unless cookies are passed. `android_vr` needs no token but can't play "made for kids" videos. `ios`/`android` need GVS or Player tokens. YouTube Premium accounts never need a GVS token. — [yt-dlp wiki: PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)
- PO tokens are now **bound to the video ID**, so manual extraction is "no longer recommended". The recommended setup is a PO Token Provider plugin supplying `mweb` GVS tokens. The featured plugins are `bgutil-ytdlp-pot-provider` and `yt-dlp-getpot-wpc` (which uses a real browser), both maintained by yt-dlp maintainers. Without a token, affected clients' format URLs "may return HTTP Error 403, or result in your account or IP address being blocked." — [yt-dlp wiki: PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)
- The Extractors wiki says yt-dlp by default "will attempt to download videos using clients that do not currently require a PO Token". If the default clients fail, it suggests the `mweb` client with a PO Token. — [yt-dlp wiki: Extractors](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)
- bgutil-ytdlp-pot-provider v2.0.2 has two parts: an HTTP server on **port 4416** (Docker image, or native with Node >=22 / Deno >=2.0.0) or a per-call generation script, plus a yt-dlp plugin. When publishing the Docker port, bind it to `127.0.0.1` only. — [bgutil-ytdlp-pot-provider README](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)

**Cookies, "Sign in to confirm you're not a bot", rate limits, ban risk**
- Cookies are "only necessary for content that requires an account" (private, age-restricted, members-only). **"By using your account with yt-dlp, you run the risk of it being banned (temporarily or permanently)…consider using a throwaway account."** — [yt-dlp wiki: Extractors](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)
- YouTube rotates account cookies in open browser tabs. For cookies that keep working, log in from a private window, go to `https://www.youtube.com/robots.txt`, export the cookies with an extension, then close the window. Don't use `--cookies-from-browser` to build the cookie file in that case, because it exports the main profile, not the private session. — [yt-dlp wiki: Extractors](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)
- **OAuth login no longer works** with yt-dlp. — [yt-dlp wiki: Extractors](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)
- Rate limits: guest sessions get about **300 videos/hour (~1000 webpage/player requests/hour)** and accounts about **2000 videos/hour**. Going over shows "This content isn't available, try again later". The fix is a 5–10 s delay between downloads (`-t sleep`). — [yt-dlp wiki: Extractors](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)
- `-t sleep` = `--sleep-subtitles 5 --sleep-requests 0.75 --sleep-interval 10 --max-sleep-interval 20`. — [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- HTTP 429 means an IP soft-block. Solve the CAPTCHA in a browser, then pass that browser's cookies (and the same IP via `--source-address`). — [yt-dlp FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ)
- YouTube throttles any request with an HTTP chunk size above 10 MB. — [yt-dlp FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ)
- A 2026 dev post found that Chrome 127+ app-bound cookie encryption broke cookie extraction on **Windows** (only Firefox's SQLite cookies worked) and that cookies expired in about 2 weeks. The author was on Windows, and the post does not cover macOS. — [DEV: 6 ways to get YouTube cookies for yt-dlp in 2026](https://dev.to/osovsky/6-ways-to-get-youtube-cookies-for-yt-dlp-in-2026-only-1-works-2cnb)
- The "Sign in to confirm you're not a bot" error mostly hits cloud/datacenter IPs (Render, AWS, Heroku) because of IP reputation. Fixes are updating yt-dlp, `--cookies-from-browser`, residential proxies, or PO tokens (community sources, not official). — [MusicBot wiki](https://github.com/umutxyp/MusicBot/wiki/YouTube-Access), [technetexperts](https://www.technetexperts.com/?p=11741)

**Sections vs. whole file**
- `--download-sections "*10:15-inf"` downloads a time range (a `*` prefix means a time range, negative times count from the end, and the option can be repeated). It needs ffmpeg. — [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- "Video files cannot be cut at exact timestamps without re-encoding." yt-dlp doesn't re-encode by default. `--force-keyframes-at-cuts` re-encodes for exact cuts and "is slow". — [yt-dlp FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ), [README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- The `-t mp4` preset = `--merge-output-format mp4 --remux-video mp4 -S vcodec:h264,lang,quality,res,fps,hdr:12,acodec:aac`. — [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- Security: since 2026.06.09, `--exec` only allows safe conversions (use `%(...)q`, not `%(...)s`). CVEs were fixed in the `--downloader curl` and `--downloader aria2c` paths. — [yt-dlp 2026.06.09 release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.06.09)

### Inferences
- **Recommended download config (local Mac, residential IP):**
  ```bash
  brew install deno ffmpeg            # deno 2.9.8 >= 2.3.0 minimum
  uv tool install --python 3.12 "yt-dlp[default]"   # pulls yt-dlp-ejs; avoids system Python 3.9.6
  # (alternative: the standalone yt-dlp_macos binary from GitHub releases bundles EJS + its own Python)
  yt-dlp -U   # or: uv tool upgrade yt-dlp  — update often; YouTube breakage is fixed within days

  # Whole podcast, 1080p, H.264 + AAC in MP4 (easiest for ffmpeg/Remotion downstream):
  yt-dlp -t mp4 -S "res:1080,vcodec:h264,acodec:aac" \
    -o "%(id)s/source.%(ext)s" --write-info-json --no-playlist \
    --concurrent-fragments 4 "https://www.youtube.com/watch?v=VIDEO_ID"

  # Audio-only first (fast; ~1/10 the size) for transcription:
  yt-dlp -f "ba[ext=m4a]/ba" -o "%(id)s/audio.%(ext)s" "URL"
  ffmpeg -i VIDEO_ID/audio.m4a -ac 1 -ar 16000 -c:a pcm_s16le VIDEO_ID/audio16k.wav

  # Only the chosen clip ranges, frame-accurate (re-encodes, slow but small):
  yt-dlp -t mp4 -S "res:1080" --download-sections "*00:41:12-00:42:05" \
    --force-keyframes-at-cuts -o "%(id)s/clip_%(section_start)s.%(ext)s" "URL"
  ```
  If Deno isn't installed, Node 22 works: add `--js-runtimes node` (put it in `~/.config/yt-dlp/config`).
- **Pipeline design:** download **audio first**, transcribe, let the AI pick clips, then fetch video. For 1–3 clips per episode, `--download-sections` with a few seconds of padding saves bandwidth and disk. Each section call re-runs extraction, though, so it counts against the request rate limit. If you expect 5–15 clips, or want to iterate on clip boundaries, download the full 1080p file once and cut locally with ffmpeg. That costs fewer YouTube requests and makes re-cuts free and exact.
- File size (estimate, not measured): a 2-hour talking-head podcast at 1080p H.264 typically runs a few GB. VP9/AV1 streams are smaller, but H.264 is friendlier for later decode/encode steps.
- **Account and IP risk for a personal tool:** a single user downloading a few podcasts a day from a home IP is far below the ~300 videos/hour guest limit. **Don't pass cookies by default.** Only add `--cookies` (from a throwaway account) when a video is age-restricted, members-only or bot-gated. Adding `-t sleep` for batch or playlist runs is cheap insurance.
- If downloads start failing with 403s, first run `yt-dlp -U` (and update `yt-dlp-ejs`). Next try `--extractor-args "youtube:player_client=default,web_safari"` (HLS formats without a GVS PO token). After that, install bgutil-ytdlp-pot-provider and use `--extractor-args "youtube:player_client=mweb"`.
- macOS cookie extraction (from general knowledge, not verified in this research): Chrome's app-bound encryption is a Windows feature. On macOS, `--cookies-from-browser chrome` reads the "Chrome Safe Storage" Keychain item (expect a Keychain prompt), `firefox` works directly, and `safari` usually needs Full Disk Access for the terminal.

### Gaps
- I found no official statement of how YouTube decides to flag a residential IP, or of whether long (2–3 h) downloads are riskier than short ones. The documented limits are counted per video and per request, not per byte.
- I couldn't confirm whether the current Homebrew `yt-dlp` formula bundles `yt-dlp-ejs`. Run `yt-dlp -v` and check the "JS Challenge Providers"/EJS debug lines, or just use the uv/pip `[default]` install or the standalone binary.
- I found no data on how reliable `--download-sections` is for SABR-only cases or very long (3 h+) DASH streams.

---

## 2. YouTube's own captions (youtube-transcript-api, `yt-dlp --write-auto-subs`): word-level quality and use as a fast first pass

### Takeaway
YouTube captions download in seconds and are good enough for **clip selection** (an LLM reading the text), but they are a weak base for **word-level animated captions**. `youtube-transcript-api` returns only **segment-level** `start`/`duration`. Per-word offsets reportedly exist only in auto-generated (ASR) tracks in the json3/srv3 formats, they aren't guaranteed for every video, and nobody has published an accuracy measurement of them. Since local Parakeet on an M1 transcribes a 2-hour file in minutes, YouTube captions are mainly useful as an instant preview or a fallback.

### Cited Findings
- youtube-transcript-api returns `FetchedTranscriptSnippet(text, start, duration)` objects plus `is_generated`, which flags auto-generated tracks. There are no per-word timings. It also supports auto-generated subs and translation, with no headless browser. — [youtube-transcript-api README](https://github.com/jdepoix/youtube-transcript-api)
- "YouTube has started blocking most IPs that are known to belong to cloud providers (like AWS, Google Cloud Platform, Azure, etc.)" (`RequestBlocked`/`IpBlocked`). The recommended workaround is rotating residential proxies (Webshare integration). — [youtube-transcript-api README](https://github.com/jdepoix/youtube-transcript-api)
- youtube-transcript-api v1.2.5 was released 2026-11-05, so it is actively maintained. — [GitHub releases](https://github.com/jdepoix/youtube-transcript-api/releases)
- yt-dlp supports `--write-auto-subs` and `--sub-format FORMAT` (a format preference list, e.g. `json3`, `srv3`, `vtt`). — [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- For the `web` client, subtitle requests need a PO token ("Subs"). The `-t sleep` preset adds `--sleep-subtitles 5`. — [PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide), [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- Auto-generated YouTube captions have word-level timestamps in the json3 format. This comes from a user feature request to a transcript-API vendor, so it is a weak source. — [Supadata feedback: fetch json3 word-level timestamp data](https://feedback.supadata.ai/p/fetch-json3-word-level-timestamp-data-for-auto-gen-yt)
- A third-party scraper parses JSON3/VTT and returns word timings "when available in the source captions", which suggests not every video has them. — [Apify YouTube Transcript Scraper](https://apify.com/epicscrapers/youtube-transcript-scraper.md)

### Inferences
- **Fast first-pass command:**
  ```bash
  yt-dlp --skip-download --write-auto-subs --write-subs --sub-langs "en.*" \
         --sub-format json3 -o "%(id)s/yt" "URL"
  ```
  Parse the `events[].segs[].tOffsetMs` fields in the json3 file for approximate word starts (format details come from general knowledge, so verify on a sample). The VTT version of auto-subs carries inline `<00:00:01.234><c>word</c>` tags.
- **Trade-off:** YouTube ASR quality and punctuation vary by channel, and manually uploaded captions often lack word timings entirely. Timing is approximate, with word *starts* only (no end times). Captions can be missing or disabled, and fetching them is another request to YouTube. For a karaoke-style animated caption, where each word lights up as it's spoken, you want start **and** end per word from a local model.
- **Suggested use:** (a) as an optional "instant preview" while local ASR runs, so the LLM can draft candidate clips in under 10 s, or (b) as the fallback transcript when local ASR is unavailable (an 8 GB machine under memory pressure). Final caption timing should always come from local ASR on the actual downloaded audio. If YouTube serves an edited version, its caption timestamps can also drift from the file you downloaded.
- Parakeet-mlx takes about 1–3 minutes for a 2-hour file on an M1 (see Q3), so a two-tier design only buys a couple of minutes of latency. Keep it out of v1 unless instant UX matters.

### Gaps
- I found no published accuracy figure (WER or timing error in ms) for YouTube auto-captions compared with local models, and no official doc for the json3 schema.
- It's unclear how often json3 word offsets are missing on podcast-length (1–3 h) videos.

---

## 3. Local transcription on M1 with word-level timestamps: mlx-whisper, lightning-whisper-mlx, whisper.cpp, faster-whisper, WhisperX, insanely-fast-whisper, parakeet-mlx, distil/turbo

### Takeaway
For English (or the 24 other European languages), **parakeet-mlx with `parakeet-tdt-0.6b-v3` (or the English-only `-v2`) is the best default on an M1**. It roughly matches or beats Whisper large-v3 on accuracy, runs about 50x+ realtime on an 8 GB M1 Air (a 2-hour podcast in about 2–3 min), produces native word and token timestamps with confidence scores, chunks automatically to fit in 8 GB, and installs with one `uv` command. For other languages, use **mlx-whisper with `whisper-large-v3-turbo` and `word_timestamps=True`**, which is about 2x faster than whisper.cpp in the most recent comparison. On the Mac, WhisperX, faster-whisper and insanely-fast-whisper are CPU-only, memory-hungry or stale. Use WhisperX only if you want wav2vec2 forced alignment and accept CPU speeds plus some dependency pain.

### Cited Findings
**parakeet-mlx (NVIDIA Parakeet TDT on MLX)**
- Install: `uv tool install parakeet-mlx -U` (CLI) or `uv add parakeet-mlx -U`, with ffmpeg required. The default model is `mlx-community/parakeet-tdt-0.6b-v3`. `--highlight-words` puts word-level timestamps in SRT/VTT, `--output-format json` writes full output, and the Python API returns `AlignedSentence`/`AlignedToken` objects with start, end, duration and confidence. — [parakeet-mlx README](https://github.com/senstella/parakeet-mlx)
- Long audio: chunking defaults to **120 s chunks with 15 s overlap**, and `--local-attention` cuts memory for unchunked long audio. Precision defaults to bf16. Beam decoding (`--decoding beam`) is available for TDT models. — [parakeet-mlx README](https://github.com/senstella/parakeet-mlx)
- **M1 8 GB Air: 11 minutes of audio in about 14 seconds** (~47x realtime), but larger files ran out of memory before chunking was added in v0.2.3. With `chunk_duration=60`, RAM rose about 1.7 GB during inference. (This is from an early-2025 issue thread, so current versions are likely the same or faster.) — [parakeet-mlx issue #4](https://github.com/senstella/parakeet-mlx/issues/4)
- Memory isn't released between `.transcribe()` calls in a loop. Fix: `mx.clear_cache()` plus `gc.collect()`, or run transcription in a subprocess. — [parakeet-mlx issue #34](https://github.com/senstella/parakeet-mlx/issues/34)
- Abnormal timestamp jumps (a 15 s jump, with sentences lost) were reported and fixed when using beam decoding. — [parakeet-mlx issue #43](https://github.com/senstella/parakeet-mlx/issues/43)
- Model card for parakeet-tdt-0.6b-v3: 600M parameters, **Open ASR Leaderboard average WER 6.34%**, LibriSpeech clean/other 1.93/3.59, Earnings-22 11.42, AMI 11.31. Gives **word-, segment- and character-level timestamps**, punctuation and capitalization, and auto-detects among 25 European languages. Handles up to 24 min with full attention or up to 3 h with local attention (on an A100). License **CC BY 4.0**. — [nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- Parakeet TDT 0.6B v2 (English-only) scores 1.69% WER on LibriSpeech test-clean, compared with 1.55B parameters for Whisper large-v3. — [MacParakeet blog, Feb/Mar 2026](https://macparakeet-website.pages.dev/blog/whisper-to-parakeet-neural-engine)
- MacParakeet's numbers: parakeet-mlx on the GPU used about 2 GB RAM and reached about **300x realtime on M1** (6.3% WER internally). Their later FluidAudio (CoreML/Neural Engine) backend reached **~155x realtime on M1 (60 min in about 23 s)** with about 66 MB working memory, and returns words with timestamps and confidences. These are vendor/app-developer figures. — [MacParakeet blog](https://macparakeet-website.pages.dev/blog/whisper-to-parakeet-neural-engine)
- These speeds conflict with a September-2026-era model card that measured parakeet-mlx (fp32) at **37x realtime on an M2 Air 16 GB GPU**, versus parakeet.cpp Metal at 38–39x and sherpa-onnx int8 CPU at 28x. That test used a 50-utterance LibriSpeech slice of short clips, where per-call overhead dominates. — [parakeet-redux model card](https://huggingface.co/suryatmodulus/parakeet-redux)

**mlx-whisper (Apple MLX port of OpenAI Whisper)**
- Install with `pip install mlx-whisper` plus `brew install ffmpeg`. CLI is `mlx_whisper audio.mp3 --model mlx-community/whisper-large-v3-turbo`. The API `mlx_whisper.transcribe(f, path_or_hf_repo=..., word_timestamps=True)` returns `segments[i]["words"]`. The default model is `whisper-tiny`, so always set the model explicitly. — [mlx-examples/whisper README](https://github.com/ml-explore/mlx-examples/tree/main/whisper)
- January 2026 hyperfine benchmark (M1 Ultra 32 GB per search summary; audio length not stated): **mlx_whisper with whisper-large-v3-turbo averaged 13.1 s, against 26.7 s for whisper.cpp ggml-large-v3-turbo, about 2.0x faster** (1.78x in the author's 2024 test). The author notes turbo is "somewhat slower than the distil models". — [Bill Mill, Jan 2026](https://notes.billmill.org/dev_blog/2026/01/updated_my_mlx_whisper_vs._whisper.cpp_benchmark.html)
- **[STALE? 2024]** A 2024 counter-test on an M1 Pro with mismatched/quantized models had whisper.cpp ahead (1m vs 1m36). A follow-up with matched models found mlx-whisper 30–40% faster. — [Bill Mill 2024 link blog](https://notes.billmill.org/link_blog/2024/08/mlx-whisper.html)
- Vendor guide: Apple Silicon with 8 GB+ gets about **4x realtime with large-v3-turbo** (Superwhisper context, not mlx specifically). Turbo is about 1.6 GB. — [getvoibe Superwhisper guide](https://www.getvoibe.com/resources/best-local-whisper-model-superwhisper/)
- Early PyTorch Whisper apps ran large-v3 at about **1x realtime on an M1 with nearly 4 GB RAM**. — [MacParakeet blog](https://macparakeet-website.pages.dev/blog/whisper-to-parakeet-neural-engine)

**whisper.cpp**
- On Apple Silicon "inference runs fully on the GPU via Metal". An optional Core ML encoder on the ANE is ">3x faster compared with CPU-only", but building it needs Python `coremltools`, Xcode CLT, `./models/generate-coreml-model.sh` and `cmake -DWHISPER_COREML=1`. The first run is slow while the ANE compiles. An alternative ANEForge encoder is about 2x faster than Core ML for tiny through medium. — [whisper.cpp README](https://github.com/ggml-org/whisper.cpp)
- Word-level timestamps are **"experimental"**, via `-ml 1` (`--max-len 1`). `whisper-cli` accepts **only 16-bit WAV**. Silero VAD (`--vad -vm ggml-silero-v6.2.0.bin`) is supported. Memory: large is 2.9 GiB on disk and about 3.9 GB in RAM, medium about 2.1 GB. — [whisper.cpp README](https://github.com/ggml-org/whisper.cpp)
- Homebrew: `brew install whisper-cpp` gives v1.9.5. Python bindings: `pywhispercpp` 1.5.1. — [Homebrew](https://formulae.brew.sh/formula/whisper-cpp), [PyPI](https://pypi.org/project/pywhispercpp/)

**faster-whisper / WhisperX (CTranslate2 backend)**
- WhisperX: "To run on CPU instead of GPU (**and for running on Mac OS X**): `whisperx audio.wav --compute_type int8 --device cpu`". GPU acceleration is CUDA-only. — [WhisperX README](https://github.com/m-bain/whisperX)
- The "Support M1 Mac's GPU" feature request, #109, is **still open** (last activity May 2026). Error #878 occurs when float16 is requested on unsupported backends, so use int8 on Mac. — [whisperX #109](https://github.com/m-bain/whisperX/issues/109), [#878](https://github.com/m-bain/whisperX/issues/878)
- WhisperX gets accurate word timestamps through **wav2vec2 phoneme forced alignment**, because raw Whisper timestamps are utterance-level and "can be inaccurate by several seconds". Limitation: words with no characters in the alignment model's dictionary (e.g. "2014.", "£13.60") get **no timing**. Default align models exist for en/fr/de/es/it, with others pulled from HF. Optional `whisperx[fast]` (Numba) speeds alignment 30–100x. — [WhisperX README](https://github.com/m-bain/whisperX)
- WhisperX paper (Interspeech 2023, **[STALE? 2023]** but still the reference): reports state-of-the-art word segmentation on long-form benchmarks. — [Bain et al. 2023](https://www.isca-archive.org/interspeech_2023/bain23_interspeech.pdf)
- WhisperX 3.8.6 dependency pins: `torch~=2.8.0`, `torchaudio~=2.8.0`, **`torchcodec>=0.6.0,<0.8.0` on darwin**, `pyannote-audio>=4.0.0`, `faster-whisper>=1.2.0`, `huggingface-hub<1.0.0`. Requires Python >=3.10,<3.14. — [PyPI whisperx metadata](https://pypi.org/project/whisperx/)
- torchcodec uses the system FFmpeg. Current torchcodec (0.17) supports FFmpeg 4–9, but **FFmpeg 8 support only arrived in torchcodec 0.8.0** for Linux and Mac. — [torchcodec README](https://github.com/meta-pytorch/torchcodec), [torchcodec v0.8.0 release](https://github.com/meta-pytorch/torchcodec/releases/tag/v0.8.0)
- Homebrew's default `ffmpeg` is now **9.0.2**. Keg-only `ffmpeg@7` (7.1.5) and `ffmpeg@8` (8.1.3) are available. — Homebrew `brew info` (2026-11-07), [formulae.brew.sh/ffmpeg](https://formulae.brew.sh/formula/ffmpeg)
- faster-whisper README CPU benchmark (13 min audio, small model, **Intel i7-12700K**, not a Mac; versions from late 2024 **[STALE?]**): faster-whisper int8 took 1m42s (1477 MB), batched int8 51s (3608 MB), and whisper.cpp fp32 2m05s (1049 MB). — [faster-whisper README](https://github.com/SYSTRAN/faster-whisper)
- faster-whisper is compatible with `distil-large-v3` and `turbo` and supports `word_timestamps=True`. — [faster-whisper README](https://github.com/SYSTRAN/faster-whisper)

**insanely-fast-whisper, lightning-whisper-mlx (both stale)**
- insanely-fast-whisper on a Mac needs `--device-id mps`. "The mps backend…is way more memory hungry": `--batch-size 4` uses **about 12 GB**. It supports `--timestamp word`. The last release was May 2024. — [insanely-fast-whisper README](https://github.com/Vaibhavs10/insanely-fast-whisper)
- lightning-whisper-mlx claims "10x faster than Whisper CPP, 4x faster than current MLX Whisper" through batched decoding, distilled models and quantization. Its README doesn't document word-level timestamps, and the last push was May 2024. — [lightning-whisper-mlx README](https://github.com/mustafaaljadery/lightning-whisper-mlx)

**CoreML / ANE alternatives (Swift)**
- WhisperKit (Argmax) runs Whisper on CoreML/ANE: 2.2% WER for optimized large-v3-turbo and about 15–30x realtime for large-v3 via CoreML (as cited by MacParakeet). — [MacParakeet blog](https://macparakeet-website.pages.dev/blog/whisper-to-parakeet-neural-engine), [WhisperKit paper](https://arxiv.org/html/2507.10860v1)
- FluidAudio (Swift SDK, Apache 2.0) runs Parakeet ASR and pyannote-style diarization on the ANE. v0.18.2 was released 2026-11-01. — [FluidAudio GitHub](https://github.com/FluidInference/FluidAudio)

### Inferences
**Comparison for a 2-hour English podcast on an M1.** Speeds are extrapolated from the cited figures, so measure on the target machine.

| Engine | Est. wall time, 2 h audio, M1 | Word timestamps | RAM working set | 8 GB M1? | Install friction | Verdict |
|---|---|---|---|---|---|---|
| **parakeet-mlx, tdt-0.6b-v3/v2** | ~25 s (300x claim) to ~2.5 min (47x measured on M1 Air) | Native (TDT token durations), with start, end and confidence | ~2 GB (+~1.7 GB chunked) | Yes, keep default 120 s chunking | Very low (`uv tool install`) | **Default** |
| mlx-whisper, large-v3-turbo | ~15–30 min if the ~4x-realtime guide holds for base M1. Faster on Pro/Max | Cross-attention DTW (Whisper-style); typically OK, can drift on music, silence or overlap | ~2–3 GB | Yes (turbo) | Low | Multilingual fallback |
| whisper.cpp (Metal, ± CoreML) | ~2x slower than mlx-whisper for turbo per the Jan-2026 benchmark | `-ml 1`, "experimental" | ~1.5–3.9 GB | Yes | Low via brew. CoreML build is moderate | Use only for a no-Python or C++ embed |
| WhisperX (CPU int8) + wav2vec2 align | CPU-bound. Probably close to or slower than realtime for large models on M1 (no M1 benchmark found) | Best-documented forced alignment, but numbers and symbols go untimed | 3–6 GB+ | Tight | **High** (torch 2.8 pin, torchcodec<0.8 vs brew FFmpeg 9) | Not recommended on Mac in v1 |
| faster-whisper (CPU) | CPU only. Same speed class as above | DTW-style | 1.5–4 GB | OK with small/turbo int8 | Low | Not needed when MLX exists |
| insanely-fast-whisper (MPS) | Fast but needs ~12 GB at batch 4 | HF pipeline word ts | ~12 GB | **No** | Medium | Skip (stale, memory) |
| lightning-whisper-mlx | Fast | Not documented | Low | Yes | Low | Skip (stale since 2024, no word timestamps) |

- **Word-timestamp accuracy (qualitative):** TDT models predict each token's duration directly, so they give natively timed tokens. Whisper's `word_timestamps` infers timing from cross-attention after the fact and is known to drift. Wav2vec2 forced alignment (WhisperX) is the classic way to fix Whisper timings. For an animated word-highlight caption, Parakeet's native timings are likely good enough without an alignment pass, but no numeric benchmark backs this (see Gaps). If any words look off, a cheap fix is to forced-align only the selected 30–90 s clip windows with a CTC aligner, rather than the whole 2-hour file.
- **Hallucination risk:** Whisper models (including turbo) are known to hallucinate or loop on long silences and music beds, a common pattern in podcast intros and outros. Run VAD first (Silero) or prefer Parakeet. This is general knowledge and wasn't re-verified here.
- **Language check:** Parakeet v3 covers only 25 European languages. For Urdu, Hindi, Arabic, Japanese and so on, route to mlx-whisper large-v3-turbo (or large-v3 on 16 GB). Use Whisper's language ID or Parakeet's auto-detect plus a confidence threshold to pick the engine.
- **8 GB vs 16 GB:**
  - **8 GB M1:** parakeet-mlx with the default 120 s chunks (or 60 s if under memory pressure) works well. mlx-whisper turbo is fine. Avoid large-v3 full, insanely-fast-whisper, and running ASR plus diarization plus a local LLM at the same time. Run each stage as its own process (or call `mx.clear_cache()`) so unified memory is freed between stages.
  - **16 GB M1:** everything above works, including mlx-whisper large-v3, sequential pyannote diarization, and parakeet with larger chunks or local attention.
- **distil-whisper:** English-only and decoder-distilled. It is faster than turbo but generally less robust. Now that large-v3-turbo and Parakeet exist, there's little reason to pick distil-large-v3 for this pipeline.

### Gaps
- I found **no independent, apples-to-apples M1 base-model benchmark** on a 1–2 h podcast across parakeet-mlx, mlx-whisper turbo and whisper.cpp. The per-hour figures above are extrapolated from an M1 Air 11-min test, an M1 Ultra clip of unknown length, M2 short-utterance tests and vendor claims. They conflict, from 37x up to 300x for parakeet-mlx. Benchmark on the target machine before committing.
- I found **no published millisecond-level word-timestamp error comparison** for Parakeet TDT, Whisper DTW and WhisperX against a common reference.
- No measured speed exists for WhisperX on M1 CPU.
- mlx-whisper's last PyPI release was 2025-08-29, and the mlx-examples repo was last pushed 2026-04. It works, but it is in maintenance mode. Watch for MLX API breakage with mlx 0.32+.

---

## 4. Speaker diarization on Mac: pyannote community-1, HF token, MPS/CPU speed, alternatives, and whether v1 needs it

### Takeaway
pyannote.audio 4.0.7 with **`speaker-diarization-community-1`** is the open default. It requires accepting the model's terms on Hugging Face plus a read token, runs on MPS at roughly 20–25x realtime on recent Apple Silicon (about 5–10+ min for a 2-hour podcast on a base M1, by estimate), and brings a heavy torch/torchcodec/FFmpeg stack. **Diarization can be skipped in v1.** An LLM can pick clips from plain text, and speaker-aware reframing is better driven by visual face or active-speaker detection. Add diarization later for per-speaker caption colors and "who said it" metadata, ideally through a CoreML backend.

### Cited Findings
- Setup: install ffmpeg (needed by `torchcodec`), `uv add pyannote.audio`, accept the user conditions on `pyannote/speaker-diarization-community-1`, then create an HF access token. Load with `Pipeline.from_pretrained("pyannote/speaker-diarization-community-1", token="HF_TOKEN")`. — [pyannote-audio README](https://github.com/pyannote/pyannote-audio)
- pyannote.audio 4.0.7 requires `torch>=2.8.0`, `torchaudio>=2.8.0` and **`torchcodec>=0.7.0`**, with Python >=3.10. — [PyPI pyannote.audio](https://pypi.org/project/pyannote.audio/)
- DER (benchmark updated 2025-09; lower is better): community-1 vs legacy 3.1 vs paid precision-2. **AMI-IHM 17.0 / 18.8 / 12.9**, **VoxConverse 11.2 / 11.2 / 8.5**, DIHARD3 20.2 / 21.4 / 14.7. "community-1 brings significant improvement in terms of speaker counting and assignment" over 3.1. — [pyannote-audio README](https://github.com/pyannote/pyannote-audio)
- Speed on an **NVIDIA H100**: community-1 took 31 s per hour of audio (AMI), precision-2 self-hosted 14 s per hour. — [pyannote-audio README](https://github.com/pyannote/pyannote-audio)
- On an Apple **M4 Pro**, pyannote community-1 on **MPS** ran at about **24x realtime** (VoxConverse dev, 7.2% DER, 2999 s total) and about 23x on VoxConverse test. The Rust/CoreML reimplementation `speakrs` reports **529–631x realtime** at the same DER. These are self-reported by a competing project. — [speakrs README](https://docs.rs/crate/speakrs/latest/source/README.md)
- MacParakeet bundles a pyannote Community-1 pipeline through FluidAudio (CoreML), measured at about 15% DER and **about 122x realtime**. — [MacParakeet blog](https://macparakeet-website.pages.dev/blog/whisper-to-parakeet-neural-engine)
- WhisperX diarization uses pyannote `speaker-diarization-community-1`. It needs `--hf_token` plus accepting the model conditions, and assigns speakers to words with `whisperx.assign_word_speakers`. The README says plainly: **"Diarization is far from perfect."** — [WhisperX README](https://github.com/m-bain/whisperX)
- sherpa-onnx (v2.0.1, Oct 2026) is an ONNX Runtime toolkit with ASR including Parakeet. Parakeet int8 runs at 28x realtime on an M2 CPU in one test. — [sherpa-onnx GitHub](https://github.com/k2-fsa/sherpa-onnx), [parakeet-redux benchmark](https://huggingface.co/suryatmodulus/parakeet-redux)

### Inferences
- **Do you need it for v1? No.**
  - *Clip selection:* LLMs find self-contained, high-hook moments from text alone. Speaker labels help at the margin, for example "prefer clips where the guest answers", but aren't essential.
  - *Speaker-aware vertical reframing:* the crop has to follow whoever is **on screen**. That is a vision problem (face detection plus active-speaker detection, or lip motion), and in multi-camera podcast edits the visible person isn't always the voice. Audio diarization alone can't tell you where to crop, so drive v1 reframing with face tracking.
  - *Captions:* single-color captions are fine for v1. Per-speaker colors are a v2 feature.
- **If you add it:** run pyannote **after** ASR in a separate process, on the same 16 kHz mono WAV, and pass the waveform as an in-memory tensor dict (`{"waveform": tensor, "sample_rate": 16000}`) so torchcodec never has to decode. The tensor-dict input comes from general pyannote knowledge, so verify it for 4.x. Use `pipeline.to(torch.device("mps"))`. Set `min_speakers`/`max_speakers` when the guest count is known (for example 2–3) to reduce speaker-count errors. Merge speakers onto Parakeet words by timestamp overlap, the same logic as `assign_word_speakers`.
- **Estimate for an M1:** the base M1 GPU is much weaker than an M4 Pro, so expect well under 24x realtime, roughly 10–20x and about 6–12 min for 2 hours. This is an unmeasured extrapolation. On CPU only it would be slower still.
- **Friction and failure modes:**
  - the HF terms-acceptance step (a gated model returns 401/403 until accepted)
  - the torch and torchcodec dylib/FFmpeg version matching (see Q5)
  - MPS ops occasionally falling back to CPU
  - over- or under-counting speakers on crosstalk and laughter
- **Alternatives ranked for the Mac:** (1) pyannote community-1 on MPS, the simplest in Python. (2) A FluidAudio CoreML diarizer through a small Swift CLI helper (fastest and least memory, but Swift). (3) `speakrs` (Rust/CoreML, very fast, young and self-benchmarked). (4) sherpa-onnx speaker diarization (ONNX, CPU, no HF gate). NeMo's Sortformer/MSDD diarizers are CUDA-oriented, and I found no Mac story for them.

### Gaps
- I found no measured pyannote community-1 speed on a **base M1** (MPS or CPU).
- I couldn't confirm that sherpa-onnx's diarization DER matches pyannote community-1, or that FluidAudio ships a ready-made CLI (as opposed to a Swift SDK).
- I didn't verify the exact pyannote 4.x API for in-memory waveform input or for MPS support guarantees.

---

## 5. Recommended concrete stack and commands for an M1 Mac (Homebrew, uv, Python 3.11/3.12; system Python is 3.9.6)

### Takeaway
Don't use the system Python 3.9.6 for anything: yt-dlp now needs **>=3.11**, and mlx, parakeet-mlx, pyannote and WhisperX need **>=3.10** (WhisperX also needs **<3.14**). Use a uv-managed **Python 3.12** project venv. The recommended v1 stack is **Homebrew ffmpeg + deno**, **yt-dlp[default] via uv**, **parakeet-mlx** (English/European) with **mlx-whisper large-v3-turbo** as the multilingual fallback, **no diarization in v1**, and an optional **YouTube json3 captions** instant preview.

### Cited Findings
- yt-dlp supports Python 3.11+ only (3.10 support was removed in 2026.10.26). — [yt-dlp 2026.10.26 release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.10.26)
- Python requirements on PyPI: parakeet-mlx >=3.10, mlx >=3.10, pyannote.audio >=3.10, whisperx >=3.10,<3.14, yt-dlp-ejs >=3.10. — [PyPI parakeet-mlx](https://pypi.org/project/parakeet-mlx/), [PyPI mlx](https://pypi.org/project/mlx/), [PyPI pyannote.audio](https://pypi.org/project/pyannote.audio/), [PyPI whisperx](https://pypi.org/project/whisperx/), [PyPI yt-dlp-ejs](https://pypi.org/project/yt-dlp-ejs/)
- parakeet-mlx recommends uv (`uv add parakeet-mlx -U` / `uv tool install parakeet-mlx -U`). — [parakeet-mlx README](https://github.com/senstella/parakeet-mlx)
- pyannote recommends `uv add pyannote.audio`. — [pyannote-audio README](https://github.com/pyannote/pyannote-audio)
- Node >=22 is a supported yt-dlp JS runtime via `--js-runtimes node`, and Deno is the default runtime. — [yt-dlp wiki: EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
- WhisperX pins torchcodec <0.8 on macOS, and FFmpeg 8 support only arrived in torchcodec 0.8. Homebrew's default ffmpeg is 9.0.2, and `ffmpeg@7` is available as keg-only. — [PyPI whisperx](https://pypi.org/project/whisperx/), [torchcodec v0.8.0](https://github.com/meta-pytorch/torchcodec/releases/tag/v0.8.0), Homebrew `brew info ffmpeg@7`

### Inferences
**Install (one time):**
```bash
brew install ffmpeg deno            # ffmpeg 9.0.2, deno 2.9.8
# (uv already installed)
uv python install 3.12

# CLI tools, isolated:
uv tool install --python 3.12 "yt-dlp[default]"      # includes yt-dlp-ejs
uv tool install --python 3.12 parakeet-mlx           # CLI: parakeet-mlx
uv tool install --python 3.12 mlx-whisper            # CLI: mlx_whisper (fallback)

# Or as libraries in the app project:
mkdir clipper && cd clipper
uv init --python 3.12
uv add "yt-dlp[default]" parakeet-mlx mlx-whisper youtube-transcript-api
# later, v2 diarization (separate process recommended):
# uv add pyannote.audio torch   # then accept HF terms for pyannote/speaker-diarization-community-1, export HF_TOKEN
```

**Run (per episode):**
```bash
ID=VIDEO_ID; URL="https://www.youtube.com/watch?v=$ID"
# 1) metadata + audio
yt-dlp --no-playlist --write-info-json -f "ba[ext=m4a]/ba" -o "work/$ID/audio.%(ext)s" "$URL"
ffmpeg -y -i work/$ID/audio.m4a -ac 1 -ar 16000 -c:a pcm_s16le work/$ID/audio16k.wav
# 2) word-level transcript (JSON has sentences -> tokens with start/end/confidence)
parakeet-mlx work/$ID/audio16k.wav --output-format all --highlight-words --output-dir work/$ID
#    (non-European language → fallback)
# mlx_whisper work/$ID/audio16k.wav --model mlx-community/whisper-large-v3-turbo --word-timestamps True -f json -o work/$ID
# 3) AI selects clips from transcript → list of (start,end)
# 4) video: whole file (many clips) or per-section (few clips)
yt-dlp -t mp4 -S "res:1080,vcodec:h264" -o "work/$ID/source.%(ext)s" "$URL"
#   or: yt-dlp -t mp4 -S "res:1080" --download-sections "*START-END" --force-keyframes-at-cuts ...
```
Check the exact mlx_whisper flag names with `mlx_whisper -h`. The README documents only `word_timestamps=True` in the Python API.

**Python-side notes:**
- Call parakeet through the API, `from_pretrained("mlx-community/parakeet-tdt-0.6b-v3").transcribe(path, chunk_duration=120, overlap_duration=15)`, then flatten `result.sentences[*].tokens` into words. Tokens are sub-word pieces, so join tokens that don't start with a space into the previous word.
- To free memory before the next stage, call `mx.clear_cache()` or run each stage in its own subprocess.
- For English-only content, try `mlx-community/parakeet-tdt-0.6b-v2`, the English-specialized model with the strong LibriSpeech score.

**Known failure modes checklist:**
1. `yt-dlp` errors about JS challenges or "n challenge" → Deno missing or too old (<2.3), or `yt-dlp-ejs` missing or mismatched. Reinstall `yt-dlp[default]` and run `-U`.
2. HTTP 403 on formats → PO-token enforcement or SABR changes. Update first, then try the `web_safari`/`mweb` clients plus the bgutil POT provider.
3. "Sign in to confirm you're not a bot" / 429 → IP reputation. On a home Mac this is rare, so slow down (`-t sleep`) and only then try throwaway-account cookies.
4. Using the system `python3` (3.9.6) by accident → import or install failures. Always run through `uv run` or `uv tool`.
5. WhisperX/pyannote: `torchcodec` can't load `libavutil` → FFmpeg major-version mismatch. Install `ffmpeg@7` (keg-only) and point `DYLD_LIBRARY_PATH` at it, or avoid torchcodec decoding by passing waveforms in memory. The WhisperX case is the most likely to hit this, given its `torchcodec<0.8` pin and Homebrew's FFmpeg 9.
6. Parakeet OOM on 8 GB → keep chunking on (don't set `--chunk-duration 0`) or lower it to 60 s. Memory growth in a long-running worker → `mx.clear_cache()`.
7. Whisper hallucination loops on silence or music → use VAD, or prefer Parakeet.
8. Timestamp jumps with Parakeet greedy decoding (reported for Japanese) → `--decoding beam`.

**Cloud fallbacks (brief; batch prices per audio hour, third-party compiled Aug 2026; verify on vendor pages):**
- OpenAI `whisper-1` $0.36/h, `gpt-4o-transcribe` about $0.36/h, `gpt-4o-mini-transcribe` about $0.18/h — [diyai.io pricing comparison, 2026-08-11](https://diyai.io/ai-tools/speech-to-text/speech-to-text-api-pricing/)
- Deepgram Nova-3 pre-recorded $0.462/h, with diarization +$0.12/h — [diyai.io](https://diyai.io/ai-tools/speech-to-text/speech-to-text-api-pricing/)
- AssemblyAI Universal-2 $0.15/h, Universal-3.5 Pro $0.21/h, with diarization +$0.02/h — [diyai.io](https://diyai.io/ai-tools/speech-to-text/speech-to-text-api-pricing/)
- Early-2026 figures from another source: OpenAI Whisper and AssemblyAI $0.006/min, Deepgram $0.008/min, Google and AWS $0.024/min — [MacParakeet blog](https://macparakeet-website.pages.dev/blog/whisper-to-parakeet-neural-engine). These conflict with the Aug-2026 AssemblyAI and Deepgram figures above because pricing changed and the products differ.
- At $0.15–0.46/h, a cloud fallback costs well under $2 per 3-hour podcast. It's worth wiring one in as an optional "accuracy mode" or for unsupported languages, provided the API returns **word-level** timestamps. Deepgram, AssemblyAI and whisper-1 `verbose_json` with word granularity have historically done so. From general knowledge, gpt-4o-transcribe historically did **not** return word timestamps, so verify this.

### Gaps
- I didn't verify ElevenLabs Scribe batch pricing from a vendor or fetched page. A search summary cited "Scribe v2 batch ~$0.22/h" from an unidentified comparison site, so treat it as unconfirmed.
- I didn't verify from vendor docs whether each cloud API returns word-level timestamps in 2026.
- I haven't tested end-to-end the claim that `uv tool install "yt-dlp[default]"` alone (without brew yt-dlp) gives a working EJS setup with Homebrew Deno. The wiki says it should.
