# Auto-Reframe 16:9 Podcast Video to 9:16 with Face / Active-Speaker Tracking (Local, Apple Silicon M1, Python)

Research date: 2026-11-07. Primary sources were package indexes (PyPI JSON), official docs, and the source code of open-source clippers that are being actively developed in 2026 (artbyjazi/autoclip, fralapo/clippyme, Rembr4nt/ai-clipper, KazKozDev/auto-vertical-reframe, nmbrthirteen/podcli). These repos give concrete, already-tuned parameter values. Older info (before 2025) is marked **[STALE]**.

---

## 1. Shot / scene-cut detection (PySceneDetect, TransNetV2, ffmpeg scene filter)

### Takeaway
For podcast footage, which is mostly hard cuts between multicam angles with almost no fades or fast motion, PySceneDetect's `ContentDetector` at its default threshold of 27 (or `AdaptiveDetector` at 3.0) is the practical choice. Merge shots shorter than about 0.8 s and always re-decide framing at every cut. TransNetV2 is more accurate in general, but on M1 its MPS path is numerically unreliable, so it has to run on CPU. That makes it overkill for podcasts. ffmpeg `scdet` is a fast prefilter option.

### Cited Findings
- PySceneDetect docs (v0.7.1) list these detector defaults:
  - `ContentDetector(threshold=27.0, min_scene_len=15, weights=(hue 1, sat 1, lum 1, edges 0), luma_only=False)`. It detects "fast cuts using changes in colour and intensity between frames" in HSV.
  - `AdaptiveDetector(adaptive_threshold=3.0, min_scene_len=15, window_width=2, min_content_val=15.0)` uses a rolling average and is meant for cases where a fixed threshold gives false positives, such as fast camera motion. It is a two-pass detector built on ContentDetector scores.
  - `HistogramDetector(threshold=0.05, bins=256)` works on luma only. `HashDetector(threshold=0.395, size=16, lowpass=2)` uses perceptual hashing. `ThresholdDetector(threshold=12)` is for fades.
  - Source: [PySceneDetect detector docs](https://www.scenedetect.com/docs/latest/api/detectors.html)
- The latest PySceneDetect on PyPI is `scenedetect` 0.7.2 (uploaded 2026-10-12) and requires Python >=3.10. — [PyPI scenedetect](https://pypi.org/pypi/scenedetect/json)
- autoclip uses `ContentDetector` threshold 27.0. Its code comment says: "27 is the library default and holds up well on talking-head and podcast footage; going lower starts firing on lighting changes and gesture blur." It merges shots shorter than `MIN_SHOT_S = 0.8` into the nearest neighbour because "re-framing across one looks frantic." — [autoclip scenes.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/scenes.py)
- autoclip's design rule: "Crop paths never interpolate across a cut. Shots are detected first and framed independently. Panning through an edit is the most obvious sign of an auto-reframed video." — [autoclip README](https://github.com/artbyjazi/autoclip)
- KazKozDev/auto-vertical-reframe runs PySceneDetect with `--scene-threshold` defaulting to `3.0`, which matches the AdaptiveDetector scale. Its pipeline is PySceneDetect → YOLOv11-seg + ByteTrack → MediaPipe face/pose + saliency → smoothed camera path → ffmpeg. — [auto-vertical-reframe README](https://github.com/KazKozDev/auto-vertical-reframe)
- ClipsAI's `resize` uses PySceneDetect with `min_scene_duration=0.25` s and `scene_merge_threshold=0.25` s. The merge threshold snaps scene changes onto diarized speaker-segment boundaries. — [ClipsAI resize reference](https://www.clipsai.com/references/resize)
- ClippyMe gets scenes from PySceneDetect, samples 7 frames per scene to choose a strategy, and resets tracker state at every scene cut. — [ClippyMe reframe architecture](https://github.com/fralapo/clippyme/blob/HEAD/docs/architecture/reframe.md)
- ai-clipper does not use a separate cut detector. It infers scenes from TalkNet face-track continuity (`detect_scenes_from_tracks(..., min_scene_frames=12)`), because TalkNet's own pipeline already runs shot detection and face tracking. — [ai-clipper talknet_speaker_detection.py](https://github.com/Rembr4nt/ai-clipper/blob/HEAD/scripts/talknet_speaker_detection.py)
- TransNetV2 (PyTorch port) details:
  - `transnetv2-pytorch` 1.0.5 was released 2025-06-01. It is inference-only and requires Python >=3.10.
  - Reported F1 scores: ClipShots 77.9, BBC Planet Earth 96.2, RAI 93.9.
  - MPS is about 3x faster than CPU but numerically inconsistent because some 3D convs fall back to CPU. In one example MPS found 66 scenes and CPU found 108 on the same video.
  - The package recommends CPU or CUDA for reproducible results. `device='auto'` prefers CUDA, then CPU, and only then MPS.
  - The weights file (`transnetv2-pytorch-weights.pth`) has to be loaded separately.
  - Source: [PyPI transnetv2-pytorch](https://pypi.org/project/transnetv2-pytorch/)
- ffmpeg `scdet` filter: `threshold` is a percentage of maximum change, the default is 10, and "Good values are in the [8.0, 14.0] range." It writes `lavfi.scd.score` and `lavfi.scd.time` frame metadata. — [FFmpeg filters docs: scdet](https://ffmpeg.org/ffmpeg-filters.html#scdet)

### Inferences
- Recommended default: `detect(video, ContentDetector(threshold=27, min_scene_len=15))` on the clip range only, not the whole episode. Post-merge shots under 0.8 s. Treat every cut as a hard reset of tracker state and crop path.
- Use AdaptiveDetector (3.0) when the show uses handheld or zooming cameras, where ContentDetector false-fires on motion.
- Running detection on a downscaled stream is the usual speed lever (PySceneDetect supports downscaling). I did not find M1 throughput numbers for PySceneDetect, so benchmark it.
- Run TransNetV2 on CPU only if you hit soft transitions or dissolves that PySceneDetect misses. Podcasts rarely have them.

### Gaps
- No published per-hour or FPS benchmark of PySceneDetect, TransNetV2-CPU, or `scdet` on M1. No head-to-head accuracy comparison on podcast footage specifically.
- The PySceneDetect docs page fetched was 0.7.1, but PyPI is at 0.7.2. Defaults are unlikely to have changed, but I did not verify against the 0.7.2 changelog.

---

## 2. Face detection on Mac (MediaPipe, YuNet, InsightFace/SCRFD, YOLO-face via Ultralytics/MPS, Apple Vision via pyobjc) and sampling rate

### Takeaway
MediaPipe is alive and ships arm64 macOS wheels (1.2.2, Nov 2026), but the legacy `mp.solutions` API is gone. New code must use the Tasks API (`FaceDetector` / `FaceLandmarker` with downloaded `.task` model bundles). Landmarks (FaceLandmarker) are worth the cost because lip landmarks feed the cheap active-speaker heuristic. Sample faces at about 5 fps, not every frame. OpenCV YuNet is the fastest CPU fallback. For Ultralytics YOLO, MPS speedups are not guaranteed, so benchmark MPS against CPU or export to CoreML.

### Cited Findings
- **MediaPipe packaging:**
  - Latest is `mediapipe` 1.2.2, uploaded 2026-11-03, as a single wheel `mediapipe-1.2.2-py3-none-macosx_11_0_arm64.whl`. Classifiers list Python 3.9 through 3.14. — [PyPI mediapipe](https://pypi.org/project/mediapipe/)
  - The wheel layout changed at 0.10.30 (2025-12-16), from per-CPython `cp310/311/312 ... macosx_11_0_universal2` wheels to one `py3-none-macosx_11_0_arm64` wheel. The last old-style release was 0.10.21 (2025-02-06). Releases since then: 0.10.30–0.10.35 (Dec 2025–Apr 2026), 1.0.0 (2026-07-27), 1.1.x (Oct 2026), 1.2.x (Oct–Nov 2026). — [PyPI mediapipe JSON](https://pypi.org/pypi/mediapipe/json)
- **`mp.solutions` removed:** On an issue where the reporter was on mediapipe 0.10.31, a maintainer replied: "the support for MediaPipe Solutions has been removed. Please migrate to MediaPipe Tasks." — [mediapipe issue #6200](https://github.com/google-ai-edge/mediapipe/issues/6200). Duplicate reports appear Dec 2025–Apr 2026 (#6204, #6241, #6261).
  - autoclip's code says "MediaPipe 1.0 removed the legacy `mp.solutions` API, so this uses the Tasks API with a downloaded model bundle." — [autoclip faces.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/faces.py). **Conflict:** the issue tracker shows it was already gone by 0.10.31 (Dec 2025), not only from 1.0.
- **Python 3.13 conflict:** autoclip's README says "Python 3.11 or 3.12 — not 3.13. MediaPipe publishes no 3.13 wheels" — [autoclip README](https://github.com/artbyjazi/autoclip). This is contradicted by current PyPI, where the py3-none arm64 wheel's classifiers go to 3.14 — [PyPI mediapipe](https://pypi.org/project/mediapipe/). The README claim is likely stale. Either way, Python 3.11/3.12 is safe.
- KazKozDev/auto-vertical-reframe pins MediaPipe 0.10.14, an old version with `mp.solutions`, plus Ultralytics YOLOv11, and is "tested on Apple Silicon". — [auto-vertical-reframe README](https://github.com/KazKozDev/auto-vertical-reframe)
- **autoclip's face stage:**
  - Uses MediaPipe FaceLandmarker at `DEFAULT_SAMPLE_FPS = 5.0`, described as "the main cost lever in the whole reframe stage". The stated reason: "Faces don't move fast enough to justify more, and the crop path is smoothed anyway."
  - `MAX_FACES = 4`; with more faces it falls back to a wide shot.
  - Lip landmarks used: inner lips 13/14, mouth corners 61/291. Eye landmarks 33/133/362/263 serve as the headroom anchor.
  - Source: [autoclip faces.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/faces.py)
- ClipsAI `resize` detects faces with MTCNN + MediaPipe on frames downscaled to `face_detect_width=960`, with `samples_per_segment=13` face-detection samples per diarized speaker segment. — [ClipsAI resize reference](https://www.clipsai.com/references/resize) **[STALE: repo last pushed 2024-01-17]** ([GitHub API metadata](https://github.com/ClipsAI/clipsai))
- ClippyMe uses YOLOv8 person detection plus MediaPipe FaceMesh mouth movement, with `REFRAME_MIN_FACE_RATIO=0.10` (ignore faces smaller than 10% of the largest). — [ClippyMe reframe architecture](https://github.com/fralapo/clippyme/blob/HEAD/docs/architecture/reframe.md); [ClippyMe configuration](https://github.com/fralapo/clippyme/blob/HEAD/docs/reference/configuration.md)
- **YuNet / SCRFD speed:** these numbers are rough and none were measured on M1.
  - A model card cites about 5 ms for YuNet against about 50 ms for SCRFD-10G on CPU — [HF yunet-GGUF](https://huggingface.co/cstr/yunet-GGUF).
  - A compilation cites about 1.6 ms/frame for YuNet at 320×320 on an i7-12700K, and SCRFD-0.5 at 22.3 ms against YuNet at 10.6 ms forward time — [ufme-docs SOTA detection](https://ufme-docs.pages.dev/research/sota-detection).
  - A 2025 benchmark on an i5-13600K found YuNet at about 0.03 s per face against MediaPipe at 0.04 s, with MediaPipe making fewer detections — [TEC benchmark](https://orion.tec.ac.cr/en/publications/benchmark-face-detection-using-deep-learning-models-andframeworks/).
- Current package versions on PyPI: `opencv-python` 5.0.0.93 (2026-07-02); `insightface` 2.1 (2026-10-03); `ultralytics` 8.4.203 (2026-11-05); `pyobjc-framework-Vision` 13.0 (2026-10-30, requires Python >=3.11). — PyPI JSON for [opencv-python](https://pypi.org/pypi/opencv-python/json), [insightface](https://pypi.org/pypi/insightface/json), [ultralytics](https://pypi.org/pypi/ultralytics/json), [pyobjc-framework-Vision](https://pypi.org/pypi/pyobjc-framework-Vision/json)
- Ultralytics + MPS: auto-vertical-reframe exposes `--device` (`cpu`, `mps`, ...) and a `--fast` mode with a smaller YOLO input that skips pose, masks, and saliency — [auto-vertical-reframe README](https://github.com/KazKozDev/auto-vertical-reframe). Users report YOLO on MPS being "really slow" with poor GPU utilisation, though those reports are about training on M1 Pro and M3 Max — [Apple Dev Forums M1 Pro](https://developer.apple.com/forums/thread/756252), [Apple Discussions M3 Max](https://discussions.apple.com/thread/256057418). Ultralytics documents CoreML export for its newest YOLO26 models — [Ultralytics CoreML docs](https://docs.ultralytics.com/vi/integrations/coreml).
- **Apple Vision:**
  - `VNDetectFaceRectanglesRequest` is available on macOS 10.13+. Revision 2 adds roll/yaw and revision 3 adds pitch. A newer Swift `DetectFaceRectanglesRequest` exists on macOS 15+. — [Apple docs](https://developer.apple.com/documentation/vision/vndetectfacerectanglesrequest.md), [objc2-vision bindings](https://docs.rs/objc2-vision/latest/src/objc2_vision/generated/VNDetectFaceRectanglesRequest.rs.html)
  - One anecdote reports 60–80% CPU on a webcam feed, with suggested mitigations of setting `regionOfInterest` and limiting faces per second — [SO mirror](https://kiwix.lema.org/stackoverflow.com_en_all_2023-11/questions/58664586/macos-reduce-cpu-usage-for-vnfaceobservation).
- TalkNet's pipeline uses the S3FD face detector — [ai-clipper README](https://github.com/Rembr4nt/ai-clipper) — and processes video at a fixed 25 fps (`TALKNET_FPS = 25.0`) — [ai-clipper auto_reframe.py](https://github.com/Rembr4nt/ai-clipper/blob/HEAD/scripts/auto_reframe.py).

### Inferences
- **Recommended M1 stack:** MediaPipe Tasks `FaceLandmarker` (CPU, XNNPACK) at 5 fps on frames downscaled to about 960 px wide. It gives boxes, eye positions for headroom, and lip landmarks for mouth-aspect-ratio (MAR) speaker cues in one pass. Interpolate or hold between samples; the smoothing stage absorbs the rest. Use OpenCV YuNet (`cv2.FaceDetectorYN` with the ONNX model from opencv_zoo) as a lightweight fallback if MediaPipe breaks again. Verify that API name against OpenCV 5.x.
- **Throughput estimate (inference, not measured):** at 5 fps with roughly 5–15 ms/frame, face detection for a 60 s clip is about 300 samples, so a few seconds of compute. Frame decode is likely the bigger cost. Decoding with ffmpeg piped at reduced fps and size (`-vf fps=5,scale=960:-2`) avoids decoding every frame in Python.
- InsightFace/SCRFD and YOLO-face add PyTorch/ONNX weight and setup cost but buy little for frontal, well-lit podcast faces. Use them only if profile or side-on faces are being missed.
- Apple Vision via pyobjc is feasible: it is native, uses the ANE/GPU, and is free. But there are no Python-side benchmarks or examples, and it returns no lip landmarks unless you also run `VNDetectFaceLandmarksRequest`. Treat it as an experiment, not the default.
- Pin `mediapipe` to an exact version and its `.task` model files. The API removal shows the package breaks without warning.

### Gaps
- No measured ms/frame on an M1 for any of MediaPipe Tasks, YuNet, SCRFD, YOLO-face (MPS against CPU against CoreML), or Apple Vision via pyobjc. All timing numbers above come from x86 desktops.
- I did not verify whether MediaPipe Tasks on macOS uses a GPU delegate from Python. It is assumed to be CPU.
- I did not find an official Ultralytics YOLO face-detection checkpoint. Face variants are third-party.

---

## 3. Active speaker detection (TalkNet, LR-ASD, Light-ASD, heuristics) and how open-source clippers solve it

### Takeaway
On an M1 without CUDA, the realistic, proven approach is **diarization (who speaks when) + face tracks + mouth-movement (MAR variance) to bind diarized speakers to faces once per clip**. Then let diarization turn boundaries drive the framing, with hysteresis. This is what autoclip, ClipsAI, and podcli do. Light-ASD (1.0M params) and LR-ASD are the best candidates if you want a real audio-visual model, but their repos are research code built around CUDA and S3FD and need porting. TalkNet is older, heavier, and its open-source integrations assume NVIDIA.

### Cited Findings
- **TalkNet-ASD** **[STALE: last push 2023-10-23]**: ACM MM 2021. AVA val mAP 92.3, test 90.8. Env setup is `conda create -n TalkNet python=3.7.9`. 520 stars. — [TalkNet-ASD README](https://github.com/TaoRuijie/TalkNet-ASD); metadata via GitHub API
- **Light-ASD** (CVPR 2023): AVA mAP 94.1% against 94.2% for the SOTA comparator, with "1.0M vs. 22.5M" params (about 23x fewer) and "0.6G vs. 2.6G" FLOPs (about 4x fewer) — [arXiv 2303.04439](https://arxiv.org/abs/2303.04439). The README reports 94.06% val mAP, weights shipped in `weight/`, and a demo `python Columbia_test.py --videoName 0001 --videoFolder demo`. Last push 2025-03-23. — [Light-ASD README](https://github.com/Junhua-Liao/Light-ASD)
- **LR-ASD**: 94.45% AVA val mAP, same demo interface, last push 2025-03-23. — [LR-ASD README](https://github.com/Junhua-Liao/LR-ASD)
- **ai-clipper** (MIT, created Oct 2026) reframes per camera shot with TalkNet:
  - Layouts are single speaker, split screen for two people, or blurred-background fallback.
  - It requires an NVIDIA GPU with CUDA ("does not run on CPU or Apple Silicon"), mainly because the speech model runs on `cuda:0`.
  - TalkNet setup needs a "NumPy 2 patch", and "Keep the project on a path without spaces: TalkNet's FFmpeg calls don't quote paths."
  - Source: [ai-clipper README](https://github.com/Rembr4nt/ai-clipper)
  - The code sanitises video names because "demoTalkNet.py runs its own FFmpeg commands through a shell with unquoted paths" — [auto_reframe.py](https://github.com/Rembr4nt/ai-clipper/blob/HEAD/scripts/auto_reframe.py).
- **ai-clipper layout decision** from TalkNet scores. Faces are split into left and right halves of the frame. It chooses `split` when:
  - each side has ≥20% of the combined frames (`MIN_RATIO=0.20`),
  - both have ≥`MIN_FRAMES`,
  - and both speak in ≥2% of frames (`MIN_SPEAKING=2.0`).
  - A silent second face also qualifies if it is ≥65% the size of the speaking face (`MIN_SIZE_RATIO=0.65`).
  - Otherwise it chooses `single` on the dominant or speaking track, falling back to `pad`. Speaking means TalkNet score > 0.
  - Source: [talknet_speaker_detection.py](https://github.com/Rembr4nt/ai-clipper/blob/HEAD/scripts/talknet_speaker_detection.py)
- **autoclip heuristic:**
  - The code combines MAR variance with diarization: "Correlating each track's mouth activity against each diarized speaker's timeline resolves that once for the whole clip, after which turn boundaries alone drive the framing — which is far more stable than deciding frame by frame."
  - It also says: "A full audio-visual model (TalkNet, LR-ASD) would beat this ... this heuristic is what runs on a laptop without another 400 MB of weights."
  - Constants: `ACTIVITY_WINDOW_S=1.0`, `SILENT_MAR_VARIANCE=0.0004`, `DOMINANCE_MARGIN=1.6`. The margin is the factor by which a track must beat the runner-up on mouth movement alone. Without it, "near-ties flip frame to frame".
  - When no speech signal resolves the choice, it falls back to a prominence ranking (size and centrality).
  - Source: [autoclip speaker.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/speaker.py)
- **autoclip face-track building**: greedy IoU/centre association with `IOU_THRESHOLD=0.25`, `CENTRE_DISTANCE_FACTOR=1.2`, `MAX_GAP_S=0.8`, `MIN_TRACK_DURATION_S=0.5`. — [autoclip tracker.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/tracker.py)
- **autoclip status**: diarization comes via WhisperX (`.[diarization]` extra), which pulls PyTorch and needs an HF token plus acceptance of the gated pyannote licences. On macOS, "Apple Silicon takes the CPU path". The project is pre-1.0. Its reframe acceptance bar is "no visible jitter, no cut-off faces, speaker on screen ≥95% of speaking time", and that bar has not yet been validated on a golden set. — [autoclip README](https://github.com/artbyjazi/autoclip)
- **ClipsAI** uses pyannote `speaker-diarization-3.0` (HF token required) with `min_segment_duration=1.5` s to define speaker segments, then face-detects within each segment. — [ClipsAI resize reference](https://www.clipsai.com/references/resize) **[STALE: pyannote 3.0 era, repo inactive since Jan 2024]**
- **ClippyMe** uses YOLOv8 + FaceMesh mouth movement with identity association by 2-D distance and box overlap.
  - Speaker switching uses hysteresis `REFRAME_SPEAKER_SWITCH_MARGIN=1.25`.
  - Dialogue framing `REFRAME_DIALOGUE_GROUP=1` keeps two similarly active, separated people in frame (score ratio 0.88, separation 0.28).
  - Source: [ClippyMe configuration](https://github.com/fralapo/clippyme/blob/HEAD/docs/reference/configuration.md)
  - Its research note: "Visual-only MAR variance is weaker than SOTA audio-visual ASD (TalkNet, Light-ASD, LoCoNet) ... a cheap win is to bias the MAR speaker score by which diarized speaker is talking ... A full TalkNet-style model is a large dependency and probably overkill." — [ClippyMe reframe-autoflip research](https://github.com/fralapo/clippyme/blob/HEAD/docs/research/reframe-autoflip.md)
- **podcli** (AGPL-3.0, runs on Apple Silicon): "Following the active speaker needs AssemblyAI, or a source install with openai-whisper and `HF_TOKEN`." Diarization is the speaker signal. — [podcli README](https://github.com/nmbrthirteen/podcli)
- Other repos, known only from search-result snippets and not verified: Dynamic-Facial-Framing treats the speaker as the face whose mouth moves while audio is active — [sahil-baligar/Dynamic-Facial-Framing](https://github.com/sahil-baligar/Dynamic-Facial-Framing). smart-reframe combines face detection with audio activity — [gauravzazz/smart-reframe](https://github.com/gauravzazz/smart-reframe).
- A commercial-tool failure mode: auto-reframe "can lock onto the wrong face during crosstalk", and the fix is to correct the speaker track or switch to split. — from a third-party guide surfaced in search ([techsy.io](https://www.techsy.io/en/blog/how-to-make-podcast-clips-with-ai)); low-authority source.

### Inferences
- **Recommended M1 pipeline (no CUDA):**
  1. Diarize the clip audio. Reuse the transcription stage's diarization: WhisperX/pyannote on CPU, or a cloud API.
  2. Run FaceLandmarker at 5 fps and build face tracks per shot (IoU 0.25, gap 0.8 s).
  3. For each diarized speaker, pick the track with the highest MAR variance during that speaker's turns, computed once per clip.
  4. Frame by turn boundaries, but only switch subject on turns of at least about 1–1.5 s (ClipsAI's 1.5 s minimum segment), with a 1.25–1.6x score margin.
  5. If there is no diarization or the result is ambiguous, use MAR-only with the 1.6x dominance margin, then fall back to the largest or most central face.
- Light-ASD is the only audio-visual ASD model small enough to be attractive on M1 (1M params). Porting means replacing `.cuda()` calls with an `mps`/`cpu` device and swapping the S3FD front end for your MediaPipe tracks. Because it is tiny, CPU inference is probably fine. This is untested; budget about a day of porting.
- **Path pitfall:** this project lives under `/Users/.../Content Clipping/`, a path with a space. TalkNet's demo scripts break on unquoted paths with spaces. Wrap or sanitize paths, or copy media to a space-free temp dir.

### Gaps
- No published M1/MPS run of TalkNet, Light-ASD, or LR-ASD, and no timing data. I did not check those repos' issue trackers for MPS ports.
- No head-to-head accuracy comparison of MAR+diarization heuristics against Light-ASD on podcast footage.
- How OpusClip, Vizard, or Adobe implement ASD internally is not publicly documented. I found no engineering write-ups.

---

## 4. Crop path smoothing (static per-shot vs smoothed tracking; filters; dead zones; re-centering at cuts)

### Takeaway
For podcasts, where people sit still, the strongest default is **one static crop per shot (per speaker turn), with a hard cut at camera cuts and speaker changes and no panning**. When tracking is needed (a guest leaning or shifting), use a 1€ filter, then a dead zone, then a velocity clamp, applied per shot and never across a cut. Concrete, already-tuned values exist; see below.

### Cited Findings
- **autoclip smoothing chain** (per shot):
  1. **One Euro Filter** with `min_cutoff=0.6`, `beta=0.02`, `d_cutoff=1.0`, "tuned for face tracking at 5–10 Hz sampling".
  2. **Dead zone** `dead_zone_px=12.0`: "below a movement threshold, don't move at all. A locked frame reads as intentional; a frame that micro-corrects reads as broken."
  3. **Velocity clamp** `max_velocity_px_s=260.0`, so "a detection glitch can never whip the frame across the shot".
  - The code notes "A plain EMA has to choose one or the other, so it either shakes or lags." Reference: Casiez et al., "1€ Filter" (CHI 2012).
  - Source: [autoclip smoothing.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/smoothing.py)
- **ClippyMe camera policy**: "the camera does not move within a shot". "Continuous tracking with a zoom that 'breathes' is what makes auto-reframed video feel seasick."
  - Default `REFRAME_COMFORT=1` (two-pass: track the whole clip, then decide the camera per scene) and `REFRAME_STATIC_AUTO=1` (one fixed crop per scene; zoom changes only at a cut).
  - The moving-camera alternatives, kept for A/B testing, are global smoothers `savgol` (default), `kalman`, or `l2`.
  - Source: [ClippyMe reframe architecture](https://github.com/fralapo/clippyme/blob/HEAD/docs/architecture/reframe.md)
- **ClippyMe tuning values** (fractions are of frame size):
  - `REFRAME_SNAP_CENTER=0.10` (snap a locked crop to centre when this close)
  - `REFRAME_MOTION_WIDE_THRESH=0.12` (subject travel that turns TRACK into WIDE)
  - `REFRAME_STATIONARY_THRESH=0.30`
  - streaming dead-band `REFRAME_DEADZONE_X/Y=0.05/0.08`
  - 1€ `mincutoff/beta=0.014/0.0008` (likely different units from autoclip's)
  - spring `response/damping=0.18/0.82`
  - lost-subject hold `REFRAME_LOST_HOLD=90` frames, then drift to centre at `0.05`
  - Source: [ClippyMe configuration](https://github.com/fralapo/clippyme/blob/HEAD/docs/reference/configuration.md)
  - Their empirical sweep found the tighter dead-band (0.20→0.05 X, 0.15→0.08 Y) "cut centering error ~30% with lower jerk". — [ClippyMe research note](https://github.com/fralapo/clippyme/blob/HEAD/docs/research/reframe-autoflip.md)
- **Google AutoFlip's model**:
  - Buffers a whole scene, then picks stationary, pan, or track.
  - `motion_stabilization_threshold_percent: 0.5` holds the scene steady if all focus objects stay within that fraction of the frame. `max_scene_size: 600` frames.
  - Source: [MediaPipe AutoFlip docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/autoflip.md)
  - The ClippyMe research note recommends the L1-optimal camera path (Grundmann et al., "Auto-Directed Video Stabilization with Robust L1 Optimal Camera Paths"). It describes the path as sparse: static segments joined by constant, linear, or parabolic pans, which reads as "professional tripod". — [ClippyMe research note](https://github.com/fralapo/clippyme/blob/HEAD/docs/research/reframe-autoflip.md)
- **Composition**: frame a talking head with the eyes about 1/3 from the top, which means shifting the crop centre down by about 0.10–0.12·crop_h relative to centring the face. Also give lead room on the side the subject is facing, using head yaw from FaceMesh plus `solvePnP`. — [ClippyMe research note](https://github.com/fralapo/clippyme/blob/HEAD/docs/research/reframe-autoflip.md)
- **ai-clipper** uses a fully static crop per scene from the mean face position and size: `FACE_WIDTH_RATIO=0.35`, `HEADROOM=0.60` ("face center sits 60% down from the crop top"), `MIN_CROP_W=400`/`MAX_CROP_W=1080` px at 1080p, and crop sizes forced to even values "to keep FFmpeg's yuv420p crop exact". — [ai-clipper auto_reframe.py](https://github.com/Rembr4nt/ai-clipper/blob/HEAD/scripts/auto_reframe.py)
- **KazKozDev presets**: `talking_head` tracks people and frames on the face with a smoothed pan/zoom camera path. `movie` "locks one static crop per shot and hard-cuts on scene or subject changes", with the noted downside that "a subject that walks across the frame can leave it". — [auto-vertical-reframe README](https://github.com/KazKozDev/auto-vertical-reframe)

### Inferences
- **Recommended defaults for a podcast clipper:**
  1. Re-centre at every camera cut and every accepted speaker switch, as a hard cut with no easing.
  2. Within a shot, compute the median face centre over the segment. If the face's range of motion is under about 5–12% of frame width (between ClippyMe's 0.05 dead-band and its 0.12 wide threshold), emit a static crop.
  3. Otherwise smooth with 1€ (min_cutoff 0.6, beta 0.02 at 5 Hz samples), then a 12 px dead zone, then a 260 px/s clamp. Or run Savitzky–Golay offline over the shot, since the whole clip is available.
  4. Keep the x axis only for 1080p sources. A 9:16 crop of a 1080-tall frame is 608×1080, full height, so y and zoom are fixed unless you deliberately zoom.
  5. When a face is lost, hold the crop for about 1–3 s, then ease to centre.
- On 16:9 → 9:16 from 1080p, the crop width is 1080×9/16 = 607.5 → 608 px (even). The output therefore upscales roughly 1.78x to 1080×1920. A 4K source avoids upscaling.
- ai-clipper's 0.60 headroom is effectively moot for single-person 9:16 crops of 1080p sources, because the crop is full-height and gets clamped. It matters for split-screen halves (9:8), where the crop is shorter than the frame.

### Gaps
- No user-study data on viewer preference between static-per-shot and smoothed tracking for podcasts. The evidence is practitioner judgement from ClippyMe and autoclip.
- Units of ClippyMe's 1€ parameters (normalised against pixels) were not verified in code.

---

## 5. Layouts for two-speaker wide shots (split-screen, blurred letterbox, pan)

### Takeaway
Commercial tools and open-source clones converge on three modes chosen per shot:
1. **Fill**: crop on the active speaker when one person talks.
2. **Split**: two face crops stacked top/bottom, each 1080×960, when both people are in the same wide frame and both talk, or during rapid back-and-forth.
3. **Fit/pad**: the whole 16:9 frame over a blurred copy of itself, when faces can't be resolved or there are three or more people.

Panning between speakers inside a shot is generally avoided.

### Cited Findings
- **OpusClip layouts**:
  - "Fill: We will focus on the speaker and crop them to fill the 9:16 screen", while Split shows both speakers stacked.
  - "Split, Three and Four layouts only work when the speakers appear together in the original video frame."
  - Fill is applied "at optimal times when one speaker is talking".
  - A Brand Template switch, "Pin first speaker", keeps the first speaker in the top slot of Split, Three, and Four layouts.
  - Source: [OpusClip help: layout and reframing](https://help.opus.pro/docs/article/layout-and-reframing), as summarised from search; not fetched in full.
- **ai-clipper ffmpeg graphs**, output always 1080×1920:
  - single: `crop=w:h:x:y,scale=1080:1920`
  - split: two crops at aspect 9:8, each `scale=1080:960`, then `[top][bottom]vstack`
  - pad: `[0:v]split[original][copy];[copy]scale=270:480,boxblur=10:5,scale=1080:1920[blurred];[original]scale=1080:-1[scaled];[blurred][scaled]overlay=0:(H-h)/2`. The comment says blurring at 1/4 size gives the "same look, ~14x faster".
  - The split comment calls it "OpusClip style tight crop".
  - Source: [ai-clipper auto_reframe.py](https://github.com/Rembr4nt/ai-clipper/blob/HEAD/scripts/auto_reframe.py)
- **ClippyMe per-scene strategies**:
  - TRACK: one near-static speaker, crop locked on the face.
  - WIDE: two or more faces, or a subject moving more than 12% of the frame, gets a locked, zoomed-out crop.
  - GENERAL: no faces, letterbox.
  - A `disabled` mode letterboxes the whole frame with optional `letterbox_zoom` of 0.05–0.15.
  - Source: [ClippyMe reframe architecture](https://github.com/fralapo/clippyme/blob/HEAD/docs/architecture/reframe.md)
- **AutoFlip** fills uncoverable areas with a solid background colour or a blurred copy of the frame (`padding_parameters { blur_cv_size: 200 }`) rather than black bars. — [MediaPipe AutoFlip docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/autoflip.md); [ClippyMe research note](https://github.com/fralapo/clippyme/blob/HEAD/docs/research/reframe-autoflip.md)
- **podcli** includes split-screen layouts. For remote shows, "one file per person becomes a split screen, and a single gallery recording is split into a camera per tile. Questions stay on the split and the guest goes full frame on long answers." — [podcli README](https://github.com/nmbrthirteen/podcli)
- **autoclip** handles mixed framing by letting each shot segment have its own crop size, then scaling every segment to the same output before concatenation. This "lets a wide two-shot and a tight single coexist in one clip without a mid-stream frame-size change, which ffmpeg filtergraphs don't allow". — [autoclip croppath.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/croppath.py)
- ClippyMe offers a letterboxed full-frame mode as a user-switchable option per clip. — [ClippyMe README](https://github.com/fralapo/clippyme)

### Inferences
- **Decision rule per shot:**
  - 1 face → Fill.
  - 2 faces with good separation (both ≥20% of frames and the second face ≥65% of the speaker's size, per ai-clipper), and the shot has turn changes shorter than about 3 s or overlapping speech → Split. Put the current speaker on top, or pin the host on top for consistency.
  - 2 faces but one dominant speaker for the whole shot → Fill on that speaker.
  - 0 faces, 3 or more faces, or a screen share → blurred-background Fit.
- Split crops at 9:8 from a 1080p source are about 540×480 px per face region upscaled to 1080×960, roughly 2x. Faces get soft, so prefer 4K sources or slightly looser crops.
- Pan-between-speakers within a shot reads as auto-reframed. Every source above avoids it in favour of hard cuts.
- Leave the lower third free for captions. In split layout, captions typically sit at the seam between halves. This is common practice, but I found no source for it.

### Gaps
- No public engineering write-up from OpusClip, Vizard, or Adobe on their layout-selection logic. Only help-centre behaviour descriptions.
- I did not fetch the full OpusClip help page. The details above come from search summaries.

---

## 6. Applying the crop (ffmpeg expressions/sendcmd/segments+concat vs OpenCV vs MoviePy) and encoding on M1

### Takeaway
Keep pixels in ffmpeg. Render each shot as its own segment with a `crop` filter, which is static, or animated with a piecewise-linear `t` expression, then scale to 1080×1920 and concat. Avoid OpenCV or MoviePy frame loops; they are slower and lose audio and colour metadata unless rebuilt. On M1, `h264_videotoolbox -q:v` (constant-quality mode, Apple Silicon only) is fast. Use `libx264 -crf 18–20` when quality matters more than speed.

### Cited Findings
- **autoclip** emits panning as a "piecewise-linear expression over `t` rather than a `sendcmd` script: it keeps everything in one filtergraph, survives seeking, and is far easier to inspect".
  - The expression is nested `if(lt(t,t1),(v0+slope*(t-t0)),...)`, capped at `MAX_KEYFRAMES_PER_SEGMENT=48`, with commas escaped (`\,`) for filtergraph parsing.
  - Segments are `trim`-ed, so PTS resets and keyframe times are offset per segment.
  - Final filter form: `crop=w=W:h=H:x='EXPR':y='EXPR'`.
  - Source: [autoclip croppath.py](https://github.com/artbyjazi/autoclip/blob/HEAD/backend/autoclip/pipeline/reframe/croppath.py)
- autoclip's verified output: "1080×1920 h264/yuv420p output, AAC at −14 LUFS, crop segments tiling each clip without gaps". — [autoclip README](https://github.com/artbyjazi/autoclip)
- ai-clipper encodes per-scene segments with `-c:v libx264 -crf 23 -preset fast -c:a aac -b:a 128k`, then concatenates them. — [ai-clipper auto_reframe.py](https://github.com/Rembr4nt/ai-clipper/blob/HEAD/scripts/auto_reframe.py)
- KazKozDev defaults to `--video-encoder h264_videotoolbox`, falling back to `libx264` with `--crf 18`. — [auto-vertical-reframe README](https://github.com/KazKozDev/auto-vertical-reframe)
- podcli uses "hardware encoding on VideoToolbox and NVENC, with a CPU fallback" and loudness-normalised audio. — [podcli README](https://github.com/nmbrthirteen/podcli)
- ClipsAI warns that `time_precision` below 4 decimal places "may cause ffmpeg cropping rounding errors" (default 6). — [ClipsAI resize reference](https://www.clipsai.com/references/resize)
- ClippyMe renders its reframe via OpenCV render loops (the `reframe.py` module is marked "No (OpenCV)" for host-testability). — [ClippyMe reframe architecture](https://github.com/fralapo/clippyme/blob/HEAD/docs/architecture/reframe.md)
- **VideoToolbox quality**:
  - Constant-quality mode for `h264_videotoolbox` (`-q:v`, 1–100, higher is better) exists only on Apple Silicon with FFmpeg ≥4.4, and does not work under Rosetta — [FFmpeg cvslog commit](https://lists.ffmpeg.org/pipermail/ffmpeg-cvslog/2021-March/126704.html), [slhck VBR settings](https://slhck.info/video/2017/02/24/vbr-settings.html).
  - One anecdotal test found `-q:v 50` produced files similar in size to `libx264 -crf 20` — [heguro scrapbox](https://scrapbox.io/heguro/ffmpeg%E3%81%A7videotoolbox(macOS)%E3%82%92%E4%BD%BF%E3%81%86).
  - A gist uses `-q:v 75` for hardware encodes and `libx264 -crf 17 -preset slow` for max quality — [gist](https://gist.github.com/wsaribeiro/4617730a0c747be8489d5e7b1487647b).
  - A videotoolbox vs libx265 benchmark on an M1 Pro exists for HEVC — [yre.jp](https://yre.jp/en/post/m1mac_h265/).
- ai-clipper's blurred background is computed at 270×480 and upscaled, about 14x faster than blurring at full resolution. — [ai-clipper auto_reframe.py](https://github.com/Rembr4nt/ai-clipper/blob/HEAD/scripts/auto_reframe.py)

### Inferences
- **Recommended render recipe** (per clip, assembled from the sources above):
  1. For each shot or turn segment, build a filter chain: `trim=start=S:end=E,setpts=PTS-STARTPTS,crop=w=608:h=1080:x='EXPR':y=0,scale=1080:1920:flags=lanczos,setsar=1`.
  2. Combine the segments with the `concat` filter in one `filter_complex`, with matching `atrim`/`asetpts` audio, or simply map the untouched audio of the clip.
  3. Encode once: `-c:v h264_videotoolbox -q:v 65 -profile:v high -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 192k` for drafts and bulk work, or `-c:v libx264 -crf 18 -preset slow` for finals.
  4. Use even crop sizes and round times to at least 4 decimals.
  - A single filter graph avoids re-encoding per segment and the concat-demuxer timestamp drift seen when segments are encoded separately.
- `sendcmd` works but is harder to debug, and autoclip found `t`-expressions sufficient. Prefer static crops anyway, which makes expressions trivial.
- MoviePy and OpenCV writing add a Python-side decode/encode loop. OpenCV `VideoWriter` drops audio and has limited codec control. Reserve them for previews or debug overlays.
- Instagram/Reels target: 1080×1920, H.264 High profile, yuv420p, 30 fps (or the source fps), AAC 48 kHz. This is common practice, but I fetched no official Meta spec page.
- If ffmpeg comes from Homebrew, check `ffmpeg -encoders | grep videotoolbox`. autoclip's README notes that "Homebrew split the formula; the plain one is a reduced build" — [autoclip README](https://github.com/artbyjazi/autoclip). Verify that the formula you install includes libx264, libass for captions, and videotoolbox.

### Gaps
- No measured M1 render throughput (seconds per minute of 1080×1920 output) for videotoolbox against libx264 in this crop+scale pipeline.
- No authoritative VMAF comparison of `h264_videotoolbox -q:v N` against `libx264 -crf N`. The mapping above is anecdotal.
- I did not fetch Instagram's official current upload or bitrate spec. Recommend checking Meta's help centre.

---

## 7. Is Google AutoFlip still usable in 2026? Newer turnkey reframing libraries

### Takeaway
AutoFlip is effectively dead for this use: it is a legacy MediaPipe solution, unsupported since March 2023, and ships as a Bazel-built C++ desktop example that "only works with OpenCV 3", with no Python API. Copy its ideas (per-scene stationary/pan/track decision, signal fusion, blurred padding), not its code. The newest turnkey options are 2026 open-source clippers. Of these, the MIT-licensed autoclip and ClippyMe code are the best references to borrow from. podcli is a full app but AGPL.

### Cited Findings
- **AutoFlip support status**: "We have ended support for this MediaPipe Legacy Solution as of March 1, 2023." The docs list it under "MediaPipe Legacy Solutions" and build it with `bazel build -c opt --define MEDIAPIPE_DISABLE_GPU=1 mediapipe/examples/desktop/autoflip:run_autoflip`. — [MediaPipe AutoFlip docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/autoflip.md)
- AutoFlip's README in the repo: "Note: AutoFlip currently only works with OpenCV 3." — [AutoFlip README](https://github.com/google-ai-edge/mediapipe/tree/master/mediapipe/examples/desktop/autoflip). The directory still exists in `google-ai-edge/mediapipe` as of Nov 2026, but recent commits touching it are repo-wide build maintenance ("Explicitly include direct headers and BUILD dependencies", 2026-11-05). — [GitHub API commits](https://github.com/google-ai-edge/mediapipe/commits/master/mediapipe/examples/desktop/autoflip)
- AutoFlip's concepts, per the docs:
  - `SignalFusingCalculator` combines weighted face and object signals.
  - `max_scene_size: 600`.
  - `motion_stabilization_threshold_percent: 0.5`.
  - `padding_parameters { blur_cv_size: 200 }`.
  - Source: [MediaPipe AutoFlip docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/autoflip.md)
  - ClippyMe's assessment: its own reframer is "feature-for-feature, close to AutoFlip's design ... and ahead of it in active-speaker selection (AutoFlip has none)". — [ClippyMe research note](https://github.com/fralapo/clippyme/blob/HEAD/docs/research/reframe-autoflip.md)
- **Turnkey / reference projects** (stars and dates from the GitHub API, 2026-11-07):

  | Project | License, stars, dates | Approach | Notes |
  |---|---|---|---|
  | [artbyjazi/autoclip](https://github.com/artbyjazi/autoclip) | MIT, 232★, created 2026-07-31 | MediaPipe FaceLandmarker + MAR + WhisperX diarization; 1€ smoothing; per-shot ffmpeg crop expressions | Pre-1.0; Python 3.11/3.12 |
  | [fralapo/clippyme](https://github.com/fralapo/clippyme) | MIT, 62★, created 2026-04-01, pushed 2026-10-14 | YOLOv8 + MediaPipe + PySceneDetect; static-per-scene camera; OpenCV render | Self-hosted Opus Clip alternative |
  | [nmbrthirteen/podcli](https://github.com/nmbrthirteen/podcli) | AGPL-3.0, 84★, pushed 2026-11-03 | Face tracking with split-screen layouts, VideoToolbox encode | Runs on Apple Silicon; Intel Macs unsupported; commercial licence available |
  | [KazKozDev/auto-vertical-reframe](https://github.com/KazKozDev/auto-vertical-reframe) | MIT, 25★, created 2026-04-19 | YOLOv11-seg + ByteTrack + MediaPipe + saliency; `talking_head`/`movie` presets; debug-preview video | Tested on Apple Silicon; speaker-aware ranking (`--speaker-json`) is only a placeholder |
  | [Rembr4nt/ai-clipper](https://github.com/Rembr4nt/ai-clipper) | MIT, 0★, created 2026-10-24 | TalkNet ASD; single/split/pad per shot | CUDA-only; blind test against OpusClip on 60 votes came out 27–27–6 ties, on choice of moment, not reframe |
  | [ClipsAI/clipsai](https://github.com/ClipsAI/clipsai) | MIT, 564★ | `resize()` = pyannote diarization + PySceneDetect + MTCNN/MediaPipe | **[STALE: last push 2024-01-17]**; depends on `mp.solutions`-era MediaPipe and pyannote 3.0 |

  The ClipsAI dependency remark is an inference from its MediaPipe usage and date.
- Search also surfaced [adityaraj-09/auto-vertical-reframe](https://github.com/adityaraj-09/auto-vertical-reframe) ("scene-aware vertical auto-reframe CLI"), [gauravzazz/smart-reframe](https://github.com/gauravzazz/smart-reframe), and [sahil-baligar/Dynamic-Facial-Framing](https://github.com/sahil-baligar/Dynamic-Facial-Framing). Not inspected.

### Inferences
- **Build rather than adopt.** Copy the architecture of autoclip (MIT) for the reframe stage:
  - PySceneDetect shots
  - FaceLandmarker at 5 fps
  - IoU tracks
  - diarization ↔ MAR binding
  - static-per-shot or 1€+dead-zone+clamp
  - ffmpeg crop/scale/concat with a VideoToolbox or x264 encode
- Add ClippyMe's WIDE/split decision and ai-clipper's split/pad filtergraphs.
- Avoid copying AGPL podcli code unless the project will be AGPL-compatible.
- ClipsAI likely needs patching to run on 2026 MediaPipe (no `mp.solutions`) and current pyannote. Do not depend on it directly.

### Gaps
- No evidence of any maintained Python binding or port of AutoFlip.
- I did not verify that ClipsAI actually breaks on mediapipe ≥0.10.30. This is inferred from the API removal.
- No newer Google or Apple first-party reframing SDK was found. Apple's Vision/Core ML has saliency and face APIs but no turnkey reframe API, and that claim is not sourced.
