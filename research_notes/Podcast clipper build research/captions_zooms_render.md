# Editing + Render Stage: Viral-Style Captions, Punch-In Zooms, SFX for 9:16 Reels on Apple M1

Scope: input = vertical 1080x1920 clip + word-level timestamps; output = finished Instagram Reel. Research date 2026-11-07. Target machine checked locally: Apple M1, 16 GB RAM, 8 cores, Node v22.22.0, uv 0.13.1, **ffmpeg not yet installed** (local `sysctl`/`brew info`/`node --version` on 2026-11-07).

---

## 1. Rendering approaches compared (ASS/libass, Remotion, MoviePy 2, pycaps/captacity, Blender/other)

### Takeaway
For a local, free, fast pipeline the best default is **ffmpeg (the `ffmpeg-full` Homebrew formula, NOT plain `ffmpeg`) + Python-generated ASS subtitles burned in via libass**, with zooms and SFX done in the same ffmpeg filtergraph. Choose **Remotion** instead (or as an overlay renderer) only if you want richer motion graphics (color emoji, spring "pop" per word without reflow, smooth sub-pixel push-ins, hook cards). It is free for an individual or a company of up to 3 people, otherwise at least $100/month on the Automators plan. pycaps is the closest off-the-shelf "Hormozi captions" library (MIT, CSS-styled), but it is alpha. MoviePy 2 and captacity are simple but slow and limited.

### Cited Findings

