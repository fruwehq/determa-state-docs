# Your first machine

This counter accepts an `increment` event. A guard keeps the count at or below 10.
The machine and its state are ordinary data owned by your program.

## Define the bundle

A **bundle** is one YAML or JSON document containing shared event contracts and one or
more machines. This bundle contains one machine named `counter`.

<!-- determa-example: machines/first-counter.yaml -->
```yaml
format: 1
namespace: tutorial.first
events:
  increment:
    direction: input
    payload:
      amount: { type: int, required: true }
machines:
  - machine_id: counter
    version: 1
    root:
      type: composite
      variables:
        count: { type: int, init: 0 }
      initial: { transition_to: running }
      states:
        running:
          on_events:
            increment:
              guard: count + event.payload.amount <= 10
              action:
                - assign: { count: count + event.payload.amount }
```

The bundle declares:

- the exact format;
- a namespace and machine identity;
- an input event with a required integer payload;
- an integer variable initialized to zero;
- an initial transition to `running`;
- a guarded action that computes the next value with portable CEL.

The schema and semantic loader reject misspelled fields, invalid event payloads, and
type errors before the machine runs.

## Run it with Python

Install the released engine:

```sh
python -m pip install determa-state==0.2.0
```

The complete program is below. `create` returns the initial state. `dispatch` returns
the resulting state: a handled step may produce a new immutable state, while unhandled
or rejected processing preserves the exact prior state object. Neither call retains
hidden work.

<!-- determa-example: python/first_counter.py -->
```python
from pathlib import Path
import sys

import determa.state as ds

machine_path = Path(sys.argv[1])
bundle = ds.load_bundle(machine_path.read_text())
created = ds.create(
    bundle,
    machine_id="counter",
    root_instance_id="tutorial-counter",
    creation_id="tutorial-counter:create",
    bindings={},
)
assert created["status"] == "running"
state = created["state"]

target = {
    "root": {
        "root_instance_id": state["root_instance_id"],
        "root_runtime_id": state["root_runtime_id"],
    }
}

accepted = ds.dispatch(
    bundle,
    state,
    {
        "input": {
            "event": "increment",
            "event_id": "tutorial-counter:increment:1",
            "target": target,
            "payload": {"amount": 3},
        }
    },
)
assert accepted["status"] == "running"
assert accepted["disposition"] == "handled"
state = accepted["state"]
root = state["runtimes"][state["root_runtime_id"]]
assert root["scopes"]["root"]["count"] == 3

rejected_by_guard = ds.dispatch(
    bundle,
    state,
    {
        "input": {
            "event": "increment",
            "event_id": "tutorial-counter:increment:2",
            "target": target,
            "payload": {"amount": 8},
        }
    },
)
assert rejected_by_guard["status"] == "running"
assert rejected_by_guard["disposition"] == "unhandled"
assert rejected_by_guard["state"] is state
print("count=3; next increment was unhandled")
```

From this repository, extract the authored fences and run the generated files:

```sh
make extract
python .cache/examples/python/first_counter.py \
  .cache/examples/machines/first-counter.yaml
```

Expected output:

```text
count=3; next increment was unhandled
```

`unhandled` is not an engine fault. It means no enabled handler accepted that event in
the active state hierarchy. Here, the guard correctly prevented `3 + 8`.

## Run the same trace with Rust

Create a small Cargo project with the released crate.

<!-- determa-example: rust/first-counter/Cargo.toml -->
```toml
[package]
name = "determa-first-counter"
version = "0.2.0"
edition = "2021"
publish = false

[dependencies]
determa-state = "=0.2.0"
```

The Rust program uses the same machine file and asserts the same count and
dispositions.

<!-- determa-example: rust/first-counter/src/main.rs -->
```rust
use determa_state::{
    create, dispatch, load_bundle, Bindings, Delivery, Disposition, Envelope, Target,
    Value,
};
use std::{collections::BTreeMap, env, fs};

fn input(state: &determa_state::AggregateState, amount: i64, sequence: u8) -> Delivery {
    Delivery::Input(Envelope {
        event: "increment".to_string(),
        event_id: format!("tutorial-counter:increment:{sequence}"),
        target: Target::Root {
            root_instance_id: state.root_instance_id.clone(),
            root_runtime_id: state.root.runtime_id.clone(),
        },
        payload: BTreeMap::from([("amount".to_string(), Value::Int(amount))]),
        correlation_id: None,
    })
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let machine_path = env::args().nth(1).expect("machine path");
    let bundle = load_bundle(&fs::read_to_string(machine_path)?)?;
    let created = create(
        &bundle,
        "counter",
        "tutorial-counter",
        "tutorial-counter:create",
        &Bindings::default(),
    );
    let initial = created.state.expect("creation succeeds");

    let accepted = dispatch(&bundle, &initial, Some(input(&initial, 3, 1)));
    assert_eq!(accepted.disposition, Some(Disposition::Handled));
    let state = accepted.state.expect("handled dispatch returns state");
    assert_eq!(state.root.visible_variables()["count"], Value::Int(3));

    let blocked = dispatch(&bundle, &state, Some(input(&state, 8, 2)));
    assert_eq!(blocked.disposition, Some(Disposition::Unhandled));
    assert_eq!(
        blocked.state.expect("unhandled dispatch returns prior state"),
        state
    );
    println!("count=3; next increment was unhandled");
    Ok(())
}
```

Run it with:

```sh
cargo run \
  --manifest-path .cache/examples/rust/first-counter/Cargo.toml \
  -- .cache/examples/machines/first-counter.yaml
```

Both examples are executed during repository validation. They are not illustrative
pseudocode.

## Next

Continue through [core statecharts](../guides/core-statecharts.md), [CEL and
actions](../guides/cel-and-actions.md), [components and spawning](../guides/components-and-spawning.md),
and [effects, faults, and hosting](../guides/effects-faults-hosting.md). Finish with the
[SQLite persistence tutorial](../guides/persistence-and-migration.md) and its
[advanced migration reference lab](../guides/persistence-migration-reference.md).
The [coverage status](../reference/coverage.md) maps the complete released format-1
surface.

Normative references:
[bundle grammar §4](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#4-bundle-grammar),
[CEL §5](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#5-static-validation-and-cel),
and
[dispatch §6](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#6-event-and-transition-semantics).
