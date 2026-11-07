from types import SimpleNamespace

import pytest

from clipper.publish import gitops
from clipper.publish.gitops import GitError, commit_queue


def make_run(staged=(), has_changes=True, push_codes=(0,), commit_code=0, probe_code=0,
             add_code=0, quiet_code=None, pull_codes=(0,), push_stderr=("rejected", "rejected"),
             ahead="0", rev_list_code=0, current_branch="master", branch_code=0):
    calls = []
    pushes = list(zip(push_codes, push_stderr))
    pulls = list(pull_codes)

    def run(args, cwd):
        calls.append(args[1:])
        verb = args[1:3]
        if verb == ["diff", "--cached"] and "--name-only" in args:
            return SimpleNamespace(returncode=probe_code, stdout="\n".join(staged), stderr="probe broke")
        if verb == ["diff", "--cached"] and "--quiet" in args:
            code = quiet_code if quiet_code is not None else (1 if has_changes else 0)
            return SimpleNamespace(returncode=code, stdout="", stderr="diff broke")
        if args[1] == "rev-parse":
            return SimpleNamespace(returncode=branch_code, stdout=current_branch + "\n", stderr="not a repo")
        if args[1] == "rev-list":
            return SimpleNamespace(returncode=rev_list_code, stdout=ahead, stderr="no upstream")
        if args[1] == "add":
            return SimpleNamespace(returncode=add_code, stdout="", stderr="add broke")
        if args[1] == "commit":
            return SimpleNamespace(returncode=commit_code, stdout="", stderr="commit failed")
        if args[1] == "push":
            code, err = pushes.pop(0) if pushes else (0, "")
            return SimpleNamespace(returncode=code, stdout="", stderr=err)
        if verb == ["pull", "--rebase"] and "--autostash" in args:
            return SimpleNamespace(returncode=pulls.pop(0) if pulls else 0, stdout="", stderr="conflict")
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
    assert ["pull", "--rebase", "--autostash"] in calls


def test_push_that_keeps_failing_raises(tmp_path):
    run, _ = make_run(push_codes=(1, 1))
    with pytest.raises(GitError, match="push"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run)


