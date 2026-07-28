# Determa State tutorial

Determa State runs the same state machine definition consistently across languages.
You define behavior once in YAML or JSON, then use a foreground engine call to create
and advance a machine.

This tutorial targets **Determa State 0.0.7** and numeric **`format: 1`**.

## Start here

[Build your first machine](getting-started/first-machine.md) to:

1. define a typed event and variable;
2. create a machine;
3. send one event;
4. observe the same result in Python and Rust.

You do not need to understand the full specification first.

Continue with [CEL and structured actions](guides/cel-and-actions.md) to learn the
complete portable expression profile, ordered guards, every structured action shape,
and atomic fault rollback through matching Python and Rust traces.

Continue with [components and owned instances](guides/components-and-spawning.md) when
one machine must coordinate isolated reusable or dynamically created runtimes.

## What is portable?

The portable core is a pure foreground state transform. Your application supplies one
input envelope and owns the returned state and emissions. Databases, queues, timers,
brokers, and schedulers belong to the host around that core.

The [coverage status](reference/coverage.md) shows what is complete and what remains
planned. Normative details always come from the
[v0.0.7 specification](https://github.com/fruwehq/determa-state-spec/blob/v0.0.7/SPEC.md).
