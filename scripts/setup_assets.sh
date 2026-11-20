#!/usr/bin/env bash
# Downloads the caption font and face model, and synthesizes a whoosh sound effect.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FFMPEG="${CLIPPER_FFMPEG_DIR:-/opt/homebrew/opt/ffmpeg-full/bin}/ffmpeg"
[ -x "$FFMPEG" ] || FFMPEG="$(command -v ffmpeg)"
mkdir -p "$ROOT/assets/fonts" "$ROOT/assets/sfx" "$ROOT/models"

FONT="$ROOT/assets/fonts/Montserrat-Black.ttf"
if [ ! -s "$FONT" ]; then
  curl -fsSL -o "$FONT" "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Black.ttf"
  curl -fsSL -o "$ROOT/assets/fonts/OFL.txt" "https://github.com/JulietaUla/Montserrat/raw/master/OFL.txt"
fi

MODEL="$ROOT/models/face_landmarker.task"
if [ ! -s "$MODEL" ]; then
  curl -fsSL -o "$MODEL" "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
fi

# Synthesized pink-noise whoosh: no licensing questions. Replace with a Mixkit/Pixabay file if preferred.
WHOOSH="$ROOT/assets/sfx/whoosh.wav"
if [ ! -s "$WHOOSH" ]; then
  "$FFMPEG" -hide_banner -loglevel error -y -f lavfi -i "anoisesrc=d=0.45:c=pink:a=0.6" \
    -af "highpass=f=250,lowpass=f=6000,afade=t=in:d=0.18,afade=t=out:st=0.2:d=0.25,volume=0.9" \
    -ar 48000 -ac 2 "$WHOOSH"
fi
echo "Assets ready: $FONT, $MODEL, $WHOOSH"