**Critical install pitfall (Homebrew ffmpeg):**
- The current Homebrew `ffmpeg` formula (stable 9.0.2) has only 11 required deps: dav1d, lame, libvmaf, libvpx, openssl@4, opus, sdl2-compat, svt-av1, x264, x265, xz. **libass, freetype, harfbuzz and fontconfig are not among them.** — local `brew info ffmpeg` on 2026-11-07; [Homebrew ffmpeg.rb](https://github.com/Homebrew/homebrew-core/blob/HEAD/Formula/f/ffmpeg.rb)
- `ffmpeg-full` (stable 9.0.2, **keg-only**, so not symlinked into /opt/homebrew/bin) includes libass, freetype, harfbuzz, fontconfig, rubberband, libvidstab, zimg, libplacebo, libsoxr, whisper.cpp/ggml, x264, x265 and others (47 deps). The formula caveat says it "includes additional tools and libraries that are not included in the regular ffmpeg formula." — local `brew info ffmpeg-full`; [Homebrew ffmpeg-full.rb](https://github.com/Homebrew/homebrew-core/blob/HEAD/Formula/f/ffmpeg-full.rb)

**(1) ASS/SSA via libass (ffmpeg `subtitles`/`ass` filter):**
- Karaoke tags `\k`, `\kf` (=`\K`, left-to-right sweep) and `\ko` take durations in **centiseconds**. `\k` switches from secondary to primary colour instantly at syllable start. — [Aegisub ASS tags](https://aegisub.org/docs/latest/ass_tags/)
- Animation uses `\t(t1,t2,accel,tags)`, with times in **ms relative to line start**. accel=1 is linear, <1 starts fast and ends slow (ease-out), >1 is ease-in. It can animate font size, scale, spacing, rotation, shear, border, shadow, blur, colours and alpha. It **cannot animate `\pos`, `\move` or `\an`**. — [Aegisub ASS tags](https://aegisub.org/docs/latest/ass_tags/)
- `\fscx`/`\fscy` are percentages. The docs recommend animating scale instead of `\fs`, because font size changes alter hinting. — [Aegisub ASS tags](https://aegisub.org/docs/latest/ass_tags/)
- Colours are written `&H<bb><gg><rr>&`, i.e. **BGR order, the reverse of HTML**. `\1c` is fill, `\2c` is karaoke pre-highlight, `\3c` is border, `\4c` is shadow. — [Aegisub ASS tags](https://aegisub.org/docs/latest/ass_tags/)
- `\bord` sets the outline width. `\shad` is the shadow distance (`\xshad`/`\yshad` allow negatives). `\blur` takes non-integer values and "can be CPU-intensive at high values." — [Aegisub ASS tags](https://aegisub.org/docs/latest/ass_tags/)
- A line can have only one positioning/movement tag. `\move` runs at constant speed only (no easing, no chaining). — [Aegisub ASS tags](https://aegisub.org/docs/latest/ass_tags/)
- Existing tooling builds karaoke captions with ASS + ffmpeg libass on Apple Silicon (an MLX-Whisper-based "karaoke-captions" agent skill: Python 3.10+, ffmpeg with libass). — [skills.sh karaoke-captions](https://www.skills.sh/ai-builder-club/skills/karaoke-captions)
- The R `subtitles` package writes word-level ASS from Whisper tokens (`whisper_to_ass(karaoke=)`) and burns it with the ffmpeg subtitles filter (ffmpeg ≥5.0 with libass). This is a useful reference design. — [CRAN subtitles README](https://stat.ethz.ch/CRAN/web/packages/subtitles/readme/README.html)
- The Python `lattifai-captions` library (PyPI) emits `{\k}` tags automatically for ASS output through a karaoke_effect setting. — [PyPI lattifai-captions](https://pypi.org/project/lattifai-captions/)

**(2) Remotion (React):**
- **License:** free for "an individual", "a for-profit organization with up to 3 employees", non-profits, and evaluation. Everyone else needs a Company License. — [Remotion LICENSE.md](https://raw.githubusercontent.com/remotion-dev/remotion/main/LICENSE.md)
- **Pricing:** Remotion for Creators is "$25 per Seat per month, with no minimum number of Seats". **Remotion for Automators is "$0.01 per render... charged in increments of 1000 renders (i.e., $10), with a Minimum Spend of $100 per month."** Enterprise has a "Minimum Spend of $500 per month". A render is "outputting a video, an audio file, a still image, or an image sequence." The Company License threshold is a combined headcount of 4 or more. — [Remotion Terms](https://www.remotion.dev/docs/terms). Caveat: the fetched terms page is labelled "Terms and Conditions of Remotion (v5.0)… takes effect when Remotion 5.0 is released; v4.0 is currently in effect." The same $25/seat and $0.01/render ($100 minimum) figures were reported for the current model by search summaries of [remotion.dev/docs/license/pricing](https://www.remotion.dev/docs/license/pricing) and the [License FAQ](https://www.remotion.dev/docs/license/faq). Third-party sites listing annual $150/$250/$500 tiers or "$10 per 1,000 renders with 4 seats" conflict with Remotion's own pages and look stale.
- **Captions API:** `createTikTokStyleCaptions({captions, combineTokensWithinMilliseconds})` groups word tokens into "pages". A small value gives word-by-word display and a large value packs more words per page. `breakOnSilenceAfterMilliseconds` (v4.0.514+) starts a new page after a pause (0 means word-by-word). A per-caption `pageBreakAfter` flag (v4.0.517+) forces breaks. Each page has `text`, `startMs`, `durationMs`, and `tokens[{text, fromMs, toMs}]` for per-word animation. Each `Caption` has `text` (with a **leading space**), `startMs`, `endMs`, `timestampMs`, `confidence`. The container needs `white-space: pre`. — [Remotion createTikTokStyleCaptions](https://www.remotion.dev/docs/captions/create-tiktok-style-captions)
- **Hardware encoding on macOS:** VideoToolbox is used for H.264/H.265 from v4.0.236 (ProRes from v4.0.228), via `hardwareAcceleration: "if-possible" | "required"` or `--hardware-acceleration`. CRF doesn't work with hardware encoders, so use `--video-bitrate`. `--video-bitrate=8M` is cited as roughly equal to software H.264 at Full HD. It is not available on Lambda or Cloud Run. — [Remotion hardware acceleration](https://www.remotion.dev/docs/hardware-acceleration)
- **Performance:** `npx remotion benchmark` measures render time across runs and concurrency values. Concurrency that is too high or too low is counterproductive. Higher resolution is slower. Embedded video and GPU-heavy effects are common bottlenecks. — [Remotion benchmark](https://remotion.dev/docs/cli/benchmark); [Remotion performance](https://remotion.dev/docs/performance)
- An anecdote from a 2019 Intel MBP: the render was slower than real time and memory limited it to `--concurrency 2`. This is stale and not M1. — [remotion-dev discussion #862](https://github.com/orgs/remotion-dev/discussions/862)

**(3) MoviePy 2.x:**
- v2 drops ImageMagick (along with PyGame, OpenCV and scipy) and focuses on Pillow. `TextClip` now **requires a font file path**. `set_*` became out-of-place `with_*`. Effects are classes applied with `with_effects()`, and `Clip.fx` is gone. `resize/crop/rotate` became `resized/cropped/rotated`. `moviepy.editor` was removed (import from `moviepy`). The migration guide has no performance notes. — [MoviePy v2 migration guide](https://zulko.github.io/moviepy/getting_started/updating_to_v2.html)
- **captacity** (MIT; 141 stars, 37 commits) adds Whisper + MoviePy captions. It exposes font path, size, colour, stroke width/colour, shadow strength/blur, current-word highlight colour, line count and padding. Its README example uses font size 130. — [captacity](https://github.com/unconv/captacity)

**(4) pycaps:**
- MIT. It is a CSS-styled animated subtitle library and CLI aimed at TikTok/Shorts/Reels. The default `CssSubtitleRenderer` uses **Playwright + Chromium**. A lighter `PictexSubtitleRenderer` needs no browser but supports only a subset of CSS, and shadows may differ. — [pycaps](https://github.com/francozanardi/pycaps)
- CSS state selectors (e.g. `.word-being-narrated`), built-in templates, pop/fade/slide animations, typewriter, emoji insertion and **sound effects**. Words can be **tagged by regex, word lists, or AI**, and tags then work as CSS/animation selectors. It accepts existing `whisper_json`, `pycaps_json`, `srt`, `vtt` transcripts, so you can skip its transcription. — [pycaps](https://github.com/francozanardi/pycaps)
- Python 3.10–3.12 tested. "Very alpha", **not on PyPI** (install with `pip install "git+https://github.com/francozanardi/pycaps.git#egg=pycaps[all]"`). 231 stars, 208 commits, no releases. — [pycaps](https://github.com/francozanardi/pycaps)

**(5) Blender / other:** not researched in depth (see Gaps).

### Inferences

**Capability matrix** (my synthesis of the findings above plus general knowledge; verify the starred cells):

| Need | ffmpeg + ASS | Remotion | MoviePy 2 (+captacity) | pycaps |
|---|---|---|---|---|
| Word pop-in | Chunk-level pop via `\t(\fscx…)`. Per-word scale reflows neighbours* | Best: per-token `spring()`/`interpolate()` with CSS transforms, no reflow | Manual per-word clips, laborious | Built-in pop/fade/slide |
| Per-keyword highlight colour | Yes (`\c&HBBGGRR&` inline) | Yes (any CSS) | Yes | Yes (tags → CSS classes) |
| Colour emoji | **Likely no** (libass lacks colour-emoji support*). Overlay PNG emoji instead | Yes (Chrome renders Apple Color Emoji on macOS*) | PNG overlay | Yes (emoji effect) |
| Stroke/shadow | `\bord`, `\shad`, `\blur` (good) | `-webkit-text-stroke` + `paint-order`, `text-shadow` | Pillow stroke_width | CSS |
| Smooth zoom | Integer-pixel scale, jitter on slow zooms (see Q4) | Sub-pixel CSS `transform: scale()` | Resize per frame (slow) | N/A (captions only) |
| Speed on M1 | Fastest (single native pass) | Slowest (headless Chrome per frame) | Slow (Python/numpy compositing) | Moderate–slow (browser renders caption states) |
| Cost | Free (GPL ffmpeg build) | Free ≤3 people, else ≥$100/mo | Free (MIT) | Free (MIT) |

**Recommended architecture:**
- **Path A (default, simplest, fastest):** Python builds an `.ass` file from word timestamps plus keyword tags. A single `ffmpeg-full` command does the zoom (scale/crop), `subtitles=` burn-in, emoji PNG overlays (`overlay=enable='between(t,a,b)'`), SFX `amix` and `loudnorm`, then encodes.
- **Path B (premium motion):** Remotion renders the **whole** composition (`<OffthreadVideo>` + captions + zoom + SFX `<Audio>`). Alternatively, render **only a transparent overlay** (ProRes 4444 / WebM with alpha) and composite it in ffmpeg. The overlay variant avoids Chrome decoding 1080x1920 video every frame and should be much faster (unverified).
- **pycaps** is worth trying for CSS templates and AI tagging. Pin a git commit, since it's alpha. Its Playwright dependency adds about 150 MB+ of Chromium.

**ASS sketch** (untested; written by hand, no library needed. pysubs2 can also write this):
```
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Montserrat Black,100,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,9,5,5,90,130,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
; one event per "active word" state; pop only on the first state of each chunk
Dialogue: 0,0:00:01.20,0:00:01.48,Cap,,0,0,0,,{\pos(540,1150)\fscx80\fscy80\t(0,80,\fscx108\fscy108)\t(80,150,\fscx100\fscy100)}{\c&H00E6FF&}THIS{\c&HFFFFFF&} IS INSANE
Dialogue: 0,0:00:01.48,0:00:01.70,Cap,,0,0,0,,{\pos(540,1150)}THIS {\c&H00E6FF&}IS{\c&HFFFFFF&} INSANE
Dialogue: 0,0:00:01.70,0:00:02.30,Cap,,0,0,0,,{\pos(540,1150)}THIS IS {\c&H66FF00&\fscx112\fscy112}INSANE
```
- Style-section colours are `&HAABBGGRR`, where the leading byte is alpha (00 = opaque). Inline `\c` is `&HBBGGRR&`, so #FFE600 yellow becomes `&H00E6FF&`.
- Burn in with `-vf "subtitles=caps.ass:fontsdir=./fonts"`. Put static TTFs (e.g. `Montserrat-Black.ttf`) in `./fonts`. The `Fontname` must match the font's family/full name. Verify with `fc-scan`, because variable-font weight matching in libass can be unreliable.
- To avoid reflow jitter, **pop the whole chunk** on entry and only **recolour** the active word. Scaling a single word inline pushes its neighbours sideways.

**Remotion sketch** (untested):
```tsx
const {pages} = createTikTokStyleCaptions({captions, combineTokensWithinMilliseconds: 600});
// per page: <Sequence from={msToFrame(page.startMs)} durationInFrames={...}>
// per token: const active = t >= tok.fromMs && t < tok.toMs;
// const s = spring({frame: frame - msToFrame(tok.fromMs), fps, config:{damping:12, stiffness:200}});
// <span style={{display:'inline-block', transform:`scale(${active ? 0.9+0.2*s : 1})`, color: isKeyword ? '#FFE600' : '#fff',
//   WebkitTextStroke:'10px black', paintOrder:'stroke fill', textShadow:'0 6px 12px rgba(0,0,0,.6)'}}>
```
`display:inline-block` + `transform` scales without reflow, which is the main advantage over ASS.

### Gaps
- Not verified this session: whether **libass renders colour emoji** (COLR/sbix). From training knowledge it historically does not. Test with `ffmpeg-full` before relying on it, and plan for PNG overlays (Twemoji CC-BY 4.0 / Noto Emoji OFL; licences not verified here).
- Whether inline `\t` mid-line animates only the following text in libass (vs the whole line) was not confirmed. The Aegisub docs suggest per-word motion "generally requires splitting into separate lines".
- pysubs2's current API/version was not fetched (searches didn't surface it).
- Blender (VSE/text strips), Motion Canvas/Revideo, and GPU compositors were not researched. No sources were found comparing them for captioning.
- pycaps last-commit date and real-world render speed are unknown.

---

## 2. Current (2025–2026) short-form caption style conventions

### Takeaway
The dominant "podcast clip" look is still **heavy sans-serif, ALL CAPS, 1–3 words on screen (≤ ~15 characters/line, max 2 lines), white fill with thick black stroke and/or drop shadow, the active or keyword word recoloured (yellow/green), and a quick pop/scale-in**, placed in the **centre to lower-middle** of the frame clear of the Reels UI. Use **Montserrat Black/ExtraBold or Anton** (both OFL, free for commercial use). Avoid Komika Axis (free for personal use only) and treat The Bold Font's free version as uppercase-only.

### Cited Findings
- Vendor blogs broadly agree that Hormozi-style captions use a bold sans-serif, uppercase, word-by-word timing, and a colour highlight on the active word, often yellow or green. They disagree on which font Hormozi actually uses (Montserrat ExtraBold/Black vs The Bold Font). No primary confirmation was found. — [ZapCap](https://zapcap.ai/blog/best-font-for-youtube-shorts-in-year); [SendShort Hormozi guide](https://sendshort.ai/guides/hormozi-captions/); [Blitzcut 2026 fonts](https://blitzcutai.com/blog/best-caption-fonts-youtube-shorts-2026); [Kapwing template](https://www.kapwing.com/explore/hormozi-style-captions-template)
- Submagic (page references 2025, © 2026): the **"old Hormozi style"** is TheBoldFont, uppercase, with shadow and no stroke. The **"new Hormozi style"** is **Anton**, uppercase, with a slight shadow, a **yellow stroke**, and a **pop-in moving bottom→top**. Their Premiere recipe uses Montserrat, a **max 15 characters per caption**, min 2 s, double-line. Their CapCut recipe uses **4–6 words max across 2 lines** and a heavy shadow (opacity 100%, blur 70%, distance 14%). Emphasis comes from splitting at the keyword and enlarging it, plus animated emojis. No hex colours or positions were given. — [Submagic: How to make Alex Hormozi captions](https://www.submagic.co/blog/how-to-make-alex-hormozi-captions)
- Komika Axis is associated with MrBeast/high-energy content. Bangers and Anton are common alternatives. — [ZapCap](https://zapcap.ai/blog/best-font-for-youtube-shorts-in-year) / search summary of vendor blogs
- **Font licences:**
  - **Montserrat** is licensed "OFL", designed by Ulanovsky, Matas, del Peral and Le Bailly. It is a variable font with weight axis 100–900, so Black (900) is included. — [google/fonts Montserrat METADATA.pb](https://github.com/google/fonts/blob/main/ofl/montserrat/METADATA.pb)
  - **Komika Axis** (Vigilante Typeface Corporation) is listed as "**Free for personal use**", with no commercial terms stated. — [DaFont Komika Axis](https://www.dafont.com/komika-axis.font)
  - **The Bold Font** (Sven Pels) is listed as "**100% Free**". The free version has **121 glyphs (no lowercase)**, and the PRO version adds lowercase. Last updated 2 Jan 2025. — [DaFont The Bold Font](https://www.dafont.com/the-bold-font.font)
- **Reels safe zones** (no official organic spec exists):
  - Ad-oriented checkers give **top ≈270 px (14%)**, **bottom ≈670 px (35%)** and **sides ≈65 px (6%)** on 1080x1920. Revid's safe area is 895×980 px starting 270 px from the top and 65 px from the left. — [Revid Reels safe zone](https://www.revid.ai/instagram-reels-safe-zone); [AdManage](https://admanage.ai/instagram-reels-safe-zone) (advises verifying in Meta Ads Manager)
  - FirstPier lists 108 px top, 320 px bottom, 60 px left and **120 px right** (the right-side action button column). — [FirstPier](https://www.firstpier.com/resources/instagram-ad-safe-zones)
  - Adkit gives a 450 px (23.4%) bottom danger zone. — [Adkit](https://adkit.so/tools/safe-zones/instagram)
  - No platform publishes margins for organic Reels. The layout is similar to ads but not identical. — [bundle.social](https://bundle.social/tools/safe-zone-checker); [visu.network](https://visu.network/tools/safe-zone-checker/)

### Inferences
**Concrete spec to start from** (my recommendation, synthesised from the above; tune by eye):
- **Canvas/safe box:** keep all text inside x ∈ [90, 960], y ∈ [270, 1250] for ads-grade safety. For organic, y can go to about 1450. The right margin should be ≥120 px for text that sits low in the frame.
- **Caption anchor:** centre-aligned (`\an5`), with the block centre at **y ≈ 1100–1200** (57–62% of the height). In split-screen two-speaker podcast layouts, put it on the seam at about y = 960.
- **Chunking:** 1–3 words per chunk (≤ 15–16 characters/line, max 2 lines). Break on punctuation and pauses > 250–300 ms, and never let a chunk span a sentence end. Use 1-word "slam" chunks for the hook and for emphasis words. Remotion equivalent: `combineTokensWithinMilliseconds` about 500–800 with `breakOnSilenceAfterMilliseconds` about 300.
- **Type:** Montserrat Black (900) or ExtraBold (800), or Anton, in ALL CAPS. Cap height about 70–90 px at 1080 width (ASS `Fontsize` about 90–110 for Montserrat; Anton is condensed, so it can go about 120). Tracking 0 to +1.
- **Stroke/shadow:** black outline 8–10 px (`\bord8`–`\bord10` with `ScaledBorderAndShadow: yes`) plus a soft drop shadow (offset 4–6 px, ~40–60% black). Avoid large `\blur` for speed.
- **Colours:** white base. Active word or keyword in yellow `#FFE600`, with green `#3DFF6E` as a second emphasis tier. Optionally use red `#FF3B30` for negative or shock words. Use at most 1–2 accent colours per video for brand consistency.
- **Case:** ALL CAPS is still dominant for the "viral clip" aesthetic. Sentence case reads more "premium/educational". Make it a template setting.
- **Animation:** chunk pop-in from 80%→108%→100% over about 120–160 ms (`\t` with accel <1 gives an ease-out), or slide up 20–40 px plus fade over about 100 ms. Avoid fades longer than about 150 ms, since they lag fast speech.
- **Font licence choice:** Montserrat and Anton are safe for monetised accounts. The Bold Font's "100% Free" DaFont tag is likely fine, but it is uppercase only. Komika Axis needs a commercial licence check.

### Gaps
- No authoritative 2025–2026 data (Meta, or creator analytics with methodology) on which caption style performs best. All style claims come from caption-tool vendors with a commercial interest.
- Proxima Nova licensing and price were not verified (from training knowledge it's a commercial Mark Simonson font, also available via Adobe Fonts). Anton's and Bangers' OFL status was inferred from their presence in Google Fonts' `ofl/` tree, not fetched.
- Exact pixel positions used by top podcast clip pages were not measured. Sampling a few reference Reels would settle this.

---

## 3. Choosing highlight keywords automatically

### Takeaway
No commercial tool documents its selection logic. Build a **hybrid**: deterministic heuristics (numbers, money, percentages, named entities, superlatives/negations, emotion lexicon) produce candidates, and **one cheap LLM call per clip** returns JSON emphasis tags under hard budgets (≤1 keyword per chunk, ~15–25% of chunks). Then map tags to colours, sizes, SFX and emoji. pycaps already implements the "tags as selectors" pattern.

### Cited Findings
- pycaps tags words or phrases by **regex, word lists, or AI** ("optional AI-powered features that require contextual understanding of your script"). Tags then drive CSS, animations and effects. — [pycaps](https://github.com/francozanardi/pycaps)
- OpusClip's help docs only say that "AI Emoji" adds "relevant" emojis (toggle in AI Enhance). The page doesn't describe keyword-highlight logic. — [OpusClip help: AI emojis](https://help.opus.pro/docs/article/ai-emojis-keywords)
- Submagic's highlighting/emoji logic is described only by third-party reviews ("AI analyzes speech content"). No official rules were found. — search summary incl. [AlternativeTo Submagic](https://alternativeto.net/software/submagic--ai-captions/about)
- Manual Hormozi-style workflows recolour keywords and enlarge an emphasis word by splitting the caption at it. — [Submagic guide](https://www.submagic.co/blog/how-to-make-alex-hormozi-captions)

### Inferences
- **Heuristic layer** (cheap and deterministic):
  - Regex for digits, `$`, `%`, `x`, `k/m/b`, number words ("million", "ten").
  - spaCy `en_core_web_sm` NER (PERSON, ORG, GPE, MONEY, PERCENT, CARDINAL).
  - Superlatives and intensifiers ("never", "always", "best", "worst", "only", "insane").
  - Negation and contrast pivots ("but", "actually", "nobody").
  - An emotion lexicon (e.g. NRC) for strong affect words.
  - Stopwords are never highlighted.
- **LLM layer prompt shape:** input is the transcript with word indices. Output is `[{"i": 42, "tier": "primary|secondary|negative", "emoji": "💰"|null}]`. Constraints: at most 1 per chunk, no adjacent chunks both highlighted unless it's a list, prefer the payoff word of a sentence, and include 1–2 words from the hook line. Validate indices server-side.
- **Mapping:**
  - primary → yellow + 110–115% scale + optional "pop" SFX
  - secondary → green
  - negative → red
  - emoji → PNG above the chunk, max one every ~4–6 s
- Separate "active word" karaoke colour from "keyword" colour, or skip karaoke colouring entirely and colour only keywords. Mixing both makes keywords hard to distinguish.

### Gaps
- No published evaluation compares LLM-picked vs heuristic emphasis on retention. No source documents how OpusClip/Submagic pick keywords.

---

## 4. Punch-in zooms

### Takeaway
ffmpeg `zoompan` is known-jittery on moving zooms (open trac #4298, a sub-pixel issue), and up-scaling first only partially helps. The most robust ffmpeg approach is **hard-cut punch-ins**: static scale per segment, typically 1.0 ↔ 1.12–1.25 at sentence or idea boundaries. These are jitter-free and look like a second camera angle. For animated zooms, use **short eased zooms (≤250–400 ms)** via `scale` with `eval=frame` plus a fixed `crop`. For slow push-ins, use a **sub-pixel renderer** (Remotion CSS `transform: scale`, or OpenCV `warpAffine` piped to ffmpeg).

### Cited Findings
- FFmpeg trac **#4298 "zoompan filter creates shaky image"** was still **open** in Oct 2024–Apr 2025 mail. A developer attributes it to **sub-pixel rendering**, other swscale algorithms didn't help, and a contributor's "subpixel_zoompan" patch is unconfirmed as merged. Upscale→zoom→downscale left jitter "still noticeable", and a `geq`-based zoom works but is "significantly slower". — [ffmpeg-trac #4298 (Apr 2025)](https://ffmpeg.org/pipermail/ffmpeg-trac/2025-April/073180.html); [ffmpeg-trac #4298 (Oct 2024)](https://ffmpeg.org/pipermail/ffmpeg-trac/2024-October/071414.html)
- Common zoompan advice is to upscale massively first (e.g. `scale=8000:-1`), use a small per-frame zoom step (0.001), and force a constant `fps`. — [Creatomate](https://creatomate.com/blog/how-to-zoom-images-and-videos-using-ffmpeg); [Bannerbear](https://www.bannerbear.com/blog/how-to-do-a-ken-burns-style-effect-with-ffmpeg)
- The `scale` filter accepts `t` and `n` only when `eval=frame`. Init-mode evaluation rejects them. — [FFmpeg vf_scale.c](https://github.com/FFmpeg/FFmpeg/blob/fa469545ba0782a9245474ecca873aa8984f506e/libavfilter/vf_scale.c)
- A Video.SE answer ramps size over time with `scale=w='if(gte(t,…)…)':h=-1:eval=frame`, with optional exponential ease. — [Video.SE: change scale over time](https://backiee.wasmer.app/http_avp_stackexchange_com/questions/12125/is-it-possible-in-ffmpeg-to-change-scale-over-time)
- `crop`: temporal variables (`t`, `n`, `pos`) apply only to **x/y**. w/h can only vary via `sendcmd`. zoompan lacks a usable fps value in expressions. (2020 thread, stale but no contrary evidence found.) — [ffmpeg-user 2020-04](https://ffmpeg.org/pipermail/ffmpeg-user/2020-April/048487.html)
- Reddit users report zoompan "stutter" and image-shift problems with scale+crop holds (2025). — [r/ffmpeg zoom issue](https://pol1.lr.ggtyler.dev/r/ffmpeg/comments/1ku9lio/issue_with_zoom_effect_in_ffmpeg_for_dynamic); [r/ffmpeg shift](https://axebps-redlib.hf.space/r/ffmpeg/comments/1l85hu4/how_to_prevent_image_shift_pixel_misalignment)

### Inferences
**Recipes** (untested sketches; validate on `ffmpeg-full` 9.x):

1. **Hard-cut punch-ins (recommended default, zero jitter).** Split at cut points and apply a static zoom per segment:
   ```
   [0:v]trim=3.20:7.90,setpts=PTS-STARTPTS,scale=1296:2304:flags=lanczos,crop=1080:1920[z1]   # 1.20x
   ...concat=n=K:v=1:a=0
   ```
   Trimming audio separately risks A/V drift, so it's simpler to keep audio untouched and only switch video. The single-chain alternative is `scale=w='if(between(t,3.2,7.9),1296,1080)':h=-2:eval=frame:flags=lanczos,crop=1080:1920` (crop w/h fixed, x/y default to centre). If libavfilter rejects mid-stream size changes, fall back to the per-segment trim/concat version.
2. **Fast eased zoom (150–300 ms ramp).** Z(t) = 1 + A·smoothstep(clip((t−T0)/D, 0, 1)), where smoothstep(s) = s²(3−2s):
   `scale=w='2*trunc(1080*(1+0.15*(st(0,clip((t-3.2)/0.25,0,1)))*ld(0)*ld(0)*(3-2*ld(0))/2)':h=-2:eval=frame:flags=bicubic,crop=1080:1920`. Generate this expression in Python for many zooms, or use `sendcmd`. The integer-pixel stepping is invisible when the ramp is fast.
3. **Slow push-in (e.g. 1.00→1.08 over 4 s):** don't use ffmpeg integer scaling. Options:
   - Remotion: `const s = interpolate(frame,[f0,f1],[1,1.08],{easing:Easing.bezier(0.33,0,0.2,1),extrapolateLeft:'clamp',extrapolateRight:'clamp'})` with `style={{transform:`scale(${s})`}}`, which is sub-pixel.
   - Python: decode rawvideo, `cv2.warpAffine` with a float scale matrix (INTER_CUBIC), pipe to `ffmpeg -f rawvideo -pix_fmt bgr24 -s 1080x1920 -r 30 -i -`.
   - ffmpeg-full includes **libplacebo**, whose crop parameters may accept per-frame expressions with sub-pixel sampling. On macOS it needs Vulkan/MoltenVK. Unverified.

**Placement rules** (heuristics, no source):
- Zoom in on primary-emphasis words, at the start of the hook, on punchlines/payoffs, and on a change of idea.
- Alternate framing every ~3–6 s so there is never more than about 6 s without a visual change.
- Never zoom across a speaker switch in split-screen.
- Return to 1.0 at sentence ends or on a hard cut.

**Amounts:**
- 1.10–1.15 for subtle push-ins.
- 1.20–1.30 for emphasis punches. The upscale cost at 1080 source is real: 1.25x samples only 864 px of width.
- **Best quality tip:** if the reframing stage has the 16:9 4K/1080p original, apply zoom there before the 9:16 crop. Cropping a smaller window from a higher-res source is lossless.

**Easing:**
- Punch: ease-out cubic over 4–8 frames at 30 fps, optionally with a 2–3% overshoot.
- Push: ease-in-out over the whole segment.
- Pair zoom-ins with a whoosh SFX (Q5).

**Order of operations:** zoom → captions (so text doesn't zoom) → overlays/emoji/hook → audio mix → encode.

### Gaps
- No confirmed merged fix for zoompan sub-pixel jitter as of the latest mail found (Apr 2025). Check trac #4298 for 2026 status.
- Not verified whether `scale` with `eval=frame` and changing output size followed by `crop` works cleanly in ffmpeg 9.x (frame-size renegotiation). Test first.
- No source quantifies "typical" zoom amounts or frequency used by top clip pages. The values above are practitioner heuristics.

---

## 5. Sound effects (sources, licences, mixing, loudness)

### Takeaway
Use **Mixkit and Pixabay** (commercial use, no attribution, but no standalone redistribution) and **Freesound filtered to CC0** for whooshes, pops and risers. Mix SFX well under dialogue, and finish with a **two-pass `loudnorm` to about −14 LUFS integrated / −1 dBTP**. That target is a social-media convention, not a published Instagram spec.

### Cited Findings
- **Mixkit's** Free License allows commercial projects (YouTube, social media marketing, online ads) with **no attribution**. Licences differ by item type, so check that you're reading the SFX terms and check each file's notice. — [Mixkit official info](https://mixkit.co/llm-info/); [CloudCover guide](https://cloudcovermusic.com/music-licensing-guide/best-sites-to-download-sound-effects)
- **Pixabay** Content License: commercial use, no attribution. It **prohibits redistributing or selling SFX as standalone files**. Pre-2019 uploads are CC0. — search summary of [SFX Engine](https://sfxengine.com/blog/free-sound-effects-download) / [Swarmify](https://swarmify.com/blog/free-sound-effects-websites/)
- **Freesound** licences are per sound: **CC0** (no credit), **CC-BY** (attribution required), and **CC-BY-NC (not for commercial use)**. Filter to CC0 for commercial work. — [Soundly: Freesound FAQ](https://getsoundly.com/faq/how-can-i-use-the-freesound-library); [CloudCover guide](https://cloudcovermusic.com/music-licensing-guide/best-sites-to-download-sound-effects)
- pycaps ships a **sound-effects** effect tied to its caption tags. — [pycaps](https://github.com/francozanardi/pycaps)
- **Loudness:**
  - Single-pass `loudnorm` defaults to dynamic mode, which compresses audio. Linear normalization needs **two passes**: measure, then feed `measured_I/LRA/TP/thresh` with `linear=true`. — [video-use loudness docs](https://instagit.com/browser-use/video-use/social-media-loudness-normalization-targets/)
  - The video-use project hard-codes **−14 LUFS, −1 dBTP, LRA 11** and claims they match Instagram/YouTube/TikTok/X/LinkedIn. That's a **third-party claim, not a Meta spec**. — [video-use loudness docs](https://instagit.com/browser-use/video-use/social-media-loudness-normalization-targets/)
  - `ffmpeg-normalize` automates the two-pass process and can lower the target to avoid true-peak violations. — [ffmpeg-normalize docs](https://docsearch.algolia.com/mcp/docs/repo/slhck/ffmpeg-normalize)

### Inferences
**SFX design rules** (practitioner heuristics):
- **Whoosh** on every zoom-in or hard cut, starting about 80–150 ms before the visual change so its peak lands on the cut.
- **Pop/click** only on primary keywords or emoji appearances, at most one every ~2–4 s. A pop on every word is fatiguing.
- **Riser** (1–2 s) into the payoff line.
- **Impact/boom** on the hook title or the biggest stat.
- Rotate 3–5 variants of each SFX type, chosen randomly, so the sound doesn't repeat audibly.

**Levels:**
- SFX peaks about 10–15 dB below dialogue peaks. Place them in word gaps rather than ducking.
- If you add a music bed, keep it about 18–25 dB under dialogue and use `sidechaincompress` keyed on the voice.

**ffmpeg mix sketch** (untested):
```
-filter_complex "[1:a]adelay=3100:all=1,volume=-14dB[w];[2:a]adelay=1200:all=1,volume=-20dB[p];
[0:a][w][p]amix=inputs=3:duration=first:normalize=0[mix];
[mix]loudnorm=I=-14:TP=-1.0:LRA=11:measured_I=…:measured_TP=…:measured_LRA=…:measured_thresh=…:offset=…:linear=true:print_format=summary,aresample=48000[a]"
```
- Pass 1: `-af loudnorm=I=-14:TP=-1:LRA=11:print_format=json -f null -`.
- `amix` normalizes (attenuates) its inputs by default, so set `normalize=0`.
- `loudnorm` upsamples internally to 192 kHz, so resample back to 48 kHz.
- Alternatively, `uv add ffmpeg-normalize` and run it on the mixed track.

**Epidemic Sound** is a paid subscription. Use it if you want consistent quality and safe-harbour licensing for monetised channels. Pricing and terms were not verified.

### Gaps
- No official Instagram/Meta loudness target was found. Instagram's playback normalization behaviour is undocumented in the sources found.
- Pixabay's exact licence text and Epidemic Sound plan pricing/terms were not fetched directly. Re-verify before commercial use.
- No sourced dB guidelines for SFX vs dialogue in short-form. The values above are heuristics.

---

## 6. Optional overlays: hook title, B-roll, emoji, progress bar

### Takeaway
Clip-page best practice (vendor guidance) is to **show a text hook on the very first frame for about 2–3 s** that states the payoff or curiosity gap, and to start the clip at the insight rather than at conversational setup. Evidence quality is weak, and one test suggests context-rich openings can win on completion.

### Cited Findings
- Guides recommend an opening-frame text overlay for the first ~2 s (e.g. a "most people don't know this" line), or a text overlay with the main takeaway for 0–3 s. They recommend starting at the climax or insight, and re-cutting the first 3 s of underperforming clips. — [Captions.ai: hook a repurposed clip](https://captions.ai/help/guides/creators/hook-repurposed-clip); [StreamLadder](https://www.streamladder.com/blog/instantly-hook-viewers-first-3-seconds); [Blitzcut 2026](https://blitzcutai.com/blog/how-to-repurpose-podcast-short-form); [PodcastAI](https://podcastai.com/blog/how-to-create-viral-podcast-clips-for-tiktok-instagram)
- Counterpoint: one test found a 3 s hook won on early view duration, but a version with 6–10 s of context won on completion rate and 7-day views. — [AutoClip: Why 3-second hooks are overrated](https://autoclip.dev/blog/why-3-second-hooks-are-overrated)
- Suggested clip lengths are 20–60 s, and 30–90 s for Reels. — search summary of [Blitzcut](https://blitzcutai.com/blog/how-to-repurpose-podcast-short-form) / podcast-clip guides
- OpusClip and Submagic auto-insert emojis ("relevant", logic undocumented). Submagic's manual Hormozi recipe uses animated emojis. — [OpusClip help](https://help.opus.pro/docs/article/ai-emojis-keywords); [Submagic guide](https://www.submagic.co/blog/how-to-make-alex-hormozi-captions)

### Inferences
**Hook title spec:**
- **Frame-0 visible** (no fade-in, so the first frame works as a scroll-stopper and thumbnail).
- **Position:** top third, y ≈ 300–520 (below the ~270 px top UI zone).
- **Size and layout:** 1–2 lines, ≤ ~32 characters per line, 60–80 px bold, set either as white text with a stroke or as black text on a white/yellow rounded box (padding 20–28 px, radius 16–24 px).
- **Duration:** 2.5–4 s with a 120–200 ms scale/slide-in, or persistent for the whole clip as a "title bar" style.
- **Content:** LLM-generated from the clip transcript (≤8 words, curiosity gap, no clickbait the clip doesn't pay off).

**Progress bar:** 8–12 px bar at the very top (y ≈ 0–12) in the accent colour. The bottom is covered by the Reels UI. Implement in ffmpeg with `drawbox` and a `w='iw*t/DUR'` expression (needs a build with expression-enabled drawbox, which is standard), or with a Remotion `<div>`.

**Emoji:**
- 140–200 px PNG from Twemoji/Noto, positioned above the caption block.
- Pop scale 0→1.15→1 over ~150 ms.
- Show for 0.8–1.5 s, at most one every 4–6 s.

**B-roll:** cutaways of 1–3 s on nouns (stock via Pexels/Pixabay APIs) are optional and add search/licensing complexity. Defer to v2.

### Gaps
- No primary data (Meta) on hook overlay effect. All guidance is vendor/creator opinion.
- Twemoji (CC-BY 4.0, attribution) and Noto Emoji (OFL) licences were not verified in this session.

---

## 7. Instagram Reels export settings (2026) and h264_videotoolbox vs libx264

### Takeaway
Export **1080x1920, 30 fps, H.264 High, yuv420p, MP4 with faststart, AAC-LC stereo 48 kHz at 192–320 kbps, about 10–16 Mbps video**. Instagram re-encodes everything, so upload a clean high-bitrate master. On M1, **libx264 (`-preset slow -crf 18`) gives better quality per bit**. `h264_videotoolbox` is several times faster but needs higher bitrate for parity. For a 60 s clip either is fast enough, so prefer libx264 for the final render and VideoToolbox for previews.

### Cited Findings
- **Consistent across 2026 third-party spec sheets:**
  - **H.264 + AAC stereo**, MP4 (MOV works), **1080×1920 9:16**.
  - **30 fps** recommended (24/60 accepted). 60 fps doubles size without visible gain for most Reels.
  - AAC ≥128 kbps, 48 kHz.
  - **Conflicting values:** bitrate recommendations range from ≥3.5 Mbps to 10–15 Mbps VBR, with one listing a 25 Mbps max. Max file size is given as 1 GB vs 4 GB.
  - These are not Meta documents. — [SocialPilot 2026](https://www.socialpilot.co/instagram-marketing/instagram-video-size); [Argil 2026 spec sheet](https://argil.ai/blog/instagram-reel-size-e350f); [Postfast Reels specs](https://postfa.st/sizes/instagram/reels); [Mallary dev guide 2026](https://www.mallary.ai/blog/instagram-reel-resolution)
- **Length:**
  - Widely reported as **3 min (180 s) in-app**, extended from 90 s in 2025. — [Buffer](https://buffer.com/library/instagram-reels-length); [Metricool](https://metricool.com/instagram-reels-length)
  - Some 2026 guides claim **20 min** via staged rollout. This is unconfirmed by Meta and varies by account. — [Inro](https://www.inro.social/blog/instagram-reels-can-now-be-20-minutes-long-new-time-limit-explained-2025)
  - Irrelevant for 45–60 s clips.
- **VideoToolbox vs libx264:**
  - An ffmpeg-user report measured **2.58x** faster processing with h264_videotoolbox on M1. (Oct 2021, stale but directionally valid.) — [ffmpeg-user 2021-10](https://ffmpeg.org/pipermail/ffmpeg-user/2021-October/053727.html)
  - An Apple forum user found M1 hardware encoding gives good performance "at a significant cost of bitrate or quality". (2021, and their comparison partly used NVENC.) — [Apple Developer Forums](https://developer.apple.com/forums/thread/678210)
  - A third-party app's table lists h264_videotoolbox at about **1.15x the file size of libx264 medium at equal quality**, with libx264 being 8x+ slower. Methodology is unverified. — [Frame docs (mintlify)](https://www.mintlify.com/66HEX/frame/guides/hardware-acceleration)
  - `-crf` applies only to software encoders. VideoToolbox supports `-b:v`, or constant quality `-q:v` (0–100) on **Apple Silicon only, ffmpeg ≥4.4**. A common start is `-q:v 50`. — [heguro scrapbox (JP)](https://scrapbox.io/heguro/ffmpeg%E3%81%A7videotoolbox(macOS)%E3%82%92%E4%BD%BF%E3%81%86); [CodeTV](https://codetv.dev/blog/hardware-acceleration-ffmpeg-apple-silicon)
  - Remotion's docs equate `--video-bitrate=8M` hardware H.264 with software encoding at Full HD. — [Remotion hardware acceleration](https://www.remotion.dev/docs/hardware-acceleration)

### Inferences
**Final master (libx264):**
```
-c:v libx264 -preset slow -crf 18 -profile:v high -level 4.2 -pix_fmt yuv420p -r 30 \
-maxrate 16M -bufsize 32M -g 60 -movflags +faststart \
-c:a aac -b:a 256k -ar 48000 -ac 2
```
1080x1920 is the same pixel count as 1920x1080, so Level 4.2 is fine at 30 fps.

**Fast/preview (VideoToolbox):**
```
-c:v h264_videotoolbox -b:v 14M -maxrate 18M -profile:v high -pix_fmt yuv420p -allow_sw 1 -realtime 0
```
Or `-q:v 60–65`. Give VideoToolbox about 1.2–1.5x the libx264 bitrate for similar quality.

**Other settings:**
- Keep the source frame rate if it's 30. If it's 29.97 or 25, either keep it or convert with `fps=30` before captions so subtitle timing is unaffected.
- Avoid 60 fps unless the source is 60.
- Don't upload HEVC/10-bit/HDR from iPhone sources without converting to SDR 8-bit (`zscale`/`tonemap` are in ffmpeg-full). Instagram's HDR handling is inconsistent, though this isn't verified here.

### Gaps
- No official Meta Reels upload spec page was retrieved. All specs are third-party.
- No 2025–2026 controlled VMAF comparison of h264_videotoolbox vs libx264 on M1 was found. Running `ffmpeg -lavfi libvmaf` on your own footage is cheap (libvmaf is in both Homebrew formulas).

---

## 8. Render-time estimates on M1 for a 45–60 s clip

### Takeaway
No published M1 benchmarks exist for any of these exact workloads. Engineering estimates for a 60 s / 1800-frame 1080x1920 clip: **ffmpeg+ASS ≈ 20–60 s (libx264 slow) or ≈ 10–25 s (VideoToolbox)**, **Remotion full composition ≈ 1.5–5 min**, **Remotion overlay-only + ffmpeg composite ≈ 1–2.5 min**, **pycaps ≈ 1–4 min**, **MoviePy 2 ≈ 3–10 min**. Measure before committing.

### Cited Findings
- Remotion provides `npx remotion benchmark` for exactly this, and warns that concurrency tuning and embedded video are the main factors. — [Remotion benchmark](https://remotion.dev/docs/cli/benchmark); [Remotion performance](https://remotion.dev/docs/performance)
- The only Mac anecdote found (Intel 2019 MBP) rendered slower than real time and was limited to concurrency 2 by memory. — [remotion-dev discussion #862](https://github.com/orgs/remotion-dev/discussions/862)
- Hardware H.264 encoding is supported in Remotion on macOS (v4.0.236+), which removes the encode bottleneck. — [Remotion hardware acceleration](https://www.remotion.dev/docs/hardware-acceleration)
- VideoToolbox measured about 2.58x faster than software on M1 (2021). — [ffmpeg-user 2021-10](https://ffmpeg.org/pipermail/ffmpeg-user/2021-October/053727.html)
- libass `\blur` at high values is CPU-intensive. — [Aegisub ASS tags](https://aegisub.org/docs/latest/ass_tags/)
- pycaps' demo is advertised as best for clips under 60 s on CPU. — [pycaps](https://github.com/francozanardi/pycaps)

### Inferences
All figures below are **estimates, not measurements**, reasoning from M1 8-core/16 GB characteristics:
- **ffmpeg + ASS + scale/crop + overlays:** decode, filter and encode in one native pass. libass on 1–3-word captions costs about 1–3 ms/frame. libx264 `slow` at 1080x1920 on M1 is roughly 30–90 fps, so 1800 frames takes about 20–60 s. VideoToolbox is roughly 100–200+ fps, so about 10–25 s total. Lanczos scaling for zoom segments adds a little.
- **Remotion full composition (OffthreadVideo + captions + CSS zoom):** headless Chrome screenshot per frame with concurrency about 4–6 on 8 cores/16 GB. Roughly 10–20 fps, so about 1.5–3 min, and up to about 5 min with heavy shadows/blur or concurrency limited by RAM.
- **Remotion overlay-only** (transparent ProRes 4444/WebM, no video decode in Chrome) then ffmpeg overlay: faster Chrome frames, but alpha encoding is heavy. Roughly 1–2.5 min total.
- **pycaps (Playwright):** renders each caption state to an image, then composites. Roughly 1–4 min. Use `PictexSubtitleRenderer` to drop the browser.
- **MoviePy 2:** per-frame numpy compositing of many TextClips at 1080x1920. Typically single-digit fps, so about 3–10 min.
- **Batching:** run 2–3 ffmpeg jobs in parallel on M1, or a single Remotion job (it already saturates cores). 16 GB RAM is the practical limit for Remotion concurrency.
- **Validation commands:**
  - `time /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg -benchmark …`
  - `npx remotion benchmark src/index.ts Clip --runs=3 --concurrencies=2,4,6`

### Gaps
- No published or measured M1 render times were found for Remotion, pycaps, MoviePy 2 or ffmpeg+libass at 1080x1920. ffmpeg isn't installed on the target Mac yet, so no local benchmark was run. These should be the first spike tasks.
