#!/usr/bin/env python3
"""Check upstream State tags and planned tutorial issues for drift."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

from ruamel.yaml import YAML


ROOT = Path(__file__).resolve().parents[1]
SEMVER_TAG = re.compile(r"^refs/tags/v(\d+)\.(\d+)\.(\d+)$")
ISSUE_URL = re.compile(
    r"^https://github\.com/([^/]+)/([^/]+)/issues/(\d+)$"
)


def github_json(url: str, token: str | None) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "determa-state-examples-drift-check",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"GitHub returned HTTP {error.code} for {url}") from error


def main() -> None:
    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    lock = yaml.load((ROOT / "sources.lock.yaml").read_text())
    coverage = yaml.load((ROOT / "coverage.yaml").read_text())
    expected = tuple(int(part) for part in lock["state_version"].split("."))
    token = os.environ.get("GITHUB_TOKEN")

    for repository in lock["repositories"].values():
        name = repository["repository"]
        refs = github_json(
            f"https://api.github.com/repos/{name}/git/matching-refs/tags/v",
            token,
        )
        if not isinstance(refs, list):
            raise SystemExit(f"unexpected tag response for {name}")
        versions = [
            tuple(int(part) for part in match.groups())
            for item in refs
            if (match := SEMVER_TAG.fullmatch(item["ref"]))
        ]
        if not versions:
            raise SystemExit(f"no semantic version tags found for {name}")
        latest = max(versions)
        if latest != expected:
            rendered = ".".join(str(part) for part in latest)
            raise SystemExit(
                f"{name} latest tag is v{rendered}; tutorial pins "
                f"v{lock['state_version']}"
            )
        print(f"{name}: v{lock['state_version']}")

    planned_issues: dict[str, tuple[str, str, int]] = {}
    for group in ("specification", "conformance"):
        for entry in coverage[group]:
            if entry["status"] != "planned":
                continue
            issue_url = entry.get("issue")
            match = ISSUE_URL.fullmatch(issue_url) if isinstance(issue_url, str) else None
            if match is None:
                raise SystemExit(f"invalid planned issue URL: {issue_url!r}")
            owner, repository, number = match.groups()
            planned_issues[issue_url] = (owner, repository, int(number))

    for issue_url, (owner, repository, number) in sorted(planned_issues.items()):
        issue = github_json(
            f"https://api.github.com/repos/{owner}/{repository}/issues/{number}",
            token,
        )
        if not isinstance(issue, dict):
            raise SystemExit(f"unexpected issue response for {issue_url}")
        if "pull_request" in issue:
            raise SystemExit(f"planned entry points to a pull request: {issue_url}")
        if issue.get("state") != "open":
            raise SystemExit(f"planned issue is not open: {issue_url}")
        print(f"planned issue: {issue_url}")


if __name__ == "__main__":
    main()
