# Coverage status

[`coverage.yaml`](https://github.com/fruwehq/determa-state-examples/blob/main/coverage.yaml)
is the machine-readable source of truth for tutorial coverage.

It inventories every normative section and every actual core conformance case at the
pinned Determa State 0.0.7 revisions.

Each entry is:

- **covered** when an existing chapter explains or executes it;
- **planned** when an open child issue owns its future chapter;
- **non-user-facing** when it is specification or test-suite machinery rather than a
  behavior to teach.

Repository validation compares the matrix with the pinned specification headings and
conformance case directories. Missing, stale, or duplicate entries fail the build.

The current tutorial covers the first foreground machine, the complete portable CEL
and structured-action surface, and
[components and owned instances](../guides/components-and-spawning.md). Issues
[#3](https://github.com/fruwehq/determa-state-examples/issues/3),
[#6](https://github.com/fruwehq/determa-state-examples/issues/6), and
[#7](https://github.com/fruwehq/determa-state-examples/issues/7) track the remaining
chapters.
