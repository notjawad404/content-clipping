"""Copy every queued and posted clip into uploads/<video_id>/ with its captions, for manual uploads.

    python scripts/sync_uploads.py

Uses the local render in output/ when present, otherwise the GitHub Release file. Run `git pull` first so the
queue (and its titles) is current. Clips with neither are listed as missing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper.publish import queue  # noqa: E402
from clipper.publish.export import UPLOADS_DIR, export_entry  # noqa: E402


def main() -> int:
    copied, missing = 0, []
    for state in ("pending", "posted"):
        for entry in queue.load_all(queue.QUEUE_ROOT, state):
            if export_entry(entry):
                copied += 1
            else:
                missing.append(entry["id"])
    print(f"{copied} clips in {UPLOADS_DIR}")
    if missing:
        print(f"no video available for {len(missing)}: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
