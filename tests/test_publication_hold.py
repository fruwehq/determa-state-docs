"""Regression checks for publication safety and candidate source provenance."""

from pathlib import Path
import sys

import pytest
from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_latest  # noqa: E402
import source_lock  # noqa: E402
import validate  # noqa: E402


def yaml():
    loader = YAML(typ="safe", pure=True)
    loader.version = (1, 2)
    return loader


def candidate_lock():
    lock = source_lock.load_lock()
    lock["lifecycle"] = "candidate"
    lock["state_version"] = "0.3.0"
    for row in lock["repositories"].values():
        del row["tag"]
    return lock


def save_lock(tmp_path, lock):
    path = tmp_path / "sources.lock.yaml"
    writer = YAML()
    with path.open("w") as stream:
        writer.dump(lock, stream)
    return path


def test_pages_hold_covers_every_workflow_trigger():
    workflow = yaml().load((ROOT / ".github/workflows/docs.yml").read_text())
    assert set(workflow["on"]) == {"pull_request", "push", "schedule", "workflow_dispatch"}
    assert set(workflow["jobs"]) == {"validate"}
    jobs = workflow["jobs"]
    assert all("pages" not in str(key).lower() and "id-token" != key
               for job in jobs.values() for key in job.get("permissions", {}))
    assert all("pages" not in step.get("uses", "").lower()
               for job in jobs.values() for step in job["steps"])
    assert any(step.get("run") == "make check" for step in jobs["validate"]["steps"])


@pytest.mark.parametrize("mutation", [
    lambda lock: lock["repositories"]["python"].update(tag="v0.3.0"),
    lambda lock: lock["repositories"]["rust"].update(commit="main"),
    lambda lock: lock.update(lifecycle="published"),
    lambda lock: lock["repositories"]["specification"].update(repository="local/spec"),
])
def test_candidate_metadata_fails_closed(tmp_path, mutation):
    lock = candidate_lock()
    mutation(lock)
    with pytest.raises(ValueError):
        source_lock.load_lock(save_lock(tmp_path, lock))


def test_released_tag_must_match_version(tmp_path):
    lock = source_lock.load_lock()
    lock["repositories"]["rust"]["tag"] = "v0.3.0"
    with pytest.raises(ValueError, match="release tag"):
        source_lock.load_lock(save_lock(tmp_path, lock))


def test_released_tag_pointing_elsewhere_fails(monkeypatch):
    monkeypatch.setattr(check_latest, "github_json", lambda url, token: {"sha": "0" * 40})
    with pytest.raises(SystemExit, match="does not resolve to pinned commit"):
        check_latest.check_released_freshness(source_lock.load_lock(), (0, 2, 0), None)


def test_source_links_use_commit_only_during_candidate(tmp_path, monkeypatch):
    path = save_lock(tmp_path, candidate_lock())
    monkeypatch.setattr(validate, "load_lock", lambda: source_lock.load_lock(path))
    assert validate.source_ref("specification") == candidate_lock()["repositories"]["specification"]["commit"]
    monkeypatch.setattr(validate, "load_lock", source_lock.load_lock)
    assert validate.source_ref("specification") == "v0.2.0"


def test_candidate_checks_public_commits_without_requiring_unreleased_tags(tmp_path, monkeypatch):
    lock = candidate_lock()
    save_lock(tmp_path, lock)
    (tmp_path / "coverage.yaml").write_text(
        "specification: []\nconformance: []\nexecution_checkpoint_profile: []\n"
    )
    monkeypatch.setattr(check_latest, "ROOT", tmp_path)
    monkeypatch.setattr(source_lock, "ROOT", tmp_path)
    # The default argument was bound at function definition; bind the fixture explicitly.
    monkeypatch.setattr(check_latest, "load_lock", lambda: source_lock.load_lock(tmp_path / "sources.lock.yaml"))
    queried = []

    def github_json(url, token):
        queried.append(url)
        assert "/commits/" in url
        return {"sha": url.rsplit("/", 1)[1]}

    monkeypatch.setattr(check_latest, "github_json", github_json)
    check_latest.main()
    assert len(queried) == 4


def test_candidate_rejects_nonpublic_or_mismatched_commit(tmp_path, monkeypatch):
    save_lock(tmp_path, candidate_lock())
    (tmp_path / "coverage.yaml").write_text(
        "specification: []\nconformance: []\nexecution_checkpoint_profile: []\n"
    )
    monkeypatch.setattr(check_latest, "ROOT", tmp_path)
    monkeypatch.setattr(check_latest, "load_lock", lambda: source_lock.load_lock(tmp_path / "sources.lock.yaml"))
    monkeypatch.setattr(check_latest, "github_json", lambda url, token: {"sha": "0" * 40})
    with pytest.raises(SystemExit, match="not an exact public commit"):
        check_latest.main()
