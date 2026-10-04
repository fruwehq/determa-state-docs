#!/usr/bin/env python3
"""Fetch immutable Determa source inputs without modifying existing checkouts."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

from source_lock import load_lock


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return completed.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=ROOT / ".sources")
    args = parser.parse_args()

    lock = load_lock()
    repositories = lock.get("repositories")
    if not isinstance(repositories, dict):
        raise SystemExit("sources.lock.yaml repositories must be a map")

    args.destination.mkdir(parents=True, exist_ok=True)
    for name, raw in repositories.items():
        if not isinstance(raw, dict):
            raise SystemExit(f"invalid repository lock for {name}")
        repository = raw["repository"]
        commit = raw["commit"]
        checkout = raw["checkout"]

        destination = args.destination / checkout
        if not destination.exists():
            destination.mkdir()
            run("git", "init", str(destination))
            run("git", "remote", "add", "origin", f"https://github.com/{repository}.git", cwd=destination)
            run("git", "fetch", "--depth", "1", "origin", commit, cwd=destination)
            run("git", "checkout", "--detach", "FETCH_HEAD", cwd=destination)
        actual = run("git", "rev-parse", "HEAD", cwd=destination)
        if actual != commit:
            raise SystemExit(
                f"{destination} is {actual}, expected {commit}; "
                "remove or move that generated checkout before retrying"
            )
        origin = run("git", "remote", "get-url", "origin", cwd=destination)
        if origin != f"https://github.com/{repository}.git":
            raise SystemExit(f"{destination} has unexpected origin {origin}")
        dirty = run(
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
            cwd=destination,
        )
        if dirty:
            raise SystemExit(f"{destination} has local changes:\n{dirty}")
        print(f"{name}: {commit}")


if __name__ == "__main__":
    main()
