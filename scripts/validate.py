#!/usr/bin/env python3
"""Validate source pins, coverage, extracted examples, and both engine traces."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

import determa.state as determa_state
from jsonschema import Draft202012Validator
from markdown_it import MarkdownIt
from ruamel.yaml import YAML


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_MARKER = re.compile(r"^<!--\s*determa-example:\s*([^\s]+)\s*-->\s*$")
NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+")
ISSUE_URL = re.compile(
    r"^https://github\.com/fruwehq/determa-state-docs/issues/\d+$"
)
CONFORMANCE_CASE_LINK = re.compile(
    r"https://github\.com/fruwehq/determa-state-conformance/tree/"
    r"v([^/]+)/conformance/core/([0-9]{2}-[A-Za-z0-9-]+)"
)
CORE_STATECHARTS_CHAPTER = "docs/guides/core-statecharts.md"
CORE_STATECHARTS_SPECIFICATION_SECTIONS = (
    "2",
    "4.6",
    "4.7",
    "6.3",
    "6.4",
    "6.5",
    "6.6",
)
CORE_STATECHARTS_CONFORMANCE_CASES = (
    "02-hierarchy-bubbling",
    "03-initial-action",
    "05-variable-scope",
    "06-payload-typing",
    "07-internal-external",
    "08-local-vs-external",
    "10-history-deep",
    "11-history-shallow",
    "15-external-env-refresh",
    "23-choice",
    "24-choice-chain",
    "25-choice-invalid",
    "26-unreachable",
    "27-dead-branch",
    "28-reachable-ok",
    "32-history-resume-restart",
    "33-history-capture-timing",
    "34-history-first-entry",
    "35-shallow-deep-history",
    "36-history-variable-reinitialization",
    "37-destroyed-variable-write",
    "39-ancestor-internal-transition",
    "40-noncanonical-transitions",
    "42-initial-history-rejection",
    "43-self-history-lifecycle",
    "44-local-history",
    "45-proper-ancestor-target",
    "53-compound-choice-lifecycle",
    "56-variable-initialization",
    "57-creation-binding-defaults",
    "58-missing-creation-binding",
    "59-payload-default-materialization",
    "60-payload-default-validation",
    "62-parsed-value-model",
    "63-entry-stop-interruption",
    "84-choice-stop-chain",
)
LANGUAGE_BY_SUFFIX = {
    ".yaml": "yaml",
    ".yml": "yaml",
    ".py": "python",
    ".rs": "rust",
    ".toml": "toml",
}
COMPONENTS_AND_SPAWNING_SPECIFICATION = {"7", "7.1", "7.2", "7.3"}
COMPONENTS_AND_SPAWNING_CASES = {
    "09-parallel-components",
    "13-spawn-completion",
    "14-explicit-targets",
    "29-owned-spawn",
    "30-owned-spawn-cancel",
    "38-destroyed-reference-binding",
    "47-scoped-owned-child-lifetime",
    "48-null-cancel",
    "49-exit-action-cancel",
    "51-component-initialization-fault",
    "52-spawned-initialization-fault",
    "54-stale-component-target",
    "55-root-owner-target",
    "73-synchronous-initialization-cycle",
    "74-sibling-cleanup-order",
    "78-component-external-refresh",
    "80-unbound-owned-child",
    "81-holder-reference-reuse",
    "82-instance-reference-target-identity",
    "83-contained-dynamic-instance-send",
    "86-initial-component-completion-order",
    "87-internal-env-target-mode",
    "91-component-host-input-rejection",
}
INVALID_BUNDLES = {
    "cel-host-extension.yaml": "cel_profile_error",
    "cel-type-mismatch.yaml": "semantic_validation",
    "cel-lifecycle-event.yaml": "semantic_validation",
}
CEL_AND_ACTIONS_SPECIFICATION = {
    "4.8",
    "5",
    "5.1",
    "5.2",
    "5.2.portable-cel-profile",
    "5.3",
}
CEL_AND_ACTIONS_CASES = {
    "12-guarded-list",
    "17-action-fault",
    "61-expression-map-order",
    "64-dynamic-target-expression-order",
    "65-portable-cel-profile",
    "66-cel-profile-rejections",
    "68-cel-and-nonabsorbed-error",
    "69-cel-or-nonabsorbed-error",
    "70-dynamic-target-list-order",
    "71-cel-reversed-and-nonabsorbed-error",
    "72-cel-reversed-or-nonabsorbed-error",
    "79-missing-refresh-field",
}
EFFECTS_FAULTS_HOSTING_CHAPTER = "docs/guides/effects-faults-hosting.md"
EFFECTS_FAULTS_HOSTING_SPECIFICATION = {
    "9",
    "10",
    "10.1",
    "10.2",
    "10.3",
    "11",
    "11.1",
    "11.2",
    "11.3",
    "11.4",
    "12",
    "13",
}
EFFECTS_FAULTS_HOSTING_CASES = {
    "16-timer-extension",
    "18-domain-failure",
    "19-public-event-contract",
    "20-invalid-public-correlation",
    "46-root-boundary-validation",
    "50-root-fault-terminal-aggregate",
    "67-bundle-state-binding",
    "75-root-initialization-fault",
    "76-invalid-create-unicode",
    "77-invalid-dispatch-unicode",
    "85-initialization-emission-rollback",
    "88-reserved-payload-validation",
    "89-nonfinite-creation-binding",
    "90-host-numeric-normalization",
    "92-faulted-root-component-precedence",
    "93-optional-correlation",
}
EFFECTS_FAULTS_HOSTING_SPECIFICATION_ANCHORS = {
    "9": "9-deterministic-identities-and-emissions",
    "10": "10-faults-and-envelope-disposition",
    "10.1": "101-engine-faults",
    "10.2": "102-contained-runtime-faults",
    "10.3": "103-domain-failures",
    "11": "11-plugins-and-hosting",
    "11.1": "111-queue-plugins",
    "11.2": "112-timer-extensions",
    "11.3": "113-external-effects",
    "11.4": "114-hosting-profiles",
    "12": "12-inspection-and-visualization",
    "13": "13-deliberately-unsupported-in-format-1",
}


def yaml_loader() -> YAML:
    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    yaml.allow_duplicate_keys = False
    return yaml


def load_yaml(path: Path) -> object:
    return yaml_loader().load(path.read_text())


def run(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout.strip()


def require_map(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a string-keyed map")
    return value


def require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def source_path(source_root: Path, repository: dict[str, object]) -> Path:
    checkout = repository.get("checkout")
    if not isinstance(checkout, str):
        raise ValueError("repository checkout must be a string")
    return source_root / checkout


def check_versions(source_root: Path) -> tuple[dict[str, object], dict[str, Path]]:
    state_version = (ROOT / "STATE_VERSION").read_text().strip()
    lock = require_map(load_yaml(ROOT / "sources.lock.yaml"), "sources.lock.yaml")
    coverage = require_map(load_yaml(ROOT / "coverage.yaml"), "coverage.yaml")
    if lock.get("state_version") != state_version:
        raise ValueError("sources.lock.yaml state_version does not match STATE_VERSION")
    if coverage.get("state_version") != state_version:
        raise ValueError("coverage.yaml state_version does not match STATE_VERSION")

    repositories = require_map(lock.get("repositories"), "locked repositories")
    paths: dict[str, Path] = {}
    for name in ("specification", "conformance", "python", "rust"):
        repository = require_map(repositories.get(name), f"repository {name}")
        path = source_path(source_root, repository)
        if not path.is_dir():
            raise ValueError(f"missing source checkout: {path}")
        actual_commit = run("git", "rev-parse", "HEAD", cwd=path)
        expected_commit = repository.get("commit")
        if actual_commit != expected_commit:
            raise ValueError(
                f"{name} source is {actual_commit}, expected {expected_commit}"
            )
        dirty = run(
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
            cwd=path,
        )
        if dirty:
            raise ValueError(f"{name} source checkout has local changes:\n{dirty}")
        paths[name] = path

    if (paths["specification"] / "VERSION").read_text().strip() != state_version:
        raise ValueError("specification VERSION drift")
    spec_header = (paths["specification"] / "SPEC.md").read_text().splitlines()
    if not any(
        line.startswith(f"Spec version: **{state_version}**")
        for line in spec_header[:8]
    ):
        raise ValueError("SPEC.md version header drift")
    if (paths["conformance"] / "VERSION").read_text().strip() != state_version:
        raise ValueError("conformance VERSION drift")

    python_metadata = tomllib.loads((paths["python"] / "pyproject.toml").read_text())
    version_path = python_metadata["tool"]["hatch"]["version"]["path"]
    version_source = (paths["python"] / version_path).read_text()
    version_match = re.search(r'^__version__ = "([^"]+)"$', version_source, re.MULTILINE)
    if version_match is None or version_match.group(1) != state_version:
        raise ValueError("Python package version drift")
    rust_metadata = tomllib.loads((paths["rust"] / "Cargo.toml").read_text())
    if rust_metadata["package"]["version"] != state_version:
        raise ValueError("Rust crate version drift")

    required_references = {
        ROOT / "README.md": f"Determa State **{state_version}**",
        ROOT / "AGENTS.md": f"Determa State synchronized version: `{state_version}`",
        ROOT / "docs" / "index.md": f"Determa State {state_version}",
        ROOT / "requirements.txt": f"determa-state=={state_version}",
        ROOT / "docs" / "getting-started" / "first-machine.md": (
            f'determa-state = "={state_version}"'
        ),
    }
    for path, expected in required_references.items():
        if expected not in path.read_text():
            raise ValueError(f"tutorial version reference drift in {path.relative_to(ROOT)}")

    print(f"source versions: Determa State {state_version}")
    return coverage, paths


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def specification_sections(specification: Path) -> list[str]:
    tokens = MarkdownIt("commonmark").parse(
        (specification / "SPEC.md").read_text()
    )
    sections: list[str] = []
    current_numbered: str | None = None
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.tag == "h1":
            continue
        title = tokens[index + 1].content
        match = NUMBERED_HEADING.match(title)
        if match:
            current_numbered = match.group(1)
            sections.append(current_numbered)
            continue
        if current_numbered is None:
            raise ValueError(f"unnumbered specification heading before a section: {title}")
        sections.append(f"{current_numbered}.{slug(title)}")
    return sections


def conformance_cases(conformance: Path) -> list[str]:
    core = conformance / "conformance" / "core"
    return sorted(
        (path.name for path in core.iterdir() if path.is_dir()),
        key=lambda value: value.encode("utf-8"),
    )


def check_dispositions(
    entries: Iterable[object],
    key: str,
    expected: list[str],
    label: str,
) -> None:
    records = [require_map(entry, f"{label} entry") for entry in entries]
    actual: list[str] = []
    for record in records:
        identifier = record.get(key)
        status = record.get("status")
        if not isinstance(identifier, str):
            raise ValueError(f"{label} {key} must be a string")
        if identifier in actual:
            raise ValueError(f"duplicate {label} entry: {identifier}")
        actual.append(identifier)
        if status in {"covered", "planned"}:
            chapter = record.get("chapter")
            if not isinstance(chapter, str) or not (ROOT / chapter).is_file():
                raise ValueError(f"{label} {identifier} has no existing chapter")
            if status == "planned":
                issue = record.get("issue")
                if not isinstance(issue, str) or not ISSUE_URL.fullmatch(issue):
                    raise ValueError(f"{label} {identifier} has no valid planning issue")
        elif status == "non_user_facing":
            reason = record.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"{label} {identifier} needs a classification reason")
        else:
            raise ValueError(f"{label} {identifier} has invalid status {status!r}")

    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing or extra:
        raise ValueError(f"{label} coverage mismatch; missing={missing}, extra={extra}")


def check_coverage(
    coverage: dict[str, object], specification: Path, conformance: Path
) -> None:
    spec_sections = specification_sections(specification)
    cases = conformance_cases(conformance)
    check_dispositions(
        require_list(coverage.get("specification"), "specification coverage"),
        "id",
        spec_sections,
        "specification",
    )
    check_dispositions(
        require_list(coverage.get("conformance"), "conformance coverage"),
        "case",
        cases,
        "conformance",
    )
    check_core_statecharts_coverage(coverage)
    print(f"coverage: {len(spec_sections)} spec sections, {len(cases)} core cases")


def check_components_and_spawning_coverage(coverage: dict[str, object]) -> None:
    chapter_path = "docs/guides/components-and-spawning.md"
    specification = {
        require_map(entry, "specification coverage entry")["id"]: require_map(
            entry, "specification coverage entry"
        )
        for entry in require_list(
            coverage.get("specification"), "specification coverage"
        )
    }
    conformance = {
        require_map(entry, "conformance coverage entry")["case"]: require_map(
            entry, "conformance coverage entry"
        )
        for entry in require_list(coverage.get("conformance"), "conformance coverage")
    }
    for identifier in COMPONENTS_AND_SPAWNING_SPECIFICATION:
        record = specification[identifier]
        if record.get("status") != "covered" or record.get("chapter") != chapter_path:
            raise ValueError(
                f"components chapter does not cover specification {identifier}"
            )
    chapter = (ROOT / chapter_path).read_text()
    for case in COMPONENTS_AND_SPAWNING_CASES:
        record = conformance[case]
        if record.get("status") != "covered" or record.get("chapter") != chapter_path:
            raise ValueError(f"components chapter does not cover conformance {case}")
        if f"/{case})" not in chapter:
            raise ValueError(f"components chapter does not link conformance {case}")
    print(
        "components coverage: "
        f"{len(COMPONENTS_AND_SPAWNING_SPECIFICATION)} spec sections, "
        f"{len(COMPONENTS_AND_SPAWNING_CASES)} core cases"
    )


def check_cel_and_actions_coverage(coverage: dict[str, object]) -> None:
    chapter_path = "docs/guides/cel-and-actions.md"
    specification = {
        require_map(entry, "specification coverage entry")["id"]: require_map(
            entry, "specification coverage entry"
        )
        for entry in require_list(
            coverage.get("specification"), "specification coverage"
        )
    }
    conformance = {
        require_map(entry, "conformance coverage entry")["case"]: require_map(
            entry, "conformance coverage entry"
        )
        for entry in require_list(coverage.get("conformance"), "conformance coverage")
    }
    mapped_specification = {
        identifier
        for identifier, record in specification.items()
        if record.get("status") == "covered"
        and record.get("chapter") == chapter_path
    }
    if mapped_specification != CEL_AND_ACTIONS_SPECIFICATION:
        raise ValueError(
            "CEL/actions specification mapping mismatch; "
            f"expected={sorted(CEL_AND_ACTIONS_SPECIFICATION)}, "
            f"actual={sorted(mapped_specification)}"
        )
    mapped_cases = {
        case
        for case, record in conformance.items()
        if record.get("status") == "covered"
        and record.get("chapter") == chapter_path
    }
    if mapped_cases != CEL_AND_ACTIONS_CASES:
        raise ValueError(
            "CEL/actions conformance mapping mismatch; "
            f"expected={sorted(CEL_AND_ACTIONS_CASES)}, "
            f"actual={sorted(mapped_cases)}"
        )
    chapter = (ROOT / chapter_path).read_text()
    for case in CEL_AND_ACTIONS_CASES:
        link = (
            "https://github.com/fruwehq/determa-state-conformance/"
            f"tree/v0.1.0/conformance/core/{case}"
        )
        if f"]({link})" not in chapter:
            raise ValueError(f"CEL/actions chapter does not link conformance {case}")
    print(
        "CEL/actions coverage: "
        f"{len(CEL_AND_ACTIONS_SPECIFICATION)} spec sections, "
        f"{len(CEL_AND_ACTIONS_CASES)} core cases"
    )


def check_effects_faults_hosting_coverage(coverage: dict[str, object]) -> None:
    specification = {
        require_map(entry, "specification coverage entry")["id"]: require_map(
            entry, "specification coverage entry"
        )
        for entry in require_list(
            coverage.get("specification"), "specification coverage"
        )
    }
    conformance = {
        require_map(entry, "conformance coverage entry")["case"]: require_map(
            entry, "conformance coverage entry"
        )
        for entry in require_list(coverage.get("conformance"), "conformance coverage")
    }
    mapped_specification = {
        identifier
        for identifier, record in specification.items()
        if record.get("status") == "covered"
        and record.get("chapter") == EFFECTS_FAULTS_HOSTING_CHAPTER
    }
    if mapped_specification != EFFECTS_FAULTS_HOSTING_SPECIFICATION:
        raise ValueError(
            "effects/faults/hosting specification mapping mismatch; "
            f"expected={sorted(EFFECTS_FAULTS_HOSTING_SPECIFICATION)}, "
            f"actual={sorted(mapped_specification)}"
        )
    mapped_cases = {
        case
        for case, record in conformance.items()
        if record.get("status") == "covered"
        and record.get("chapter") == EFFECTS_FAULTS_HOSTING_CHAPTER
    }
    if mapped_cases != EFFECTS_FAULTS_HOSTING_CASES:
        raise ValueError(
            "effects/faults/hosting conformance mapping mismatch; "
            f"expected={sorted(EFFECTS_FAULTS_HOSTING_CASES)}, "
            f"actual={sorted(mapped_cases)}"
        )

    state_version = coverage.get("state_version")
    if not isinstance(state_version, str):
        raise ValueError("coverage state_version must be a string")
    chapter = (ROOT / EFFECTS_FAULTS_HOSTING_CHAPTER).read_text()
    for identifier, anchor in EFFECTS_FAULTS_HOSTING_SPECIFICATION_ANCHORS.items():
        url = (
            "https://github.com/fruwehq/determa-state-spec/blob/"
            f"v{state_version}/SPEC.md#{anchor}"
        )
        if chapter.count(url) != 1:
            raise ValueError(
                "effects/faults/hosting specification link must occur once: "
                f"{identifier}"
            )
    for case in EFFECTS_FAULTS_HOSTING_CASES:
        url = (
            "https://github.com/fruwehq/determa-state-conformance/tree/"
            f"v{state_version}/conformance/core/{case}"
        )
        if chapter.count(url) != 1:
            raise ValueError(
                f"effects/faults/hosting conformance link must occur once: {case}"
            )
    required_boundaries = (
        "also defines portable aggregate serialization",
        "do not promise\ndelivery exactly once",
        "A scheduling intent is not a portable timer",
        "authentication, authorization, tenancy, transport, and presentation",
    )
    for boundary in required_boundaries:
        if boundary not in chapter:
            raise ValueError(
                f"effects/faults/hosting boundary statement drift: {boundary!r}"
            )
    print(
        "effects/faults/hosting coverage: "
        f"{len(EFFECTS_FAULTS_HOSTING_SPECIFICATION)} spec sections, "
        f"{len(EFFECTS_FAULTS_HOSTING_CASES)} core cases"
    )


def check_core_statecharts_coverage(coverage: dict[str, object]) -> None:
    assignments = (
        (
            require_list(coverage.get("specification"), "specification coverage"),
            "id",
            CORE_STATECHARTS_SPECIFICATION_SECTIONS,
            "specification",
        ),
        (
            require_list(coverage.get("conformance"), "conformance coverage"),
            "case",
            CORE_STATECHARTS_CONFORMANCE_CASES,
            "conformance",
        ),
    )
    for raw_entries, key, expected_identifiers, label in assignments:
        entries = [
            require_map(entry, f"{label} entry")
            for entry in raw_entries
        ]
        mapped = {
            entry.get(key)
            for entry in entries
            if entry.get("chapter") == CORE_STATECHARTS_CHAPTER
        }
        expected = set(expected_identifiers)
        if mapped != expected:
            raise ValueError(
                f"core statecharts {label} assignment mismatch; "
                f"missing={sorted(expected - mapped)}, "
                f"extra={sorted(mapped - expected)}"
            )
        for entry in entries:
            if entry.get(key) in expected and (
                entry.get("status") != "covered"
                or entry.get("chapter") != CORE_STATECHARTS_CHAPTER
            ):
                raise ValueError(
                    f"core statecharts {label} {entry.get(key)} is not covered "
                    "by the core statecharts chapter"
                )

    state_version = coverage.get("state_version")
    if not isinstance(state_version, str):
        raise ValueError("coverage state_version must be a string")
    chapter = (ROOT / CORE_STATECHARTS_CHAPTER).read_text()
    actual_links = set(CONFORMANCE_CASE_LINK.findall(chapter))
    expected_links = {
        (state_version, case)
        for case in CORE_STATECHARTS_CONFORMANCE_CASES
    }
    if actual_links != expected_links:
        raise ValueError(
            "core statecharts conformance links mismatch; "
            f"missing={sorted(expected_links - actual_links)}, "
            f"extra={sorted(actual_links - expected_links)}"
        )
    for case in CORE_STATECHARTS_CONFORMANCE_CASES:
        url = (
            "https://github.com/fruwehq/determa-state-conformance/tree/"
            f"v{state_version}/conformance/core/{case}"
        )
        if chapter.count(url) != 1:
            raise ValueError(
                f"core statecharts conformance link must occur once: {case}"
            )
    print(
        "core statecharts coverage: "
        f"{len(CORE_STATECHARTS_SPECIFICATION_SECTIONS)} spec sections, "
        f"{len(CORE_STATECHARTS_CONFORMANCE_CASES)} linked core cases"
    )


def safe_example_path(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe example path: {raw}")
    return path


def extract_examples(destination: Path) -> list[Path]:
    markdown = MarkdownIt("commonmark")
    extracted: list[Path] = []
    seen: set[PurePosixPath] = set()
    for document in sorted((ROOT / "docs").rglob("*.md")):
        pending: PurePosixPath | None = None
        for token in markdown.parse(document.read_text()):
            if token.type == "html_block":
                match = EXAMPLE_MARKER.fullmatch(token.content.strip())
                if match:
                    if pending is not None:
                        raise ValueError(f"unconsumed example marker in {document}")
                    pending = safe_example_path(match.group(1))
                    continue
            if token.type == "fence" and pending is not None:
                if pending in seen:
                    raise ValueError(f"duplicate example path: {pending}")
                expected_language = LANGUAGE_BY_SUFFIX.get(pending.suffix)
                if expected_language is None or token.info.strip() != expected_language:
                    raise ValueError(
                        f"{pending} requires a {expected_language!r} fence, "
                        f"found {token.info.strip()!r}"
                    )
                output = destination.joinpath(*pending.parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(token.content)
                extracted.append(output)
                seen.add(pending)
                pending = None
                continue
            if pending is not None and token.type not in {"html_block"}:
                raise ValueError(f"example marker in {document} must precede its fence")
        if pending is not None:
            raise ValueError(f"example marker without fence in {document}")
    if not extracted:
        raise ValueError("no runnable example fences found")
    print(f"extraction: {len(extracted)} files")
    return extracted


def check_bundles(extracted: Iterable[Path], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    valid_count = 0
    invalid_count = 0
    for path in extracted:
        if path.suffix not in {".yaml", ".yml"}:
            continue
        document = load_yaml(path)
        validator.validate(document)
        expected_error = (
            INVALID_BUNDLES.get(path.name) if path.parent.name == "invalid" else None
        )
        if expected_error is None:
            determa_state.load_bundle(path.read_text())
            valid_count += 1
            continue
        try:
            determa_state.load_bundle(path.read_text())
        except determa_state.ValidationError as error:
            if error.code != expected_error:
                raise ValueError(
                    f"{path.name} rejected with {error.code}, expected {expected_error}"
                ) from error
        else:
            raise ValueError(f"{path.name} unexpectedly passed semantic validation")
        invalid_count += 1
    if valid_count == 0:
        raise ValueError("no extracted machine bundles found")
    print(
        "bundles: "
        f"{valid_count} valid and {invalid_count} expected semantic rejections; "
        "all YAML 1.2 and schema-valid"
    )


def run_traces(destination: Path) -> None:
    traces = [
        (
            destination / "python" / "first_counter.py",
            destination / "rust" / "first-counter" / "Cargo.toml",
            destination / "machines" / "first-counter.yaml",
            "count=3; next increment was unhandled",
        ),
        (
            destination / "python" / "core_statecharts.py",
            destination / "rust" / "core-statecharts" / "Cargo.toml",
            destination,
            (
                "order=work.review; history=deep_second; "
                "yaml=no; stop=completed"
            ),
        ),
    ]
    for python_example, rust_manifest, argument, expected in traces:
        python_output = run(sys.executable, str(python_example), str(argument))
        rust_output = run(
            "cargo",
            "run",
            "--quiet",
            "--manifest-path",
            str(rust_manifest),
            "--",
            str(argument),
        )
        if python_output != expected or rust_output != expected:
            raise ValueError(
                f"trace mismatch: python={python_output!r}, rust={rust_output!r}"
            )

    components_machine = destination / "machines" / "order-components.yaml"
    owned_machine = destination / "machines" / "owned-workers.yaml"
    components_python = destination / "python" / "components_and_spawning.py"
    components_rust_manifest = (
        destination / "rust" / "components-spawning" / "Cargo.toml"
    )
    components_python_output = run(
        sys.executable,
        str(components_python),
        str(components_machine),
        str(owned_machine),
    )
    components_rust_output = run(
        "cargo",
        "run",
        "--quiet",
        "--manifest-path",
        str(components_rust_manifest),
        "--",
        str(components_machine),
        str(owned_machine),
    )
    components_expected = "\n".join(
        (
            "components: isolated, refreshed, stale target rejected, completed",
            "owned: 4 spawned, 2 scoped disposed, bound completed, unbound cascaded",
        )
    )
    if (
        components_python_output != components_expected
        or components_rust_output != components_expected
    ):
        raise ValueError(
            "components trace mismatch: "
            f"python={components_python_output!r}, rust={components_rust_output!r}"
        )
    print(
        "traces: Python and Rust agree for first machine, core statecharts, "
        "and components/spawning"
    )

    cel_paths = [
        destination / "machines" / "guard-order.yaml",
        destination / "machines" / "cel-actions.yaml",
        destination / "machines" / "cel-faults.yaml",
        destination / "invalid" / "cel-host-extension.yaml",
        destination / "invalid" / "cel-type-mismatch.yaml",
        destination / "invalid" / "cel-lifecycle-event.yaml",
    ]
    cel_python = destination / "python" / "cel_actions.py"
    cel_rust_manifest = destination / "rust" / "cel-actions" / "Cargo.toml"
    cel_python_output = run(
        sys.executable,
        str(cel_python),
        *(str(path) for path in cel_paths),
    )
    cel_rust_output = run(
        "cargo",
        "run",
        "--quiet",
        "--manifest-path",
        str(cel_rust_manifest),
        "--",
        *(str(path) for path in cel_paths),
    )
    cel_expected = (
        "guards=standard,bulk,empty; total=4.5; "
        "audit=audit:priority:vip:4.5; faults=11"
    )
    if cel_python_output != cel_expected or cel_rust_output != cel_expected:
        raise ValueError(
            "CEL trace mismatch: "
            f"python={cel_python_output!r}, rust={cel_rust_output!r}"
        )
    print("traces: Python and Rust agree on first-machine and CEL/action traces")

    effects_machine = destination / "machines" / "effects-faults-hosting.yaml"
    effects_python = destination / "python" / "effects_faults_hosting.py"
    effects_rust_manifest = (
        destination / "rust" / "effects-faults-hosting" / "Cargo.toml"
    )
    effects_python_output = run(
        sys.executable,
        str(effects_python),
        str(effects_machine),
    )
    effects_rust_output = run(
        "cargo",
        "run",
        "--quiet",
        "--manifest-path",
        str(effects_rust_manifest),
        "--",
        str(effects_machine),
    )
    effects_expected = (
        "effect=deterministic; correlation=enforced; domain=handled; "
        "timer=host-event; fault=rolled-back; terminal=stable"
    )
    if (
        effects_python_output != effects_expected
        or effects_rust_output != effects_expected
    ):
        raise ValueError(
            "effects/faults/hosting trace mismatch: "
            f"python={effects_python_output!r}, rust={effects_rust_output!r}"
        )
    print("traces: Python and Rust agree on effects/faults/hosting")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=ROOT / ".sources")
    parser.add_argument("--extract-only", action="store_true")
    args = parser.parse_args()

    if args.extract_only:
        destination = ROOT / ".cache" / "examples"
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        extract_examples(destination)
        print(destination)
        return

    coverage, paths = check_versions(args.source_root)
    check_coverage(coverage, paths["specification"], paths["conformance"])
    check_components_and_spawning_coverage(coverage)
    check_cel_and_actions_coverage(coverage)
    check_effects_faults_hosting_coverage(coverage)
    with tempfile.TemporaryDirectory(prefix="determa-examples-") as temporary:
        destination = Path(temporary)
        extracted = extract_examples(destination)
        check_bundles(
            extracted,
            paths["specification"] / "schema" / "machine.schema.json",
        )
        run_traces(destination)
    print("validation: passed")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"validation failed: {error}") from error
