from types import SimpleNamespace

import pytest

from clipper.publish.gitops import GitError, commit_queue


def make_run(staged=(), has_changes=True, push_codes=(0,), commit_code=0):
    calls = []
    pushes = list(push_codes)

    def run(args, cwd):
        calls.append(args[1:])
        verb = args[1:3]
        if verb == ["diff", "--cached"] and "--name-only" in args:
            return SimpleNamespace(returncode=0, stdout="\n".join(staged), stderr="")
        if verb == ["diff", "--cached"] and "--quiet" in args:
            return SimpleNamespace(returncode=1 if has_changes else 0, stdout="", stderr="")
        if args[1] == "commit":
            return SimpleNamespace(returncode=commit_code, stdout="", stderr="commit failed")
        if args[1] == "push":
            return SimpleNamespace(returncode=pushes.pop(0) if pushes else 0, stdout="", stderr="rejected")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return run, calls


def test_commits_and_pushes_queue_changes(tmp_path):
    run, calls = make_run()
    assert commit_queue("queue: add vid", cwd=tmp_path, run=run) is True
    assert ["add", "queue"] in calls
    assert ["commit", "-m", "queue: add vid"] in calls
    assert ["push"] in calls


def test_nothing_to_commit_returns_false(tmp_path):
    run, calls = make_run(has_changes=False)
    assert commit_queue("queue: nothing", cwd=tmp_path, run=run) is False
    assert not any(c[0] in ("commit", "push") for c in calls)


def test_refuses_when_unrelated_files_are_staged(tmp_path):
    run, calls = make_run(staged=("queue/pending/a.json", "README.md"))
    with pytest.raises(GitError, match="README.md"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run)
    assert not any(c[0] == "commit" for c in calls)


def test_push_rejection_pulls_with_rebase_and_retries(tmp_path):
    run, calls = make_run(push_codes=(1, 0))
    assert commit_queue("queue: add vid", cwd=tmp_path, run=run) is True
    assert ["pull", "--rebase"] in calls


def test_push_that_keeps_failing_raises(tmp_path):
    run, _ = make_run(push_codes=(1, 1))
    with pytest.raises(GitError, match="push"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run)
