"""List your Publer workspaces and social accounts, to fill PUBLER_WORKSPACE_ID and publer_accounts.

Usage: put PUBLER_API_KEY (and optionally PUBLER_WORKSPACE_ID) in .env, then run
    python scripts/publer_accounts.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clipper.publish import PublishError  # noqa: E402
from clipper.publish.post_next import _load_dotenv  # noqa: E402
from clipper.publish.publer import PublerClient  # noqa: E402


def main() -> int:
    _load_dotenv()
    key = os.environ.get("PUBLER_API_KEY")
    if not key:
        print("error: set PUBLER_API_KEY in .env first")
        return 2
    workspace = os.environ.get("PUBLER_WORKSPACE_ID")
    try:
        print("Workspaces:")
        for ws in PublerClient(key, None).workspaces():
            print(f"  {ws.get('id')}  {ws.get('name')}")
        if not workspace:
            print("\nSet PUBLER_WORKSPACE_ID in .env to one of these and run again to list its accounts.")
            return 0
        print(f"\nAccounts in workspace {workspace}:")
        for account in PublerClient(key, workspace).accounts():
            print(f"  {account.get('id')}  {account.get('provider'):<10} {account.get('name')}")
    except PublishError as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
