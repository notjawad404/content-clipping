"""Post one clip to TikTok as SELF_ONLY (private) to prove the credentials and account are right.

    python scripts/tiktok_test_upload.py output/<id>/clip_01.mp4

Reads TT_CLIENT_KEY, TT_CLIENT_SECRET and TT_REFRESH_TOKEN from .env.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper.publish import PublishError  # noqa: E402
from clipper.publish.tiktok import TikTokClient  # noqa: E402
from scripts.tiktok_auth import read_env  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private test post to TikTok")
    parser.add_argument("video", type=Path)
    args = parser.parse_args(argv)
    env = read_env()
    missing = [k for k in ("TT_CLIENT_KEY", "TT_CLIENT_SECRET", "TT_REFRESH_TOKEN") if not env.get(k)]
    if missing:
        print(f"error: missing in .env: {', '.join(missing)}")
        return 2
    try:
        video = args.video.read_bytes()
    except OSError as exc:
        print(f"error: {exc}")
        return 2
    client = TikTokClient(env["TT_CLIENT_KEY"], env["TT_CLIENT_SECRET"], env["TT_REFRESH_TOKEN"])
    try:
        info = client.creator_info()
        print(f"account: @{info.get('creator_username')}; allowed privacy: {info.get('privacy_level_options')}")
        publish_id = client.upload(video, "Pipeline test #test", "SELF_ONLY")
        status = client.wait(publish_id, 5, 300)
    except PublishError as exc:
        print(f"error: {type(exc).__name__}: {exc}")
        return 1
    print(f"posted (private): publish id {publish_id}, status {status.get('status')}. Check your TikTok profile.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
