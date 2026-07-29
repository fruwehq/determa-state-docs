# Coverage status

[`coverage.yaml`](https://github.com/fruwehq/determa-state-docs/blob/main/coverage.yaml)
is the machine-readable source of truth for tutorial coverage.

It inventories every normative section and every actual core conformance case at the
pinned Determa State 0.1.0 revisions.

Each entry is:

- **covered** when an existing chapter explains or executes it;
- **planned** when an open child issue owns its future chapter;
- **non-user-facing** when it is specification or test-suite machinery rather than a
  behavior to teach.

Repository validation compares the matrix with the pinned specification headings and
conformance case directories. Missing, stale, or duplicate entries fail the build.

The current tutorial covers the first guarded foreground machine,
[core statechart structure and control flow](../guides/core-statecharts.md), the
[complete portable CEL and structured-action surface](../guides/cel-and-actions.md), and
[components and owned instances](../guides/components-and-spawning.md), and
[effects, faults, inspection, and hosting](../guides/effects-faults-hosting.md).
The [persistence and migration tutorial](../guides/persistence-and-migration.md)
adds the portable aggregate, content-addressed definition registry, SQLite
inbox/state/outbox transaction, deleted-state failure, and explicit lazy remap.

Advanced package transport, variable/history/component/owned-runtime transforms,
multi-descriptor routes, terminal maintenance migration, and resource-limit vectors
remain planned under
[issue #7](https://github.com/fruwehq/determa-state-docs/issues/7) because the focused
tutorial does not execute them.
