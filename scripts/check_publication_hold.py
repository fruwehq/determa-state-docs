"""Fail closed if any repository Actions path can publish documentation."""

from pathlib import Path
import re

from ruamel.yaml import YAML


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "docs.yml"
APPROVED_STEPS = (
    {"name": "Check out tutorial", "uses": "actions/checkout@v7"},
    {"name": "Set up Python", "uses": "actions/setup-python@v7", "with": {"python-version": "3.13", "cache": "pip"}},
    {"name": "Set up Rust", "uses": "dtolnay/rust-toolchain@stable", "with": {"toolchain": "1.95.0"}},
    {"name": "Install pinned dependencies", "run": "python -m pip install --requirement requirements.txt"},
    {"name": "Fetch pinned Determa State sources", "run": "make sources"},
    {"name": "Install candidate Python engine from pinned source", "run": "python scripts/install_candidate.py"},
    {"name": "Validate public source identity and release freshness", "env": {"GITHUB_TOKEN": "${{ github.token }}"}, "run": "python scripts/check_latest.py"},
    {"name": "Verify publication hold", "run": "python scripts/check_publication_hold.py"},
    {"name": "Validate tutorials and build site", "run": "make check"},
)
APPROVED_CHECK = (
    '$(PYTHON) scripts/check_publication_hold.py',
    '$(PYTHON) -m pytest -q tests/test_publication_hold.py',
    '$(PYTHON) scripts/validate.py --source-root "$(SOURCE_ROOT)"',
    '$(PYTHON) -m mkdocs build --strict',
)
PUBLICATION_OPERATION = re.compile(
    r"(?i)(?:\bpages\b|gh-deploy|ghp-import|git\s+push|gh\s+api)"
)


def check_hold(root: Path = ROOT) -> None:
    workflows = root / ".github" / "workflows"
    found = {path.relative_to(workflows).as_posix() for path in workflows.rglob("*") if path.is_file()}
    if found != {"docs.yml"}:
        raise ValueError(f"publication hold requires one reviewed workflow: {sorted(found)}")
    actions = root / ".github" / "actions"
    if actions.exists() and any(path.is_file() for path in actions.rglob("*")):
        raise ValueError("publication hold forbids local Actions")
    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    workflow = yaml.load((workflows / "docs.yml").read_text())
    if not isinstance(workflow, dict) or set(workflow) != {"name", "on", "permissions", "jobs"}:
        raise ValueError("documentation workflow has an unreviewed top-level field")
    if workflow["name"] != "Validate documentation" or workflow["permissions"] != {"contents": "read"}:
        raise ValueError("documentation workflow name or top-level permissions changed")
    triggers = workflow["on"]
    if not isinstance(triggers, dict) or set(triggers) != {"pull_request", "push", "schedule", "workflow_dispatch"}:
        raise ValueError("documentation workflow triggers changed")
    if triggers["pull_request"] is not None or triggers["workflow_dispatch"] is not None:
        raise ValueError("documentation workflow trigger settings changed")
    if triggers["push"] != {"branches": ["main"]} or triggers["schedule"] != [{"cron": "23 4 * * 1"}]:
        raise ValueError("documentation workflow push or schedule settings changed")
    jobs = workflow["jobs"]
    if not isinstance(jobs, dict) or set(jobs) != {"validate"}:
        raise ValueError("publication hold forbids additional jobs")
    job = jobs["validate"]
    if not isinstance(job, dict) or set(job) != {"runs-on", "permissions", "steps"}:
        raise ValueError("documentation validation job shape changed")
    if job["runs-on"] != "ubuntu-latest" or job["permissions"] != {"contents": "read"}:
        raise ValueError("documentation validation job permissions changed")
    if job["steps"] != list(APPROVED_STEPS):
        raise ValueError("documentation workflow steps changed; publication hold review required")
    makefile = (root / "Makefile").read_text()
    check_recipe = []
    in_check = False
    for line in makefile.splitlines():
        if line == "check:":
            in_check = True
            continue
        if in_check and not line.startswith("\t"):
            break
        if in_check:
            check_recipe.append(line.lstrip("\t"))
    if tuple(check_recipe) != APPROVED_CHECK:
        raise ValueError("make check recipe changed; publication hold review required")
    # The approved commands enter these scripts. A publication primitive added
    # below that entry point must be reviewed even if the workflow YAML stays put.
    for path in [root / "Makefile", *sorted((root / "scripts").rglob("*.py"))]:
        if path == root / "scripts" / "check_publication_hold.py":
            continue
        if PUBLICATION_OPERATION.search(path.read_text()):
            raise ValueError(f"publication operation found in {path.relative_to(root)}")


if __name__ == "__main__":
    check_hold()
    print("publication hold: all workflow, action, permission, and check paths closed")
