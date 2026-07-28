# Determa State examples

Beginner-friendly, runnable tutorials for
[Determa State](https://github.com/fruwehq/determa-state-spec).

The tutorials currently target synchronized Determa State **0.0.7** and the numeric
`format: 1` grammar. Start with
[Your first machine](docs/getting-started/first-machine.md).

## One source, two views

Every chapter is ordinary Markdown:

- GitHub renders the files under [`docs/`](docs/) directly.
- [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) builds those same
  files as a searchable static site.
- Runnable files are extracted from named Markdown code fences during validation. They
  are never maintained as duplicate authored copies.

This repository explains and demonstrates Determa State. The
[specification](https://github.com/fruwehq/determa-state-spec/blob/v0.0.7/SPEC.md) and
[conformance suite](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7)
remain normative.

## Validate locally

Python 3.11 or newer, Rust 1.95.0, and Git are required.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --requirement requirements.txt
make sources
make check
```

`make check` verifies the pinned source versions, coverage totality, YAML 1.2 parsing,
JSON Schema validity, Python and Rust traces, and the strict MkDocs build.

Use `make serve` to preview the site locally.

## Status

Issue [#1](https://github.com/fruwehq/determa-state-examples/issues/1) tracks complete
format-1 tutorial coverage. The machine-readable [`coverage.yaml`](coverage.yaml)
distinguishes covered, planned, and deliberately non-user-facing material.

Persistence and definition migration are blocked on
[determa-state-spec#51](https://github.com/fruwehq/determa-state-spec/issues/51).
Portable package imports are not part of format 1 and are not documented as available.

See [CONTRIBUTING.md](CONTRIBUTING.md) before changing examples or coverage.

Licensed under the [MIT License](LICENSE).