def test_missing_git_binary_raises_git_error(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(gitops.subprocess, "run", missing)
    with pytest.raises(GitError, match="could not run git: FileNotFoundError"):
        commit_queue("queue: add vid", cwd=tmp_path)


def test_staged_probe_failure_raises_and_commits_nothing(tmp_path):
    run, calls = make_run(probe_code=128)
    with pytest.raises(GitError, match="git diff failed"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run)
    assert not any(c[0] in ("add", "commit", "push") for c in calls)


def test_git_add_failure_raises_and_commits_nothing(tmp_path):
    run, calls = make_run(add_code=1)
    with pytest.raises(GitError, match="git add failed"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run)
    assert not any(c[0] in ("commit", "push") for c in calls)


def test_diff_quiet_error_is_not_read_as_no_changes(tmp_path):
    run, calls = make_run(quiet_code=128)
    with pytest.raises(GitError, match="git diff failed"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run)
    assert not any(c[0] in ("commit", "push") for c in calls)


def test_pull_failure_aborts_rebase_and_raises(tmp_path):
    run, calls = make_run(push_codes=(1, 0), pull_codes=(1,))
    with pytest.raises(GitError, match="git pull --rebase failed"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run)
    assert ["rebase", "--abort"] in calls
    assert ["push"] in calls and calls.count(["push"]) == 1


def test_second_push_failure_includes_push_stderr(tmp_path):
    run, calls = make_run(push_codes=(1, 1), push_stderr=("net down", "remote rejected"))
    with pytest.raises(GitError, match="git push failed: remote rejected"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run)
    assert calls.count(["pull", "--rebase", "--autostash"]) == 1


def test_unpushed_commit_with_nothing_new_to_commit_is_pushed(tmp_path):
    run, calls = make_run(has_changes=False, ahead="1\n")
    assert commit_queue("queue: retry", cwd=tmp_path, run=run) is True
    assert ["rev-list", "--count", "@{u}..HEAD"] in calls
    assert ["push"] in calls and not any(c[0] == "commit" for c in calls)


def test_nothing_to_commit_and_nothing_unpushed_does_not_push(tmp_path):
    run, calls = make_run(has_changes=False, ahead="0\n")
    assert commit_queue("queue: retry", cwd=tmp_path, run=run) is False
    assert ["rev-list", "--count", "@{u}..HEAD"] in calls
    assert not any(c[0] in ("commit", "push") for c in calls)


def test_unpushed_check_failure_raises(tmp_path):
    run, calls = make_run(has_changes=False, rev_list_code=128)
    with pytest.raises(GitError, match="cannot tell whether there are unpushed commits: no upstream"):
        commit_queue("queue: retry", cwd=tmp_path, run=run)
    assert not any(c[0] in ("commit", "push") for c in calls)


def test_unpushed_check_with_garbage_output_raises(tmp_path):
    run, _ = make_run(has_changes=False, ahead="fatal?")
    with pytest.raises(GitError, match="cannot tell whether there are unpushed commits"):
        commit_queue("queue: retry", cwd=tmp_path, run=run)


def test_retry_push_rejection_pulls_with_rebase_and_retries(tmp_path):
    run, calls = make_run(has_changes=False, ahead="2", push_codes=(1, 0))
    assert commit_queue("queue: retry", cwd=tmp_path, run=run) is True
    assert ["pull", "--rebase", "--autostash"] in calls and calls.count(["push"]) == 2


def test_retry_pull_failure_aborts_rebase_and_raises(tmp_path):
    run, calls = make_run(has_changes=False, ahead="2", push_codes=(1, 0), pull_codes=(1,))
    with pytest.raises(GitError, match="git pull --rebase failed"):
        commit_queue("queue: retry", cwd=tmp_path, run=run)
    assert ["rebase", "--abort"] in calls and calls.count(["push"]) == 1


def test_retry_second_push_failure_raises(tmp_path):
    run, _ = make_run(has_changes=False, ahead="2", push_codes=(1, 1), push_stderr=("net", "remote rejected"))
    with pytest.raises(GitError, match="git push failed: remote rejected"):
        commit_queue("queue: retry", cwd=tmp_path, run=run)


def test_unrelated_staged_files_still_refuse_before_the_unpushed_check(tmp_path):
    run, calls = make_run(staged=("README.md",), has_changes=False, ahead="3")
    with pytest.raises(GitError, match="README.md"):
        commit_queue("queue: retry", cwd=tmp_path, run=run)
    assert not any(c[0] in ("rev-list", "push") for c in calls)


def test_branch_guard_runs_first_and_passes_on_the_right_branch(tmp_path):
    run, calls = make_run()
    assert commit_queue("queue: add vid", cwd=tmp_path, run=run, branch="master") is True
    assert calls[0] == ["rev-parse", "--abbrev-ref", "HEAD"]


def test_wrong_branch_is_refused_before_anything_else(tmp_path):
    run, calls = make_run(current_branch="feature/clipper-v1")
    with pytest.raises(GitError) as caught:
        commit_queue("queue: add vid", cwd=tmp_path, run=run, branch="master")
    assert str(caught.value) == ("refusing to commit: you are on 'feature/clipper-v1' but the queue lives on "
                                 "'master'; switch with `git checkout master`")
    assert calls == [["rev-parse", "--abbrev-ref", "HEAD"]]


def test_branch_lookup_failure_raises_and_changes_nothing(tmp_path):
    run, calls = make_run(branch_code=128)
    with pytest.raises(GitError, match="cannot determine the current branch: not a repo"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run, branch="master")
    assert calls == [["rev-parse", "--abbrev-ref", "HEAD"]]


def test_detached_head_is_refused(tmp_path):
    run, calls = make_run(current_branch="HEAD")
    with pytest.raises(GitError, match="'HEAD'"):
        commit_queue("queue: add vid", cwd=tmp_path, run=run, branch="master")
    assert not any(c[0] in ("add", "commit", "push") for c in calls)


def test_no_branch_argument_skips_the_guard(tmp_path):
    run, calls = make_run(current_branch="anything")
    assert commit_queue("queue: add vid", cwd=tmp_path, run=run) is True
    assert not any(c[0] == "rev-parse" for c in calls)
