import yaml

from clipper.env import PROJECT_ROOT

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "post-next.yml"


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def triggers(doc: dict) -> dict:
    return doc.get("on") or doc.get(True)  # PyYAML parses a bare `on:` key as boolean True


def test_post_next_workflow_shape():
    doc = load()
    assert doc["concurrency"] == {"group": "ig-post", "cancel-in-progress": False}
    assert doc["permissions"] == {"contents": "write"}
    assert doc["jobs"]["post"]["runs-on"] == "ubuntu-latest"
    dispatch = triggers(doc)["workflow_dispatch"]
    assert dispatch["inputs"]["dry_run"]["default"] is True


def test_post_next_workflow_uses_the_light_entry_point_and_the_two_secrets():
    text = WORKFLOW.read_text()
    assert "python -m clipper.publish.post_next" in text
    assert "secrets.IG_ACCESS_TOKEN" in text and "secrets.CLIPS_REPO_TOKEN" in text
    assert "uv sync" not in text and "pip install ." not in text


def test_post_next_workflow_wiring_of_secrets_and_dry_run():
    doc = load()
    steps = doc["jobs"]["post"]["steps"]
    last = steps[-1]
    assert last["env"]["IG_ACCESS_TOKEN"] == "${{ secrets.IG_ACCESS_TOKEN }}"
    assert last["env"]["GH_TOKEN"] == "${{ secrets.CLIPS_REPO_TOKEN || github.token }}"
    assert last["env"]["DRY_RUN"] == "${{ github.event_name == 'workflow_dispatch' && inputs.dry_run }}"
    for step in steps[:-1]:
        env_text = str(step.get("env", {}))
        assert "secrets." not in env_text and "IG_ACCESS_TOKEN" not in env_text and "GH_TOKEN" not in env_text
    script = last["run"]
    assert 'if [ "$DRY_RUN" = "true" ]; then' in script
    live_branch = script.split("else")[1]
    assert "--dry-run" not in live_branch and "python -m clipper.publish.post_next" in live_branch
    assert script.split("else")[0].count("--dry-run") == 1


def test_post_next_is_scheduled_three_times_a_day():
    schedule = triggers(load())["schedule"]
    assert schedule == [{"cron": "41 19 * * *"}, {"cron": "41 1 * * *"}]
