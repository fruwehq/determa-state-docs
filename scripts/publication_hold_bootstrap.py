"""Verify reviewed local inputs before installing dependencies or running Make."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "publication-hold-inputs.json"


def reviewed_inputs(root: Path) -> dict[str, str]:
    """Inventory the full local execution and site-input closure, including new files."""
    files = [
        root / name
        for name in (
            "Makefile",
            "requirements.txt",
            "mkdocs.yml",
            "sources.lock.yaml",
            "STATE_VERSION",
            "coverage.yaml",
        )
    ]
    for directory in (".github/workflows", "docs", "scripts", "tests"):
        files.extend(
            path for path in (root / directory).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
    result = {}
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"publication hold input missing or linked: {path}")
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(result.items()))


def check_hold_inputs(root: Path = ROOT) -> None:
    manifest = json.loads((root / MANIFEST).read_text())
    if not isinstance(manifest, dict) or set(manifest) != {"format", "inputs"} or manifest["format"] != 1:
        raise ValueError("publication hold manifest has an unreviewed format")
    expected = manifest["inputs"]
    actual = reviewed_inputs(root)
    if not isinstance(expected, dict) or expected != actual:
        changed = sorted(set(expected or {}) ^ set(actual)) if isinstance(expected, dict) else []
        changed += [name for name in set(expected or {}) & set(actual) if expected[name] != actual[name]] if isinstance(expected, dict) else []
        raise ValueError(f"publication hold inputs changed; update reviewed manifest: {sorted(changed)}")


if __name__ == "__main__":
    check_hold_inputs()
    print("publication hold bootstrap: reviewed input digests verified")
