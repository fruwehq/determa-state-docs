# Determa State documentation

The manual, beginner-friendly tutorial, and documentation website for
[Determa State](https://github.com/fruwehq/determa-state-spec).

The tutorials currently target synchronized Determa State **0.1.0** and the numeric
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
[specification](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md) and
[conformance suite](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0)
remain normative.

Independent, fully working real-world applications live in
[`fruwehq/determa-state-examples`](https://github.com/fruwehq/determa-state-examples).

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

The released format-1 user-facing surface is taught and executed across the progressive
guides. The machine-readable [`coverage.yaml`](coverage.yaml) inventories every
normative section and core conformance case as covered or deliberately
non-user-facing.

Persistence and definition migration include a beginner SQLite walkthrough and an
advanced 105-vector Python/Rust reference lab. Aggregate packages are supported as
content-addressed transport; portable package imports in machine definitions remain
unsupported.

See [CONTRIBUTING.md](CONTRIBUTING.md) before changing examples or coverage.

Licensed under the [MIT License](LICENSE).
