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

Install the unreleased candidate from its exact public source commit:

```sh
python -m pip install "git+https://github.com/fruwehq/determa-state-python.git@3b5d1c9a98e8691acd754357d1f3645f387f3ad8"
```

The complete program is below. `create` returns a queue-bearing aggregate.
`admit` accepts an input delivery into its ready mailbox, and `step` processes one
selected runtime’s mailbox head. Each call returns explicit data; your application
owns it. An unhandled input is still consumed from the mailbox, so its disposition
does not mean that the complete aggregate is unchanged.

<!-- determa-example: python/first_counter.py -->
```python
from pathlib import Path
import sys

import determa.state as ds

bundle = ds.load_bundle(Path(sys.argv[1]).read_text())
created = ds.create(
    bundle, machine_id="counter", root_instance_id="tutorial-counter",
    creation_id="tutorial-counter:create", bindings={},
)
assert created["status"] == "running"
state = created["state"]
resolver = ds.MemoryArtifactResolver(definitions={bundle.fingerprint: bundle})


def increment(state, amount, sequence):
    runtime_id = state["root_runtime_id"]
    target = {"root": {
        "root_instance_id": state["root_instance_id"],
        "root_runtime_id": runtime_id,
    }}
    envelope = ds.portable_envelope(
        "increment", f"tutorial-counter:increment:{sequence}", target, {"amount": amount},
    )
    delivery = {
        "delivery_mode": "input", "envelope": envelope,
        "envelope_digest": ds.delivery_request_digest(
            state["root_instance_id"], "input", envelope,
        ),
    }
    admitted = ds.admit(state, [delivery], resolver)
    assert admitted["result"] == "accepted"
    return ds.step(admitted["state"], runtime_id, resolver)


def count(state):
    root = next(runtime for runtime in state["runtimes"]
                if runtime["runtime_id"] == state["root_runtime_id"])
    return next(variable["value"] for variable in root["variables"]
                if variable["variable_declaration_pointer"].endswith("/count"))


accepted = increment(state, 3, 1)
assert accepted["disposition"] == "handled"
state = accepted["state"]
assert count(state) == ["integer", "3"]
blocked = increment(state, 8, 2)
assert blocked["disposition"] == "unhandled"
assert count(blocked["state"]) == ["integer", "3"]
assert blocked["state"]["runtimes"][0]["ready_mailbox"] == []
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

Create a small Cargo project with the same unreleased candidate source.

<!-- determa-example: rust/first-counter/Cargo.toml -->
```toml
[package]
name = "determa-first-counter"
version = "0.3.0"
edition = "2021"
publish = false

[dependencies]
determa-state = { git = "https://github.com/fruwehq/determa-state-rust.git", rev = "efaed0a21409f75ed55f159a6f8c833f3b62e88c" }
serde_json = "1"
serde_json_canonicalizer = "0.3"
sha2 = "0.10"
```

The Rust program uses the same machine file and asserts the same count and
dispositions.

<!-- determa-example: rust/first-counter/src/main.rs -->
```rust
use determa_state::{
    admit, create, load_bundle, restore_aggregate, step, AdmissionDelivery,
    Bindings, InMemoryDefinitionResolver, QueueEnvelope, TypedValue,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, fs};

fn increment(
    bundle: &determa_state::Bundle,
    state: &determa_state::Aggregate,
    amount: i64,
    sequence: u8,
) -> Result<Value, Box<dyn std::error::Error>> {
    let envelope = QueueEnvelope {
        event: "increment".into(),
        event_id: format!("tutorial-counter:increment:{sequence}"),
        cause_id: format!("tutorial-counter:increment:{sequence}"),
        source: json!({"host": true}),
        target: state.value()["runtimes"][0]["target_identity"].clone(),
        payload: TypedValue::Map(vec![("amount".into(), TypedValue::Integer(amount))]),
        correlation_id: None,
    };
    let digest_bytes = serde_json_canonicalizer::to_vec(&json!([
        "determa-inbox-envelope-digest-1", "1", "tutorial-counter", "input", envelope
    ]))?;
    let delivery = AdmissionDelivery {
        delivery_mode: "input".into(), envelope,
        envelope_digest: format!("sha256:{:x}", Sha256::digest(digest_bytes)),
    };
    let admitted = admit(bundle, state, &[delivery])?;
    assert_eq!(admitted["result"], "accepted");
    let mut resolver = InMemoryDefinitionResolver::default();
    resolver.insert(bundle.clone(), true);
    let state = restore_aggregate(
        &serde_json_canonicalizer::to_vec(&admitted["state"])? , &resolver,
    )?;
    let runtime_id = state.value()["root_runtime_id"].as_str().unwrap();
    Ok(step(bundle, &state, runtime_id)?)
}

fn count(state: &Value) -> Value {
    state["runtimes"][0]["variables"].as_array().unwrap().iter()
        .find(|variable| variable["variable_declaration_pointer"].as_str().unwrap()
            .ends_with("/count")).unwrap()["value"].clone()
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let machine_path = env::args().nth(1).expect("machine path");
    let bundle = load_bundle(&fs::read_to_string(machine_path)?)?;
    let initial = create(
        &bundle, "counter", "tutorial-counter", "tutorial-counter:create", &Bindings::default(),
    )?;
    let accepted = increment(&bundle, &initial, 3, 1)?;
    assert_eq!(accepted["disposition"], "handled");
    assert_eq!(count(&accepted["state"]), json!(["integer", "3"]));
    let mut resolver = InMemoryDefinitionResolver::default();
    resolver.insert(bundle.clone(), true);
    let state = restore_aggregate(
        &serde_json_canonicalizer::to_vec(&accepted["state"])? , &resolver,
    )?;
    let blocked = increment(&bundle, &state, 8, 2)?;
    assert_eq!(blocked["disposition"], "unhandled");
    assert_eq!(count(&blocked["state"]), json!(["integer", "3"]));
    assert_eq!(blocked["state"]["runtimes"][0]["ready_mailbox"], json!([]));
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
[bundle grammar §4](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#4-bundle-grammar),
[CEL §5](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#5-static-validation-and-cel),
and
[dispatch §6](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#6-event-and-transition-semantics).
