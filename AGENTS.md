# AGENTS.md - determa-state-examples

Guidance for coding agents working in this repository.

## Repository role

This repository contains the living, beginner-friendly tutorials and runnable examples
for Determa State. Ordinary Markdown under `docs/` is the single authored source for
both GitHub viewing and the MkDocs Material static site.

This repository is explanatory, not normative. The `determa-state-spec` specification
and applicable `determa-state-conformance` core cases decide portable behavior.

## Current target

- Determa State synchronized version: `0.0.7`
- machine grammar: numeric `format: 1`
- exact source revisions: `sources.lock.yaml`

The coverage matrix must contain every normative specification section and every
actual core conformance case at the pinned revisions.

## Working rules

- One implementation issue to one branch to one pull request, squash-merged with linear
  history and all review conversations resolved.
- Never add assistant attribution to commits, pull requests, comments, or docs.
- Behavioral changes land specification, conformance, Python, and Rust before their
  tutorial claims become covered.
- Keep spec, conformance, Python, and Rust State versions synchronized. The umbrella
  launcher versions independently.
- Do not add new abbreviations to public JSON or identifiers.
- Ask before broad changes. Keep each tutorial pull request focused and reviewable.
- Never edit generated example files or site output; edit the Markdown fence that
  produced them.

## Documentation contract

- Markdown under `docs/` must render cleanly on GitHub.
- A runnable fence is preceded by
  `<!-- determa-example: safe/relative/path -->`.
- `scripts/validate.py` extracts named fences to a temporary directory, parses YAML
  with YAML 1.2 rules, validates bundles with the pinned schema, and executes the
  Python and Rust traces.
- `coverage.yaml` uses `covered`, `planned`, or `non_user_facing`. Covered entries must
  name an existing chapter. Planned entries must name an open implementation issue.
- Normative text belongs in `determa-state-spec`, not here. Link to it and explain it
  in beginner language.
- Persistence/migration content remains blocked on `determa-state-spec#51`.
- Package-import content remains unsupported until a portable import contract exists.

## Gates

```sh
python -m pip install --requirement requirements.txt
make sources
make check
```

`make check` runs source/version, coverage, extraction, schema, both-engine trace, and
strict site-build validation. CI is the same contract.

## Repository map

- `docs/`: authored tutorial chapters.
- `coverage.yaml`: spec-section and core-case disposition.
- `sources.lock.yaml`: immutable upstream source identities.
- `STATE_VERSION`: synchronized State version displayed and checked.
- `scripts/`: extraction and validation tools.
- `mkdocs.yml`: site navigation and presentation.
