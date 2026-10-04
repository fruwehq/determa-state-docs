"""Regression checks for publication safety and candidate source provenance."""

from pathlib import Path
import json
import sys

import pytest
from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_latest  # noqa: E402
import check_publication_hold  # noqa: E402
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


def hold_fixture(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "docs.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text((ROOT / ".github/workflows/docs.yml").read_text())
    (tmp_path / "Makefile").write_text((ROOT / "Makefile").read_text())
    (tmp_path / "scripts").mkdir()
    return workflow


def test_pages_hold_covers_every_workflow_trigger(tmp_path):
    hold_fixture(tmp_path)
    check_publication_hold.check_hold(tmp_path)


@pytest.mark.parametrize("attack", [
    "second_workflow",
    "local_action",
    "top_level_write_permission",
    "direct_pages_api",
    "indirect_gh_deploy",
    "indirect_script_pages_api",
])
def test_publication_hold_rejects_other_paths(tmp_path, attack):
    workflow = hold_fixture(tmp_path)
    if attack == "second_workflow":
        (workflow.parent / "deploy.yml").write_text("jobs: {}\n")
    elif attack == "local_action":
        action = tmp_path / ".github/actions/deploy/action.yml"
        action.parent.mkdir(parents=True)
        action.write_text("runs:\n  using: composite\n")
    elif attack == "top_level_write_permission":
        workflow.write_text(workflow.read_text().replace("contents: read\n", "pages: write\n", 1))
    elif attack == "direct_pages_api":
        workflow.write_text(workflow.read_text().replace("run: make check", "run: gh api repos/x/y/pages --method POST"))
    elif attack == "indirect_gh_deploy":
        makefile = tmp_path / "Makefile"
        makefile.write_text(makefile.read_text().replace("mkdocs build --strict", "mkdocs gh-deploy"))
    else:
        (tmp_path / "scripts" / "validate.py").write_text('import os\nos.system("gh api repos/x/y/pages")\n')
    with pytest.raises(ValueError):
        check_publication_hold.check_hold(tmp_path)


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


@pytest.mark.parametrize("dependency", [
    '"=0.3.0"',
    '{ git = "https://github.com/fruwehq/determa-state-rust", tag = "v0.3.0" }',
    '{ git = "https://github.com/fruwehq/determa-state-rust", branch = "main" }',
    '{ git = "https://github.com/attacker/determa-state-rust", rev = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }',
    '{ git = "https://github.com/fruwehq/determa-state-rust", rev = "abcdef0" }',
])
def test_candidate_cargo_rejects_unpinned_or_nonpublic_source(tmp_path, dependency):
    manifest = tmp_path / "Cargo.toml"
    manifest.write_text(f"[dependencies]\ndeterma-state = {dependency}\n")
    with pytest.raises(ValueError, match="exact public git"):
        validate.check_candidate_cargo_dependencies([manifest], "a" * 40)


def test_candidate_cargo_checks_every_extracted_manifest(tmp_path):
    valid = tmp_path / "one" / "Cargo.toml"
    stale = tmp_path / "two" / "Cargo.toml"
    for path in (valid, stale):
        path.parent.mkdir()
    valid.write_text(
        '[dependencies]\ndeterma-state = { git = "https://github.com/fruwehq/determa-state-rust", '
        'rev = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }\n'
    )
    stale.write_text('[dependencies]\ndeterma-state = "=0.3.0"\n')
    with pytest.raises(ValueError, match="exact public git"):
        validate.check_candidate_cargo_dependencies([valid, stale], "a" * 40)
    stale.write_text(valid.read_text())
    validate.check_candidate_cargo_dependencies([valid, stale], "a" * 40)


def test_candidate_cargo_rejects_renamed_dependency(tmp_path):
    manifest = tmp_path / "Cargo.toml"
    manifest.write_text(
        '[dependencies]\nengine = { package = "determa-state", '
        'git = "https://github.com/fruwehq/determa-state-rust", '
        'rev = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }\n'
    )
    with pytest.raises(ValueError, match="exact public git"):
        validate.check_candidate_cargo_dependencies([manifest], "a" * 40)


def test_candidate_python_rejects_stale_installed_bytes(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source_file = source / "src/determa/state/engine.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("pinned bytes\n")
    site = tmp_path / "site"
    installed_file = site / "determa/state/engine.py"
    installed_file.parent.mkdir(parents=True)
    installed_file.write_text("stale bytes\n")
    commit = "a" * 40

    class Distribution:
        files = [Path("determa/state/engine.py")]

        def read_text(self, name):
            assert name == "direct_url.json"
            return json.dumps({
                "url": "https://github.com/fruwehq/determa-state-python.git",
                "vcs_info": {"vcs": "git", "commit_id": commit},
            })

        def locate_file(self, path):
            return site / path

    monkeypatch.setattr(validate.importlib.metadata, "distribution", lambda name: Distribution())
    monkeypatch.setattr(validate, "run", lambda *args, **kwargs: "src/determa/state/engine.py")
    with pytest.raises(ValueError, match="installed content differs"):
        validate.check_candidate_python_install(source, commit)
    installed_file.write_bytes(source_file.read_bytes())
    validate.check_candidate_python_install(source, commit)


def test_candidate_python_rejects_directory_only_provenance(tmp_path, monkeypatch):
    class Distribution:
        def read_text(self, name):
            return json.dumps({"url": tmp_path.as_uri(), "dir_info": {}})

    monkeypatch.setattr(validate.importlib.metadata, "distribution", lambda name: Distribution())
    with pytest.raises(ValueError, match="not built from the pinned commit"):
        validate.check_candidate_python_install(tmp_path, "a" * 40)
