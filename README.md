# Determa State documentation

The manual, beginner-friendly tutorial, and documentation website for
[Determa State](https://github.com/fruwehq/determa-state-spec).

The tutorials currently target synchronized Determa State **0.3.0** (unreleased candidate) and the numeric
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
[specification](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md) and
[conformance suite](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1)
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
make candidate-install
make check
```

`make check` verifies the pinned source versions, specification/core/profile coverage
totality, YAML 1.2 parsing, JSON Schema validity, Python and Rust traces, and the strict
MkDocs build.

Use `make serve` to preview the site locally.

## What the scripts do

The scripts maintain this manual and check its runnable examples. They are not
part of the Determa State engine and do not install timers, HTTP endpoints,
archive exporters, or recovery providers.

| Script | Purpose | Side effects |
|---|---|---|
| [`fetch_sources.py`](scripts/fetch_sources.py) | Fetch the four public repositories at the exact commits in `sources.lock.yaml`; verify checkout identity and cleanliness. | Network reads and local source checkouts. |
| [`source_lock.py`](scripts/source_lock.py) | Read and validate the source-lock metadata. | Reads local files; used by the other scripts. |
| [`install_candidate.py`](scripts/install_candidate.py) | Install the pinned unreleased Python engine and its dependencies for tutorial validation. | Network reads; replaces the engine installation in the Python environment running the command. Use a dedicated virtual environment. |
| [`validate.py`](scripts/validate.py) | Check versions, coverage and links; extract named Markdown fences; validate their syntax/schema; run Python and Rust traces and persistence checks. | Temporary files, local builds and subprocess execution; Cargo may fetch dependencies. `--extract-only` writes `.cache/examples`. |
| [`check_latest.py`](scripts/check_latest.py) | Check public commit identities and that planned coverage issues remain open. For released locks, also check tag identity and latest published versions. | Read-only GitHub API requests. Candidate mode does not require a published 0.3.0 tag. |
| [`publication_hold_bootstrap.py`](scripts/publication_hold_bootstrap.py) | Compare documentation and validation inputs with the local hash inventory before CI installs dependencies or runs Make. | Reads local files. |
| [`check_publication_hold.py`](scripts/check_publication_hold.py) | Check that hash inventory and the expected validation-only workflow/Make recipe. | Reads local files. |

The publication-hold checks make changes visible; their hashes do not establish
independent review or release readiness. They currently include authored chapters,
so an intended chapter edit also requires refreshing `publication-hold-inputs.json`.
The documentation workflow has read-only repository permissions and no deployment
step. `make check` builds the site locally; none of these scripts publishes it or
publishes engine packages.

## Status

The 0.3.0 tutorial migration is in progress in [#28](https://github.com/fruwehq/determa-state-docs/issues/28).
This branch is an unfinished review checkpoint; runnable fences and coverage must pass
validation before it is ready. The candidate website remains under publication hold. The machine-readable [`coverage.yaml`](coverage.yaml) inventories every
normative section, core conformance case, and released execution-checkpoint profile
case as covered or deliberately non-user-facing.

Persistence and definition migration include a durable execution-checkpoint tutorial,
a lower-level SQLite transaction walkthrough, and an advanced 108-vector Python/Rust
reference lab. Aggregate packages are supported as content-addressed transport;
portable package imports in machine definitions remain unsupported.

See [CONTRIBUTING.md](CONTRIBUTING.md) before changing examples or coverage.

Licensed under the [MIT License](LICENSE).
