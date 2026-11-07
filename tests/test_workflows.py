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
