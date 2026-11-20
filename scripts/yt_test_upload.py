"""Upload one clip to YouTube as PRIVATE to prove the credentials and channel are right (Step 5).

    YT_REFRESH_TOKEN=... python3 scripts/yt_test_upload.py output/<id>/clip_01.mp4 [--client ~/secrets/yt_client.json]

Client id/secret come from the Desktop client JSON; the refresh token comes from the environment.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper.publish import PublishError  # noqa: E402
from clipper.publish.youtube import YouTubeClient  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private test upload to YouTube")
    parser.add_argument("video", type=Path)
    parser.add_argument("--client", default="~/secrets/yt_client.json")
    args = parser.parse_args(argv)
    refresh = os.environ.get("YT_REFRESH_TOKEN")
    if not refresh:
        print("error: set the YT_REFRESH_TOKEN environment variable")
        return 2
    try:
        client = json.loads(Path(args.client).expanduser().read_text(encoding="utf-8"))["installed"]
        video = args.video.read_bytes()
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}")
        return 2
    try:
        video_id = YouTubeClient(client["client_id"], client["client_secret"], refresh).upload(
            video, "Test upload #Shorts", "Pipeline test, private.", privacy="private")
    except PublishError as exc:
        print(f"error: {type(exc).__name__}: {exc}")
        return 1
    print(f"uploaded (private): https://studio.youtube.com/video/{video_id}/edit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
