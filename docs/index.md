# Determa State documentation

Determa State runs the same state machine definition consistently across languages.
You define behavior once in YAML or JSON, then use a foreground engine call to create
and advance a machine.

This tutorial targets **Determa State 0.1.0** and numeric **`format: 1`**.

This site owns the manual and progressive tutorial. Independent, fully working
real-world applications live in
[`fruwehq/determa-state-examples`](https://github.com/fruwehq/determa-state-examples).

## Start here

[Build your first machine](getting-started/first-machine.md) to:

1. define a typed event and variable;
2. create a machine;
3. send one event;
4. observe the same result in Python and Rust.

You do not need to understand the full specification first.

Continue with [core statecharts](guides/core-statecharts.md) for nested states,
hierarchical dispatch, transition boundaries, choices, history, typed creation data,
external values, portable YAML parsing, and stop behavior.

Then study [CEL and structured actions](guides/cel-and-actions.md) to learn the
complete portable expression profile, ordered guards, every structured action shape,
and atomic fault rollback through matching Python and Rust traces.

Use [components and owned instances](guides/components-and-spawning.md) when
one machine must coordinate isolated reusable or dynamically created runtimes.

Finish the released format-1 tutorial with
[effects, faults, inspection, and hosting](guides/effects-faults-hosting.md). It
explains public effect intents, correlation, deterministic results, terminal states,
and the boundary between the portable core and host infrastructure.

## What is portable?

The portable core is a pure foreground state transform. Your application supplies one
input envelope and owns the returned state and emissions. Databases, queues, timers,
brokers, and schedulers belong to the host around that core.

The [coverage status](reference/coverage.md) shows what is complete and what remains
planned. Normative details always come from the
[v0.1.0 specification](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md).
