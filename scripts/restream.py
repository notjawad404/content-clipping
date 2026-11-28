"""Relay a live feed (PS5 -> Twitch or unlisted YouTube) to your real channels (+ Kick), with a webcam slot.

The webcam slot shows a placeholder until you press C in this window (C again turns the camera off);
+ / - zoom the webcam in and out, 0 resets the zoom.
    python scripts/restream.py                  feed = twitch.tv/$TWITCH_CHANNEL
    python scripts/restream.py --source URL     feed = any live URL, e.g. an unlisted YouTube stream
    python scripts/restream.py --cam            start with the camera on
    python scripts/restream.py --no-overlay     no webcam slot, pass the stream through untouched

Each platform runs as its own stream, so one can drop or be restarted without touching the others:
    Y / T / K           start or stop YouTube / Twitch / Kick
    Shift+Y / T / K     restart that stream
    S                   show which streams are running;  H  list the keys

Settings come from .env (or the environment):
    TWITCH_CHANNEL      Twitch channel used as the feed when --source is not given
    SOURCE_URL          optional, default feed URL (overrides TWITCH_CHANNEL)
    YT_STREAM_KEY       optional, YouTube Studio > Go live > Stream > Stream key
    TWITCH_STREAM_KEY   optional, Twitch dashboard > Settings > Stream > Primary stream key
    TWITCH_COOKIES      optional, cookies.txt exported while logged in to twitch.tv (no ad slates)
    KICK_RTMP_URL       optional, Kick dashboard > Settings > Stream URL (rtmps://...)
    KICK_STREAM_KEY     optional, Kick stream key; Kick gets whichever feed is live
    TIKTOK_RTMP_URL     optional, TikTok LIVE server URL
    TIKTOK_STREAM_KEY   optional, TikTok LIVE stream key (sent as vertical 1080x1920)
    CAM_DEVICE          optional, webcam name (default "Integrated Webcam")
    CAM_PLACEHOLDER     optional, image shown while the camera is off
    CAM_BG              optional, webcam background: white (default), #RRGGBB, blur, none, an image or a looping video
    CAM_ZOOM            optional, starting webcam zoom (default 1.3)
    CAM_FPS             optional, webcam slot frame rate (default 30; 15 if the PC struggles)
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
CAM_POS = {
    "br": "W-w-{m}:H-h-{m}", "bl": "{m}:H-h-{m}", "tr": "W-w-{m}:{m}", "tl": "{m}:{m}",
}
QSV = ["-c:v", "h264_qsv", "-preset", "veryfast",
       "-force_key_frames", "expr:gte(t,n_forced*2)", "-forced_idr", "1"]


def _read_env() -> dict[str, str]:
    env = ROOT / ".env"
    if not env.exists():
        return {}
    values = {}
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_env() -> None:
    for key, value in _read_env().items():
        os.environ.setdefault(key, value)


def _ingest(base_var: str | None, base: str, key_var: str) -> str | None:
    """Ingest URL from the current .env, so an updated stream key is picked up on the next start."""
    env = _read_env()
    key = env.get(key_var) or os.environ.get(key_var)
    if base_var:
        base = env.get(base_var) or os.environ.get(base_var) or ""
    return f"{base.rstrip('/')}/{key}" if key and base else None


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


def _ffmpeg_cmd(tiktok: str | None, cam: dict | None, video: dict | None = None) -> list[str]:
    """Writes the relay as MPEG-TS to stdout for the per-platform pushers.

    video = {"height", "bitrate"} re-encodes at that size; None copies when possible.
    """
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-stats", "-i", "pipe:0"]
    if not cam and not tiktok and not video:
        return cmd + ["-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-f", "mpegts", "pipe:1"]

    video = video or {"height": 1080, "bitrate": 6000}
    h = video["height"]
    graph, main = [f"[0:v:0]scale=-2:{h}:flags=bilinear,format=yuv420p[base]"], "[base]"
    if cam:
        margin = round(24 * h / 1080)
        cam_w = round(480 * h / 1080 / 2) * 2
        cmd += ["-f", "rawvideo", "-pixel_format", "bgra", "-video_size", CAM_SIZE,
                "-framerate", str(cam["fps"]), "-i", f"tcp://127.0.0.1:{cam['port']}?listen=1"]
        graph.append(f"[1:v]scale={cam_w}:-2,format=yuva420p[cam]")
        graph.append(f"[base][cam]overlay={CAM_POS[cam['pos']].format(m=margin)}:eof_action=pass:format=yuv420[m]")
        main = "[m]"
    if tiktok:
        graph.append(main + VERTICAL.replace("split[a][b]", "split=3[out][a][b]"))
        main = "[out]"
    cmd += ["-filter_complex", ";".join(graph)]
    rate = video["bitrate"]
    # headers on every keyframe so a restarted pusher can join mid-stream
    cmd += ["-map", main, "-map", "0:a:0", *QSV, "-pix_fmt", "nv12",
            "-b:v", f"{rate}k", "-maxrate", f"{rate}k", "-bufsize", f"{rate * 2}k",
            "-flags:v", "+global_header", "-bsf:v", "dump_extra=freq=keyframe",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-f", "mpegts", "pipe:1"]
    if tiktok:
        cmd += ["-map", "[tt]", "-map", "0:a:0", *QSV, "-pix_fmt", "nv12", "-b:v", "4500k", "-maxrate", "4500k",
                "-bufsize", "9000k", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                "-flags", "+global_header", "-f", "tee", f"[f=flv:onfail=ignore]{tiktok}"]
    return cmd


def _camfx_cmd(cam: dict) -> list[str]:
    cmd = ["uv", "run", "--with", "mediapipe", "--with", "opencv-python",
           "python", str(ROOT / "scripts" / "camfx.py"),
           "--device", cam["device"], "--bg", cam["bg"], "--delay", str(cam["delay"]),
           "--port", str(cam["port"]), "--size", CAM_SIZE, "--fps", str(cam["fps"])]
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

    def key(self, key: str) -> bool:
        if key == "c":
            self.on = not self.on
            self.send("on" if self.on else "off")
            print(f"\nCamera {'ON' if self.on else 'OFF (placeholder)'}", flush=True)
        elif key in ("+", "=", "-", "0"):
            zoom = 1.0 if key == "0" else self.zoom * (1.1 if key in "+=" else 1 / 1.1)
            self.zoom = round(min(max(zoom, 1.0), 3.0), 2)
            self.send(f"zoom {self.zoom}")
            print(f"\nZoom {self.zoom}x", flush=True)
        else:
            return False
        return True


class Output:
    """One platform's stream: an ffmpeg that copies the relay to its ingest, startable on its own."""

    def __init__(self, name: str, key: str, base_var: str | None, base: str, key_var: str):
        self.name, self.key = name, key
        self.ingest = (base_var, base, key_var)
        self.url = _ingest(*self.ingest)
        self.wanted = True
        self.active = False
        self.proc: subprocess.Popen | None = None
        self.chunks: queue.Queue | None = None
        self.lock = threading.Lock()
        self.log = ROOT / "jobs" / f"relay_{name.lower()}.log"

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        with self.lock:
            if self.running():
                return
            self.url = _ingest(*self.ingest) or self.url
            self.log.parent.mkdir(exist_ok=True)
            self.proc = subprocess.Popen(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
                 "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-f", "flv", self.url],
                stdin=subprocess.PIPE, stderr=self.log.open("w"), cwd=ROOT)
            self.chunks = queue.Queue(maxsize=1024)
            threading.Thread(target=self._write, args=(self.proc, self.chunks), daemon=True).start()

    @staticmethod
    def _write(proc: subprocess.Popen, chunks: queue.Queue) -> None:
        try:
            while (chunk := chunks.get()) is not None:
                proc.stdin.write(chunk)
            proc.stdin.close()
        except OSError:
            pass

    def stop(self) -> None:
        with self.lock:
            proc, chunks, self.proc = self.proc, self.chunks, None
        if proc:
            try:
                chunks.put_nowait(None)
            except queue.Full:
                pass
            _stop(proc)

    def send(self, data: bytes) -> None:
        with self.lock:
            proc, chunks = self.proc, self.chunks
        if proc is None:
            return
        if proc.poll() is not None:
            self._dropped(_last_line(self.log) or f"ffmpeg exited ({proc.returncode})")
            return
        try:
            chunks.put_nowait(data)
        except queue.Full:
            self._dropped("upload fell too far behind")

    def _dropped(self, why: str) -> None:
        self.stop()
        print(f"\n{self.name} stream dropped: {why}\n"
              f"  press {self.key.upper()} to start it again", flush=True)

    def status(self) -> str:
        if self.running():
            return "LIVE"
        if not self.active:
            return "waiting for a relay" if self.wanted else "off"
        return "stopped"


