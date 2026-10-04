"""Closed metadata for released tags and unreleased, immutable candidate commits."""

from __future__ import annotations

from pathlib import Path
import re

from ruamel.yaml import YAML


ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = ("specification", "conformance", "python", "rust")
HEX_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
VERSION = re.compile(r"0|[1-9][0-9]*")


def load_lock(path: Path = ROOT / "sources.lock.yaml") -> dict:
    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    lock = yaml.load(path.read_text())
    if not isinstance(lock, dict) or set(lock) != {"state_version", "lifecycle", "repositories"}:
        raise ValueError("source lock needs exactly state_version, lifecycle, repositories")
    version = lock["state_version"]
    if not isinstance(version, str) or len(version.split(".")) != 3 or not all(
        VERSION.fullmatch(part) for part in version.split(".")
    ):
        raise ValueError("source lock state_version must be exact SemVer major.minor.patch")
    lifecycle = lock["lifecycle"]
    if lifecycle not in ("candidate", "released"):
        raise ValueError("source lock lifecycle must be candidate or released")
    repositories = lock["repositories"]
    if not isinstance(repositories, dict) or set(repositories) != set(REPOSITORIES):
        raise ValueError("source lock needs exactly four State repositories")
    for name in REPOSITORIES:
        row = repositories[name]
        expected_keys = {"repository", "commit", "checkout"}
        if lifecycle == "released":
            expected_keys.add("tag")
        if not isinstance(row, dict) or set(row) != expected_keys:
            raise ValueError(f"{name} has invalid {lifecycle} source metadata")
        if row["repository"] != f"fruwehq/determa-state-{('spec' if name == 'specification' else name)}":
            raise ValueError(f"{name} repository identity mismatch")
        if row["checkout"] != f"determa-state-{('spec' if name == 'specification' else name)}":
            raise ValueError(f"{name} checkout identity mismatch")
        if not isinstance(row["commit"], str) or not HEX_COMMIT.fullmatch(row["commit"]):
            raise ValueError(f"{name} needs an immutable 40-character commit")
        if lifecycle == "released" and row["tag"] != f"v{version}":
            raise ValueError(f"{name} release tag must match state_version")
    return lock
