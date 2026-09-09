# Coverage status

[`coverage.yaml`](https://github.com/fruwehq/determa-state-docs/blob/main/coverage.yaml)
is the machine-readable source of truth for tutorial coverage.

It inventories every normative section, every actual core conformance case, and every
released execution-checkpoint profile case directory at the pinned Determa State 0.2.0
revisions.

Each entry is:

- **covered** when an existing chapter explains or executes it;
- **non-user-facing** when it is specification or test-suite machinery rather than a
  behavior to teach.

Repository validation compares the matrix with the pinned specification headings,
core case directories, and execution-checkpoint profile case directories. Missing,
stale, or duplicate entries fail the build.

The current tutorial covers the first guarded foreground machine,
[core statechart structure and control flow](../guides/core-statecharts.md), the
[complete portable CEL and structured-action surface](../guides/cel-and-actions.md), and
[components and owned instances](../guides/components-and-spawning.md), and
[effects, faults, inspection, and hosting](../guides/effects-faults-hosting.md).
The [persistence and migration tutorial](../guides/persistence-and-migration.md)
adds the portable aggregate, content-addressed definition registry, SQLite
inbox/state/outbox transaction, deterministic quarantine, deleted-state failure, and
explicit lazy remap. The
[persistence reference lab](../guides/persistence-migration-reference.md) executes all
108 released Python and Rust persistence vectors and teaches package transport,
variable/history/component/owned-runtime transforms, exact multi-descriptor routes,
terminal maintenance migration, failure completeness, resource limits,
occurrence-local binding, and large decimal identities.
The [durable checkpoint host](../guides/execution-checkpoint-hosting.md) covers all
three released profile scenarios and executes the complete profile in both engines.

There are no planned entries. Aggregate package transport is covered; portable package
imports in machine definitions remain unsupported.
