"""Relay a live feed (PS5 -> Twitch or unlisted YouTube) to your real channels, with a webcam slot.

The webcam slot shows a placeholder until you press C in this window (C again turns the camera off);
+ / - zoom the webcam in and out, 0 resets the zoom.
    python scripts/restream.py                  feed = twitch.tv/$TWITCH_CHANNEL
    python scripts/restream.py --source URL     feed = any live URL, e.g. an unlisted YouTube stream
    python scripts/restream.py --cam            start with the camera on
    python scripts/restream.py --no-overlay     no webcam slot, pass the stream through untouched

Settings come from .env (or the environment):
    TWITCH_CHANNEL      Twitch channel used as the feed when --source is not given
    SOURCE_URL          optional, default feed URL (overrides TWITCH_CHANNEL)
    YT_STREAM_KEY       optional, YouTube Studio > Go live > Stream > Stream key
    TWITCH_STREAM_KEY   optional, Twitch dashboard > Settings > Stream > Primary stream key
    TWITCH_COOKIES      optional, cookies.txt exported while logged in to twitch.tv (no ad slates)
    TIKTOK_RTMP_URL     optional, TikTok LIVE server URL
    TIKTOK_STREAM_KEY   optional, TikTok LIVE stream key (sent as vertical 1080x1920)
    CAM_DEVICE          optional, webcam name (default "Integrated Webcam")
    CAM_PLACEHOLDER     optional, image shown while the camera is off
    CAM_BG              optional, webcam background: white (default), #RRGGBB, blur, none, or an image
    CAM_ZOOM            optional, starting webcam zoom (default 1.3)
    TWITCH_HEIGHT       optional, Twitch output height (default 720; Twitch gives new channels no quality options)
    TWITCH_BITRATE      optional, Twitch video bitrate in kbps (default 4000)
    YT_HEIGHT           optional, YouTube output height when re-encoding (default 1080)
    YT_BITRATE          optional, YouTube video bitrate in kbps when re-encoding (default 6000)
    RELAY_BUFFER        optional, seconds the relay runs behind to smooth out lag (default 20)

Waits for the feed to go live, and reconnects if it drops. Ctrl+C to stop.
"""
from __future__ import annotations

import argparse
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YT_INGEST = "rtmp://a.rtmp.youtube.com/live2"
TWITCH_INGEST = "rtmp://live.twitch.tv/app"
VERTICAL = (
    "split[a][b];"
    "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];"
    "[b]scale=1080:-2[fg];"
    "[bg][fg]overlay=(W-w)/2:(H-h)/2[tt]"
)
CAM_SIZE = "480x360"
CAM_FPS = 15
CAM_POS = {
    "br": "W-w-{m}:H-h-{m}", "bl": "{m}:H-h-{m}", "tr": "W-w-{m}:{m}", "tl": "{m}:{m}",
}
QSV = ["-c:v", "h264_qsv", "-preset", "veryfast",
       "-force_key_frames", "expr:gte(t,n_forced*2)", "-forced_idr", "1"]


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _pull_cmd(source: str) -> list[str]:
    fmt = "b" if "twitch.tv" in source else "bv*[height<=1080]+ba/b"
    cmd = ["yt-dlp", "-q", "--no-warnings", "-f", fmt, "--hls-use-mpegts"]
    if "twitch.tv" in source and os.environ.get("TWITCH_COOKIES"):
        cmd += ["--cookies", os.environ["TWITCH_COOKIES"]]
    return cmd + ["-o", "-", source]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _copy_to(urls: list[str]) -> list[str]:
    cmd = []
    for url in urls:
        cmd += ["-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-f", "flv", url]
    return cmd


def _tee(urls: list[str]) -> list[str]:
    if len(urls) == 1:
        return ["-f", "flv", urls[0]]
    return ["-flags", "+global_header", "-f", "tee", "|".join(f"[f=flv:onfail=ignore]{u}" for u in urls)]


