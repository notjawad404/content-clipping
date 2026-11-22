"""Webcam slot for restream.py: a placeholder image, or the webcam with an AI virtual background.

Streams raw BGRA frames to ffmpeg on 127.0.0.1:<port> and reconnects when ffmpeg restarts.
Reads "on" / "off" / "delay <seconds>" / "zoom <factor>" lines on stdin to switch between the camera and the placeholder; if the
camera cannot be opened or stops sending frames, the placeholder is shown instead.
Camera frames are held back by --delay seconds so you line up with the relayed gameplay.
    --bg white | blur | none | #RRGGBB | path/to/image.jpg     (none = just you cut out, no box)

Needs: uv run --with mediapipe --with opencv-python, and models/selfie_segmenter.tflite.
"""
from __future__ import annotations

import argparse
import collections
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "selfie_segmenter.tflite"
DEFAULT_PLACEHOLDER = ROOT / "assets" / "branding" / "cam_placeholder.png"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/image_segmenter/"
             "selfie_segmenter/float16/latest/selfie_segmenter.tflite")


def _camera_index(device: str) -> int:
    if device.isdigit():
        return int(device)
    out = subprocess.run(["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                         capture_output=True, text=True, errors="replace").stderr
    names = re.findall(r'"([^"]+)" \(video\)', out)
    if device not in names:
        raise OSError(f"Camera {device!r} not found; available: {names}")
    return names.index(device)


def _open_camera(device: str, w: int, h: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(_camera_index(device), cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, 30)
    if not cap.isOpened():
        raise OSError(f"Cannot open camera {device!r}")
    return cap


def _cover(img: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    w, h = size
    scale = max(w / img.shape[1], h / img.shape[0])
    img = cv2.resize(img, (round(img.shape[1] * scale), round(img.shape[0] * scale)))
    y, x = (img.shape[0] - h) // 2, (img.shape[1] - w) // 2
    return img[y:y + h, x:x + w]


def _zoom(frame: np.ndarray, zoom: float) -> np.ndarray:
    if zoom <= 1.0:
        return frame
    h, w = frame.shape[:2]
    cw, ch = round(w / zoom), round(h / zoom)
    x, y = (w - cw) // 2, (h - ch) // 2
    return frame[y:y + ch, x:x + cw]


def _placeholder(path: str | None, size: tuple[int, int]) -> np.ndarray:
    w, h = size
    if not path and DEFAULT_PLACEHOLDER.exists():
        path = str(DEFAULT_PLACEHOLDER)
    if path:
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise SystemExit(f"Cannot read placeholder image {path!r}")
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        elif img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        return _cover(img, size)
    ys = np.linspace(0, 1, h)[:, None, None]
    img = ((1 - ys) * np.array([60, 24, 40]) + ys * np.array([30, 12, 18])).astype(np.uint8)
    img = np.ascontiguousarray(np.broadcast_to(img, (h, w, 3)))
    cv2.rectangle(img, (2, 2), (w - 3, h - 3), (180, 90, 150), 2)
    font = cv2.FONT_HERSHEY_DUPLEX
    for text, scale, dy in (("CAMERA OFF", 1.3, -10), ("back soon", 0.8, 40)):
        (tw, th), _ = cv2.getTextSize(text, font, scale, 2)
        cv2.putText(img, text, ((w - tw) // 2, h // 2 + dy), font, scale, (235, 225, 240), 2, cv2.LINE_AA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)


class Matte:
    def __init__(self, bg: str, size: tuple[int, int], every: int = 2):
        if not MODEL.exists():
            raise SystemExit(f"Missing {MODEL}; download it from {MODEL_URL}")
        self.seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(MODEL)),
            running_mode=vision.RunningMode.VIDEO, output_confidence_masks=True))
        colors = {"white": "#ffffff", "black": "#000000", "green": "#00b140"}
        bg = colors.get(bg.lower(), bg)
        self.mode = bg if bg in ("blur", "none") else "color" if re.fullmatch(r"#[0-9a-fA-F]{6}", bg) else "image"
        self.image = None
        if self.mode == "color":
            r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
            self.image = np.full((size[1], size[0], 3), (b, g, r), np.uint8)
        elif self.mode == "image":
            img = cv2.imread(bg)
            if img is None:
                raise SystemExit(f"Cannot read background image {bg!r}")
            self.image = _cover(img, size)
        self.prev = None
        self.every = max(every, 1)
        self.n = 0
        self.t0 = time.monotonic()

    def apply(self, frame: np.ndarray) -> np.ndarray:
        self.n += 1
        if self.prev is None or self.n % self.every == 0:
            rgb = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            ts = int((time.monotonic() - self.t0) * 1000)
            mask = self.seg.segment_for_video(rgb, ts).confidence_masks[0].numpy_view()
            mask = cv2.GaussianBlur(mask, (7, 7), 0)
            self.prev = mask if self.prev is None else 0.6 * mask + 0.4 * self.prev
        alpha = self.prev[..., None]
        if self.mode == "none":
            out = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
            out[..., 3] = (self.prev * 255).astype(np.uint8)
            return out
        back = cv2.GaussianBlur(frame, (0, 0), 15) if self.mode == "blur" else self.image
        mixed = (frame * alpha + back * (1 - alpha)).astype(np.uint8)
        return cv2.cvtColor(mixed, cv2.COLOR_BGR2BGRA)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--device", default="Integrated Webcam")
    p.add_argument("--bg", default="white")
    p.add_argument("--delay", type=float, default=8.0)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--size", default="480x360")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--placeholder", help="image shown while the camera is off")
    p.add_argument("--start-on", action="store_true", help="start with the camera on")
    p.add_argument("--seg-every", type=int, default=2, help="run the background model on every Nth frame")
    p.add_argument("--zoom", type=float, default=1.0, help="digital zoom, 1.0 to 3.0")
    args = p.parse_args()
    w, h = (int(v) for v in args.size.split("x"))

    matte = Matte(args.bg, (w, h), args.seg_every)
    placeholder = _placeholder(args.placeholder, (w, h))
    buf: collections.deque[tuple[float, np.ndarray]] = collections.deque()
    lock = threading.Lock()
    want = threading.Event()
    if args.start_on:
        want.set()

    def control() -> None:
        for line in sys.stdin:
            cmd = line.strip().lower()
            if cmd == "on":
                want.set()
            elif cmd == "off":
                want.clear()
            elif cmd.startswith("delay "):
                args.delay = float(cmd.split()[1])
            elif cmd.startswith("zoom "):
                args.zoom = min(max(float(cmd.split()[1]), 1.0), 3.0)

    def capture() -> None:
        cap = None
        misses = 0
        while True:
            if not want.is_set():
                if cap is not None:
                    cap.release()
                    cap = None
                    with lock:
                        buf.clear()
                time.sleep(0.1)
                continue
            if cap is None:
                try:
                    cap = _open_camera(args.device, 640, 480)
                    misses = 0
                except OSError as e:
                    print(f"camfx: {e}; showing placeholder, retrying in 3s", flush=True)
                    time.sleep(3)
                    continue
            ok, frame = cap.read()
            if not ok:
                misses += 1
                if misses > 30:
                    print("camfx: camera stopped sending frames; reopening", flush=True)
                    cap.release()
                    cap = None
                    with lock:
                        buf.clear()
                time.sleep(0.05)
                continue
            misses = 0
            out = matte.apply(_cover(_zoom(frame, args.zoom), (w, h)))
            now = time.monotonic()
            with lock:
                buf.append((now, out))
                while len(buf) > 1 and buf[1][0] <= now - args.delay:
                    buf.popleft()

    threading.Thread(target=control, daemon=True).start()
    threading.Thread(target=capture, daemon=True).start()
    print(f"camfx: {args.device} -> 127.0.0.1:{args.port}, bg={args.bg}, delay={args.delay}s", flush=True)
    step = 1 / args.fps
    while True:
        try:
            sock = socket.create_connection(("127.0.0.1", args.port), timeout=2)
        except OSError:
            time.sleep(0.5)
            continue
        sock.settimeout(None)
        nxt = time.monotonic()
        try:
            while True:
                now = time.monotonic()
                with lock:
                    fresh = buf and now - args.delay - 1 <= buf[0][0] <= now - args.delay
                    frame = buf[0][1] if fresh and want.is_set() else placeholder
                sock.sendall(frame.tobytes())
                nxt += step
                lag = nxt - time.monotonic()
                if lag > 0:
                    time.sleep(lag)
                elif lag < -1:
                    nxt = time.monotonic()
        except OSError:
            sock.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
