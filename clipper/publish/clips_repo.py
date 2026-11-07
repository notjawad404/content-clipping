"""Store rendered clips as Release assets in the public clips repo, using the `gh` CLI.

Locally `gh` uses your login; in GitHub Actions it uses the GH_TOKEN environment variable.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from clipper.publish import PublishError


class RepoError(PublishError):
    pass


def default_run(args: list[str]):
    return subprocess.run(args, capture_output=True, text=True)


def _check(proc, what: str) -> str:
    if proc.returncode != 0:
        raise RepoError(f"{what} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout


def ensure_release(repo: str, tag: str, run=default_run) -> None:
    if run(["gh", "release", "view", tag, "-R", repo]).returncode == 0:
        return
    _check(run(["gh", "release", "create", tag, "-R", repo, "--title", tag,
                "--notes", "Clips queued for Instagram posting"]), "create release")


def upload_asset(repo: str, tag: str, path: str | Path, run=default_run) -> tuple[str, int]:
    ensure_release(repo, tag, run)
    _check(run(["gh", "release", "upload", tag, str(path), "-R", repo, "--clobber"]), "upload asset")
    release = json.loads(_check(run(["gh", "api", f"repos/{repo}/releases/tags/{tag}"]), "read release"))
    name = Path(path).name
    for asset in release.get("assets", []):
        if asset["name"] == name:
            return asset["browser_download_url"], int(asset["id"])
    raise RepoError(f"uploaded asset {name} not found in release {tag}")


def delete_asset(repo: str, asset_id: int, run=default_run) -> None:
    _check(run(["gh", "api", "-X", "DELETE", f"repos/{repo}/releases/assets/{asset_id}"]), "delete asset")