def _ffmpeg_cmd(outputs: list[str], tiktok: str | None, cam: dict | None, video: dict | None = None) -> list[str]:
    """video = {"height", "bitrate"} re-encodes the outputs at that size; None copies them when possible."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-stats", "-i", "pipe:0"]
    if not cam and not tiktok and not video:
        return cmd + _copy_to(outputs)

    video = video or {"height": 1080, "bitrate": 6000}
    h = video["height"]
    graph, main = [f"[0:v:0]scale=-2:{h}:flags=bilinear,format=yuv420p[base]"], "[base]"
    if cam:
        margin = round(24 * h / 1080)
        cam_w = round(480 * h / 1080 / 2) * 2
        cmd += ["-f", "rawvideo", "-pixel_format", "bgra", "-video_size", CAM_SIZE,
                "-framerate", str(CAM_FPS), "-i", f"tcp://127.0.0.1:{cam['port']}?listen=1"]
        graph.append(f"[1:v]scale={cam_w}:-2,format=yuva420p[cam]")
        graph.append(f"[base][cam]overlay={CAM_POS[cam['pos']].format(m=margin)}:eof_action=pass:format=yuv420[m]")
        main = "[m]"
    if tiktok:
        split = "split=3[out][a][b]" if outputs else "split[a][b]"
        graph.append(main + VERTICAL.replace("split[a][b]", split))
        main = "[out]"
    cmd += ["-filter_complex", ";".join(graph)]
    rate = video["bitrate"]
    if outputs:
        cmd += ["-map", main, "-map", "0:a:0", *QSV, "-pix_fmt", "nv12",
                "-b:v", f"{rate}k", "-maxrate", f"{rate}k", "-bufsize", f"{rate * 2}k",
                "-c:a", "aac", "-b:a", "160k", "-ar", "44100"] + _tee(outputs)
    if tiktok:
        cmd += ["-map", "[tt]", "-map", "0:a:0", *QSV, "-pix_fmt", "nv12", "-b:v", "4500k", "-maxrate", "4500k",
                "-bufsize", "9000k", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                "-f", "flv", tiktok]
    return cmd


def _camfx_cmd(cam: dict) -> list[str]:
    cmd = ["uv", "run", "--with", "mediapipe", "--with", "opencv-python",
           "python", str(ROOT / "scripts" / "camfx.py"),
           "--device", cam["device"], "--bg", cam["bg"], "--delay", str(cam["delay"]),
           "--port", str(cam["port"]), "--size", CAM_SIZE, "--fps", str(CAM_FPS)]
    if cam["placeholder"]:
        cmd += ["--placeholder", cam["placeholder"]]
    return cmd + ["--zoom", str(cam["zoom"])] + (["--start-on"] if cam["on"] else [])


def _stop(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()


class Camfx:
    def __init__(self, cam: dict):
        log = ROOT / "jobs" / "camfx.log"
        log.parent.mkdir(exist_ok=True)
        env = dict(os.environ, GLOG_minloglevel="2", TF_CPP_MIN_LOG_LEVEL="2")
        self.proc = subprocess.Popen(_camfx_cmd(cam), stdin=subprocess.PIPE, stderr=log.open("w"),
                                     cwd=ROOT, env=env)
        self.lock = threading.Lock()
        self.on = cam["on"]
        self.zoom = cam["zoom"]

    def send(self, msg: str) -> None:
        with self.lock:
            self.proc.stdin.write(f"{msg}\n".encode())
            self.proc.stdin.flush()

    def keys(self) -> None:
        if os.name != "nt":
            return
        import msvcrt

        while self.proc.poll() is None:
            if msvcrt.kbhit():
                key = msvcrt.getwch().lower()
                if key == "c":
                    self.on = not self.on
                    self.send("on" if self.on else "off")
                    print(f"\nCamera {'ON' if self.on else 'OFF (placeholder)'}", flush=True)
                elif key in "+=-0":
                    zoom = 1.0 if key == "0" else self.zoom * (1.1 if key in "+=" else 1 / 1.1)
                    self.zoom = round(min(max(zoom, 1.0), 3.0), 2)
                    self.send(f"zoom {self.zoom}")
                    print(f"\nZoom {self.zoom}x", flush=True)
            time.sleep(0.05)


def _is_live(url: str) -> bool:
    try:
        r = subprocess.run(["yt-dlp", "-q", "--no-warnings", "--skip-download", "--print", "is_live", url],
                           capture_output=True, text=True, cwd=ROOT, timeout=60)
    except subprocess.TimeoutExpired:
        return False
    return r.stdout.strip().splitlines()[-1:] == ["True"]


def _youtube_live_url(channel: str) -> str:
    if channel.startswith("http"):
        return channel.rstrip("/") + ("" if channel.rstrip("/").endswith("/live") else "/live")
    return f"https://www.youtube.com/{channel if channel.startswith(('@', 'channel/')) else '@' + channel}/live"


def _pump(src, dst, buffer: float, stall: float = 20.0) -> bool:
    """Copy src to dst after `buffer` seconds; returns True if the feed stopped sending."""
    chunks: queue.Queue[bytes] = queue.Queue()

    def reader() -> None:
        while chunk := src.read1(1 << 16):
            chunks.put(chunk)
        chunks.put(b"")

    threading.Thread(target=reader, daemon=True).start()
    stalled = False
    try:
        chunk = chunks.get(timeout=90)
        if chunk:
            time.sleep(buffer)
        while chunk:
            dst.write(chunk)
            chunk = chunks.get(timeout=stall)
    except queue.Empty:
        stalled = True
    except OSError:
        pass
    finally:
        try:
            dst.close()
        except OSError:
            pass
    return stalled


def _keep_awake(on: bool) -> None:
    if os.name == "nt":
        import ctypes

        es_continuous, es_system_required = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | (es_system_required if on else 0))


def _relay(source: str, outputs: list[str], tiktok: str | None, cam: dict | None, buffer: float,
           video: dict | None = None) -> float:
    src = subprocess.Popen(_pull_cmd(source), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=ROOT)
    started = time.monotonic()
    cmd = _ffmpeg_cmd(outputs, tiktok, cam, video)
    if buffer > 0:
        cmd[cmd.index("-i"):cmd.index("-i")] = ["-re"]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        if _pump(src.stdout, ff.stdin, buffer):
            print("Feed stopped sending video; reconnecting...", flush=True)
        _stop(src)
        ff.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass
    finally:
        _stop(src)
        if ff.poll() is None:
            _stop(ff)
    return time.monotonic() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", help="fixed feed URL, sent to every configured output (skips auto mode)")
    parser.add_argument("--channel", help="Twitch channel to watch (overrides TWITCH_CHANNEL)")
    parser.add_argument("--yt-channel", help="YouTube channel to watch, e.g. @handle (overrides YT_CHANNEL)")
    parser.add_argument("--no-tiktok", action="store_true", help="skip TikTok even if a key is set")
    parser.add_argument("--no-overlay", action="store_true", help="no webcam slot; pass the stream through")
    parser.add_argument("--cam", action="store_true", help="start with the camera on instead of the placeholder")
    parser.add_argument("--cam-bg", help="white (default, or CAM_BG), black, #RRGGBB, blur, none (cut-out), "
                                          "or a background image path")
    parser.add_argument("--cam-delay", type=float,
                        help="seconds to hold the webcam back to match the gameplay "
                             "(default: CAM_DELAY_TWITCH=8 / CAM_DELAY_YOUTUBE=15 by feed)")
    parser.add_argument("--cam-pos", choices=sorted(CAM_POS), default="br", help="corner for the webcam")
    parser.add_argument("--cam-zoom", type=float, help="starting webcam zoom, 1.0-3.0 (default CAM_ZOOM or 1.3)")
    parser.add_argument("--placeholder", help="image shown while the camera is off (overrides CAM_PLACEHOLDER)")
    parser.add_argument("--buffer", type=float,
                        help="seconds the relay runs behind the feed to ride out network hiccups "
                             "(default RELAY_BUFFER or 20; 0 = as fast as possible)")
    parser.add_argument("--wait", type=int, default=30, help="seconds between live checks")
    parser.add_argument("--cooldown", type=int, default=120,
                        help="seconds to ignore the other platform after a relay ends, so it is not relayed back")
    args = parser.parse_args()

    _load_env()
    env = os.environ.get
    yt_out = f"{YT_INGEST}/{env('YT_STREAM_KEY')}" if env("YT_STREAM_KEY") else None
    tw_out = f"{TWITCH_INGEST}/{env('TWITCH_STREAM_KEY')}" if env("TWITCH_STREAM_KEY") else None
    tiktok = None
    if not args.no_tiktok and env("TIKTOK_RTMP_URL") and env("TIKTOK_STREAM_KEY"):
        tiktok = f"{env('TIKTOK_RTMP_URL').rstrip('/')}/{env('TIKTOK_STREAM_KEY')}"
    delays = {"Twitch": float(env("CAM_DELAY_TWITCH", 8)), "YouTube": float(env("CAM_DELAY_YOUTUBE", 15))}
    buffer = args.buffer if args.buffer is not None else float(env("RELAY_BUFFER", 20))
    twitch_video = {"height": int(env("TWITCH_HEIGHT", 720)), "bitrate": int(env("TWITCH_BITRATE", 4000))}
    youtube_video = {"height": int(env("YT_HEIGHT", 1080)), "bitrate": int(env("YT_BITRATE", 6000))}

    # (name, feed url, outputs, output names)
    feeds = []
    source = args.source or env("SOURCE_URL")
    if source:
        outs = [o for o in (yt_out, tw_out) if o]
        names = [n for n, o in (("YouTube", yt_out), ("Twitch", tw_out)) if o]
        feeds.append(("YouTube" if "youtu" in source else "Twitch", source, outs, names))
    else:
        twitch = args.channel or env("TWITCH_CHANNEL")
        youtube = args.yt_channel or env("YT_CHANNEL")
        if twitch and yt_out:
            feeds.append(("Twitch", f"https://www.twitch.tv/{twitch}", [yt_out], ["YouTube"]))
        if youtube and tw_out:
            feeds.append(("YouTube", _youtube_live_url(youtube), [tw_out], ["Twitch"]))
    if tiktok:
        feeds = [(n, u, o, names + ["TikTok"]) for n, u, o, names in feeds]
    if not feeds or not any(f[2] or tiktok for f in feeds):
        sys.exit("Nothing to relay. Set TWITCH_CHANNEL + YT_STREAM_KEY (Twitch -> YouTube) and/or "
                 "YT_CHANNEL + TWITCH_STREAM_KEY (YouTube -> Twitch) in .env, or pass --source")
    for tool in ("ffmpeg", "yt-dlp"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found on PATH")

    cam = camfx = None
    if not args.no_overlay:
        cam = {"device": env("CAM_DEVICE", "Integrated Webcam"), "bg": args.cam_bg or env("CAM_BG", "white"),
               "delay": (args.cam_delay or delays[feeds[0][0]]) + buffer, "pos": args.cam_pos, "port": _free_port(),
               "on": args.cam, "placeholder": args.placeholder or env("CAM_PLACEHOLDER"),
               "zoom": args.cam_zoom or float(env("CAM_ZOOM", 1.3))}
        camfx = Camfx(cam)
        threading.Thread(target=camfx.keys, daemon=True).start()

    for name, url, _, names in feeds:
        print(f"Watching {name} ({url}) -> {' + '.join(names)}")
    if cam:
        print(f"Camera {'ON' if args.cam else 'OFF (placeholder)'}; press C to toggle, + / - to zoom, 0 to reset zoom.")
    print("Ctrl+C to stop.", flush=True)

    ignore_until: dict[str, float] = {}
    try:
        while True:
            live = None
            for feed in feeds:
                if time.monotonic() >= ignore_until.get(feed[0], 0) and _is_live(feed[1]):
                    live = feed
                    break
            if not live:
                time.sleep(args.wait)
                continue
            name, url, outs, names = live
            if camfx:
                camfx.send(f"delay {(args.cam_delay or delays[name]) + buffer}")
            print(f"{name} is live -> relaying to {' + '.join(names)}", flush=True)
            _keep_awake(True)
            try:
                video = twitch_video if "Twitch" in names else (youtube_video if cam else None)
                ran = _relay(url, outs, tiktok, cam, buffer, video)
            finally:
                _keep_awake(False)
            print(f"{name} relay ended after {ran / 60:.1f} min", flush=True)
            for other in feeds:
                if other[0] != name:
                    ignore_until[other[0]] = time.monotonic() + args.cooldown
            if ran < 15:
                time.sleep(args.wait)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if camfx:
            _stop(camfx.proc)


if __name__ == "__main__":
    main()