def _last_line(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except OSError:
        return ""
    return lines[-1].strip() if lines else ""


def _fanout(src, outputs: list[Output]) -> None:
    rest = b""
    while chunk := src.read1(1 << 16):
        data = rest + chunk
        cut = len(data) - len(data) % 188
        rest, data = data[cut:], data[:cut]
        for out in outputs:
            out.send(data)


def _toggle(out: Output, restart: bool) -> None:
    if restart:
        out.wanted = True
        if out.active:
            out.stop()
            out.start()
            print(f"\n{out.name}: restarting", flush=True)
        else:
            print(f"\n{out.name}: not in this relay; it will start with the next one", flush=True)
    elif out.running() or (out.wanted and not out.active):
        out.wanted = False
        out.stop()
        print(f"\n{out.name}: stopped", flush=True)
    else:
        out.wanted = True
        if out.active:
            out.start()
        print(f"\n{out.name}: {'starting' if out.active else 'will start with the next relay'}", flush=True)


def _help(outputs: list[Output], camfx: Camfx | None) -> str:
    keys = ", ".join(f"{o.key.upper()} {o.name}" for o in outputs)
    text = f"Keys: {keys} = start/stop; Shift+key = restart; S = status; H = help"
    if camfx:
        text += "\n      C = camera on/off, + / - = zoom, 0 = reset zoom"
    return text


def _controls(outputs: list[Output], camfx: Camfx | None) -> None:
    if os.name != "nt":
        return
    import msvcrt

    by_key = {o.key: o for o in outputs}
    while True:
        if not msvcrt.kbhit():
            time.sleep(0.05)
            continue
        key = msvcrt.getwch()
        low = key.lower()
        if low in by_key:
            _toggle(by_key[low], restart=key != low)
        elif low == "s":
            print("\n" + "\n".join(f"  {o.name:<8} {o.status()}" for o in outputs), flush=True)
        elif low in ("h", "?"):
            print("\n" + _help(outputs, camfx), flush=True)
        elif camfx:
            camfx.key(low)


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


def _relay(source: str, outputs: list[Output], tiktok: str | None, cam: dict | None, buffer: float,
           video: dict | None = None) -> float:
    src = subprocess.Popen(_pull_cmd(source), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=ROOT)
    started = time.monotonic()
    cmd = _ffmpeg_cmd(tiktok, cam, video)
    if buffer > 0:
        cmd[cmd.index("-i"):cmd.index("-i")] = ["-re"]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for out in outputs:
        out.active = True
        if out.wanted:
            out.start()
    threading.Thread(target=_fanout, args=(ff.stdout, outputs), daemon=True).start()
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
        for out in outputs:
            out.active = False
            out.stop()
    return time.monotonic() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", help="fixed feed URL, sent to every configured output (skips auto mode)")
    parser.add_argument("--channel", help="Twitch channel to watch (overrides TWITCH_CHANNEL)")
    parser.add_argument("--yt-channel", help="YouTube channel to watch, e.g. @handle (overrides YT_CHANNEL)")
    parser.add_argument("--no-tiktok", action="store_true", help="skip TikTok even if a key is set")
    parser.add_argument("--no-kick", action="store_true", help="skip Kick even if a key is set")
    parser.add_argument("--no-overlay", action="store_true", help="no webcam slot; pass the stream through")
    parser.add_argument("--cam", action="store_true", help="start with the camera on instead of the placeholder")
    parser.add_argument("--cam-bg", help="white (default, or CAM_BG), black, #RRGGBB, blur, none (cut-out), "
                                          "or a background image / video path")
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
    yt_out = Output("YouTube", "y", None, YT_INGEST, "YT_STREAM_KEY") if env("YT_STREAM_KEY") else None
    tw_out = Output("Twitch", "t", None, TWITCH_INGEST, "TWITCH_STREAM_KEY") if env("TWITCH_STREAM_KEY") else None
    kick = None
    if not args.no_kick and env("KICK_RTMP_URL") and env("KICK_STREAM_KEY"):
        kick = Output("Kick", "k", "KICK_RTMP_URL", "", "KICK_STREAM_KEY")
    outputs = [o for o in (yt_out, tw_out, kick) if o]
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
        feeds.append(("YouTube" if "youtu" in source else "Twitch", source, outputs, [o.name for o in outputs]))
    else:
        twitch = args.channel or env("TWITCH_CHANNEL")
        youtube = args.yt_channel or env("YT_CHANNEL")
        for name, channel, url, target in (("Twitch", twitch, f"https://www.twitch.tv/{twitch}", yt_out),
                                           ("YouTube", youtube, youtube and _youtube_live_url(youtube), tw_out)):
            targets = [o for o in (target, kick) if o]
            if channel and targets:
                feeds.append((name, url, targets, [o.name for o in targets]))
    if tiktok:
        feeds = [(n, u, o, names + ["TikTok"]) for n, u, o, names in feeds]
    if not feeds or not any(f[2] or tiktok for f in feeds):
        sys.exit("Nothing to relay. Set TWITCH_CHANNEL + YT_STREAM_KEY (Twitch -> YouTube) and/or "
                 "YT_CHANNEL + TWITCH_STREAM_KEY (YouTube -> Twitch) in .env (KICK_* adds Kick), or pass --source")
    for tool in ("ffmpeg", "yt-dlp"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found on PATH")

    cam = camfx = None
    if not args.no_overlay:
        cam = {"device": env("CAM_DEVICE", "Integrated Webcam"), "bg": args.cam_bg or env("CAM_BG", "white"),
               "delay": (args.cam_delay or delays[feeds[0][0]]) + buffer, "pos": args.cam_pos, "port": _free_port(),
               "on": args.cam, "placeholder": args.placeholder or env("CAM_PLACEHOLDER"),
               "zoom": args.cam_zoom or float(env("CAM_ZOOM", 1.3)), "fps": int(env("CAM_FPS", 30))}
        camfx = Camfx(cam)
    threading.Thread(target=_controls, args=(outputs, camfx), daemon=True).start()

    for name, url, _, names in feeds:
        print(f"Watching {name} ({url}) -> {' + '.join(names)}")
    if cam:
        print(f"Camera {'ON' if args.cam else 'OFF (placeholder)'}")
    print(_help(outputs, camfx))
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
        for out in outputs:
            out.stop()
        if camfx:
            _stop(camfx.proc)


if __name__ == "__main__":
    main()
