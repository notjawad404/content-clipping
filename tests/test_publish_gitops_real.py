"""commit_queue against real git repositories, all inside tmp_path (a bare remote and two clones)."""
import shutil
import subprocess
from pathlib import Path

import pytest

from clipper.publish.gitops import commit_queue

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert done.returncode == 0, f"git {' '.join(args)} failed: {done.stderr}"
    return done.stdout


def configure(repo: Path) -> None:
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """(remote, clone_a, clone_b): both clones start level with the remote's master."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-b", "master", str(remote))
    seed = tmp_path / "seed"
    git(tmp_path, "init", "-b", "master", str(seed))
    configure(seed)
    (seed / "README.md").write_text("original\n")
    (seed / "queue").mkdir()
    (seed / "queue" / ".gitkeep").write_text("")  # the real repo tracks queue/.gitkeep, so `git add queue` works
    git(seed, "add", "README.md", "queue")
    git(seed, "commit", "-m", "seed")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "master")
    clones = []
    for name in ("a", "b"):
        clone = tmp_path / name
        git(tmp_path, "clone", "-b", "master", str(remote), str(clone))
        configure(clone)
        clones.append(clone)
    return remote, clones[0], clones[1]


def remote_subjects(remote: Path) -> list[str]:
    return git(remote, "log", "--format=%s", "master").splitlines()


def test_behind_clone_with_dirty_tracked_file_commits_and_pushes_the_queue_only(repos):
    remote, a, b = repos
    (b / "other.txt").write_text("from b\n")
    git(b, "add", "other.txt")
    git(b, "commit", "-m", "bot commit")
    git(b, "push")
    (a / "README.md").write_text("edited locally, not committed\n")
    (a / "queue" / "pending").mkdir()
    (a / "queue" / "pending" / "x.json").write_text("{}\n")

    assert commit_queue("queue: add x", cwd=a, branch="master") is True

    assert remote_subjects(remote)[:3] == ["queue: add x", "bot commit", "seed"]
    assert git(remote, "show", "master:README.md") == "original\n"
    assert git(remote, "show", "master:queue/pending/x.json") == "{}\n"
    assert (a / "README.md").read_text() == "edited locally, not committed\n"
    assert " M README.md" in git(a, "status", "--porcelain").splitlines()
    assert git(a, "diff", "--name-only", "HEAD~1", "HEAD").split() == ["queue/pending/x.json"]


def test_unpushed_local_commit_with_nothing_new_to_commit_is_pushed(repos):
    remote, a, _ = repos
    (a / "queue" / "pending").mkdir()
    (a / "queue" / "pending" / "y.json").write_text("{}\n")
    git(a, "add", "queue")
    git(a, "commit", "-m", "queue: add y (not pushed)")
    assert remote_subjects(remote) == ["seed"]

    assert commit_queue("queue: retry", cwd=a, branch="master") is True

    assert remote_subjects(remote) == ["queue: add y (not pushed)", "seed"]


def test_nothing_to_commit_and_not_ahead_returns_false(repos):
    remote, a, _ = repos
    assert commit_queue("queue: nothing", cwd=a, branch="master") is False
    assert remote_subjects(remote) == ["seed"]


def test_wrong_branch_is_refused_and_nothing_is_committed(repos):
    remote, a, _ = repos
    git(a, "checkout", "-b", "feature/x")
    (a / "queue" / "pending").mkdir()
    (a / "queue" / "pending" / "z.json").write_text("{}\n")
    with pytest.raises(Exception, match="you are on 'feature/x' but the queue lives on 'master'"):
        commit_queue("queue: add z", cwd=a, branch="master")
    assert remote_subjects(remote) == ["seed"]
    assert git(a, "log", "--format=%s").splitlines() == ["seed"]
    assert git(a, "diff", "--cached", "--name-only") == ""
