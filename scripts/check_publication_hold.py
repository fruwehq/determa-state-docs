"""Fail closed when Actions or any reviewed validation input changes."""

from pathlib import Path

from ruamel.yaml import YAML
from publication_hold_bootstrap import check_hold_inputs, reviewed_inputs, MANIFEST


ROOT = Path(__file__).resolve().parents[1]
APPROVED_STEPS = (
    {"name": "Check out tutorial", "uses": "actions/checkout@v7"},
    {"name": "Verify reviewed inputs before running repository code", "run": "python scripts/publication_hold_bootstrap.py"},
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

def check_hold(root: Path = ROOT) -> None:
    check_hold_inputs(root)
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


if __name__ == "__main__":
    check_hold()
    print("publication hold: workflow and reviewed input digests verified")
