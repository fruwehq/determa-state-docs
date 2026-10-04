"""Install the unreleased Python engine from the exact fetched candidate source."""

from pathlib import Path
import subprocess
import sys
import tomllib

from source_lock import load_lock


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    lock = load_lock()
    if lock["lifecycle"] != "candidate":
        print("released lock: registry dependency remains in requirements.txt")
        return
    source = ROOT / ".sources" / lock["repositories"]["python"]["checkout"]
    if not source.is_dir():
        raise SystemExit("candidate Python checkout is missing; run make sources first")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if actual != lock["repositories"]["python"]["commit"]:
        raise SystemExit("candidate Python checkout does not match its pinned commit")
    origin = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=source, text=True).strip()
    if origin != f"https://github.com/{lock['repositories']['python']['repository']}.git":
        raise SystemExit("candidate Python checkout has an unexpected origin")
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"],
        cwd=source,
        text=True,
    ).strip()
    if dirty:
        raise SystemExit("candidate Python checkout has local changes")
    project = tomllib.loads((source / "pyproject.toml").read_text())["project"]
    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) for item in dependencies
    ):
        raise SystemExit("candidate Python project needs static dependency declarations")
    if dependencies:
        subprocess.run([sys.executable, "-m", "pip", "install", *dependencies], check=True)
    # PEP 610 records both the public repository and resolved commit for a VCS
    # install. The validator also compares the installed bytes to this checkout.
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--force-reinstall",
            "--no-deps",
            f"git+https://github.com/{lock['repositories']['python']['repository']}.git@{actual}",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
