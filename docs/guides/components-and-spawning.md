# Components and owned instances

A nested state is part of one state hierarchy. A **component** or **owned spawned
instance** is a separate runtime with its own configuration and variables.

Use a component when the relationship is known when the bundle is written and should
exist only while one parallel state is active. Use `spawn` when an owner must create a
same-bundle machine dynamically.

| Relationship | Created | Lifetime | Address |
|---|---|---|---|
| Nested state | with its hierarchy | enclosing hierarchy | state path |
| Component | on entry to a `parallel` state | that activation of the parallel state | immutable component target |
| Owned instance | by a `spawn` action | its reference holder, explicit cancellation, completion, or owner cascade | nominal `instance_reference` |
| External system | by its host | outside the engine | declared input and output events |

Components and owned instances never share variables or receive implicit broadcasts.
Author-directed communication uses an explicit `send`. Internal sends enqueue an
immutable envelope in the target runtime's mailbox; the application selects that
runtime in a later foreground `step`. External sends return committed intents for
the host to deliver outside the core. Reserved lifecycle
notifications for completion and failure are emitted automatically by the engine.

## 1. Place isolated components

This order coordinator has two reusable lanes. Both receive typed values through
`with`, but each gets a private copy. The coordinator can fan work out to both lanes
and can forward an `env` update to only the inventory lane.

<!-- determa-example: machines/order-components.yaml -->
```yaml
format: 1
namespace: tutorial.components
events:
  begin:
    direction: input
  refresh_inventory:
    direction: input
    payload:
      token: { type: string, required: true }
  finish_inventory:
    direction: input
  finish_receipt:
    direction: input
  restart:
    direction: input
  component_host_work:
    direction: input
  component_work:
    direction: internal
  component_finish:
    direction: internal
machines:
  - machine_id: order_coordinator
    version: 1
    root:
      type: composite
      variables:
        order_id: { type: string, input: true }
        inventory_token: { type: string, external: true }
      initial: { transition_to: idle }
      states:
        idle:
          on_events:
            begin: { transition_to: processing }
        processing:
          type: parallel
          entry:
            - send:
                event: component_work
                targets:
                  - { component: inventory }
                  - { component: receipt }
          on_events:
            refresh_inventory:
              action:
                - send:
                    event: env
                    to: { component: inventory }
                    payload:
                      changed: "{'token': event.payload.token}"
            finish_inventory:
              action:
                - send:
                    event: component_finish
                    to: { component: inventory }
            finish_receipt:
              action:
                - send:
                    event: component_finish
                    to: { component: receipt }
            restart: { transition_to: idle }
            done: { transition_to: fulfilled }
          components:
            - component_id: inventory
              machine_id: processing_lane
              with:
                input:
                  order_id: owner.variables.order_id
                  label: "'inventory'"
                external:
                  token: owner.variables.inventory_token
            - component_id: receipt
              machine_id: processing_lane
              with:
                input:
                  order_id: owner.variables.order_id
                  label: "'receipt'"
                external:
                  token: owner.variables.inventory_token
        fulfilled: { type: final }
  - machine_id: processing_lane
    version: 1
    root:
      type: composite
      variables:
        order_id: { type: string, input: true }
        label: { type: string, input: true }
        token: { type: string, external: true }
        handled: { type: int, init: 0 }
      on_events:
        env:
          action:
            - refresh: { only: [token] }
      initial: { transition_to: waiting }
      states:
        waiting:
          on_events:
            component_work:
              action:
                - assign: { handled: "handled + 1" }
            component_host_work:
              action:
                - assign: { handled: "handled + 1" }
            component_finish: { transition_to: complete }
        complete: { type: final }
```

The placement contract is strict:

1. The engine allocates both component identities.
2. It runs the `processing` entry action. The two sends can target those allocated
   identities, but they do not dispatch recursively.
3. It evaluates each `with.input` map, then each `with.external` map. All expressions
   for one placement see the same owner snapshot.
4. It initializes components in declaration order and commits only after both reach a
   stable configuration.

Missing, extra, or wrongly typed bindings reject the bundle. Synchronous
component/spawn initialization dependencies must also be acyclic; a machine that
creates itself during initialization, directly or through placements, is invalid.

### Deliver fan-out explicitly

The `processing` entry returns two independent `component_work` envelopes in target
order. Delivering the first changes only `inventory.handled`; `receipt.handled` remains
zero until its own envelope is delivered. There is no component queue or subscription
inside the portable core.

The `env` exception is equally narrow. An owner may send one statically checked
`env.changed` map to one component. Delivering that internal envelope updates the
inventory token; it does not update the owner, the receipt component, or an owned
instance with a similar shape.

### Completion, disposal, and re-entry

When a lane reaches its final state, it becomes a retained, inspectable `completed`
component and emits `determa.component_completed` to its owner. When the last lane
completes, that same step emits:

1. `determa.component_completed`; then
2. `done` for the parallel state.

The owner decides whether `done` causes a transition. Here it enters `fulfilled`.
Leaving `processing` disposes both retained components before the owner transition
commits.

Re-entering `processing` allocates new component identities. An envelope captured from
an earlier activation still contains the old complete target and is rejected with
`inactive_component_target`; it can never be redirected to the new lane.

Ordinary host input may target a root or an owned instance, never a component. Even
though `component_host_work` is declared as input and the lane has a handler, an input
envelope using the component target is rejected with `invalid_instance_target` and
leaves state unchanged. The host must send input to the owner, whose behavior can emit
an internal component event.

### Contained faults

A component initialization or event fault rolls back that component step, freezes the
component for diagnostics, and emits `determa.component_failed` to the owner. Other
placements can still initialize. A send already emitted to the now-faulted component
keeps its original identity but later delivery is rejected as inactive.

If the owner handles the failure event, it can leave the parallel state and dispose the
diagnostic component. If it does not, delivery of that reserved failure faults the
owner with `contained_runtime_fault`. A retained-faulted component runs no exit
behavior during cleanup.

## 2. Spawn owned workers

The next bundle demonstrates three lifetime choices:

- two workers bound to one state-scoped holder;
- one worker bound to a root-scoped holder; and
- one unbound worker.

<!-- determa-example: machines/owned-workers.yaml -->
```yaml
format: 1
namespace: tutorial.owned_workers
events:
  prepare:
    direction: input
  request_bound_work:
    direction: input
  finish_bound:
    direction: input
  leave:
    direction: input
  cleanup_references:
    direction: input
  finish_owner:
    direction: input
  work:
    direction: internal
  finish_child:
    direction: internal
  worked:
    direction: internal
  child_exited:
    direction: output
    payload:
      label: { type: string, required: true }
machines:
  - machine_id: owner
    version: 1
    root:
      type: composite
      variables:
        root_worker:
          type: instance_reference
          machine_id: worker
          nullable: true
          init: null
        never_assigned:
          type: instance_reference
          machine_id: worker
          nullable: true
          init: null
        reply_count: { type: int, init: 0 }
        completed_count: { type: int, init: 0 }
        cleanup_count: { type: int, init: 0 }
      initial: { transition_to: holding }
      on_events:
        request_bound_work:
          action:
            - send:
                event: work
                to: { instance: root_worker }
        finish_bound:
          action:
            - send:
                event: finish_child
                to: { instance: root_worker }
        cleanup_references:
          action:
            - cancel: { instance: never_assigned }
            - cancel: { instance: root_worker }
            - assign: { cleanup_count: "cleanup_count + 1" }
        worked:
          action:
            - assign: { reply_count: "reply_count + 1" }
        done:
          guard: "event.payload.relationship == 'spawned_instance'"
          action:
            - assign: { completed_count: "completed_count + 1" }
      states:
        holding:
          variables:
            scoped_worker:
              type: instance_reference
              machine_id: worker
              nullable: true
              init: null
          on_events:
            prepare:
              action:
                - spawn:
                    machine_id: worker
                    bindings:
                      input: { label: "'scoped-one'" }
                    bind_to: scoped_worker
                - assign: { scoped_worker: "null" }
                - spawn:
                    machine_id: worker
                    bindings:
                      input: { label: "'scoped-two'" }
                    bind_to: scoped_worker
                - assign: { scoped_worker: "null" }
                - spawn:
                    machine_id: worker
                    bindings:
                      input: { label: "'root-bound'" }
                    bind_to: root_worker
                - spawn:
                    machine_id: worker
                    bindings:
                      input: { label: "'unbound'" }
            leave: { transition_to: outside }
        outside:
          on_events:
            finish_owner: { transition_to: complete }
        complete: { type: final }
  - machine_id: worker
    version: 1
    root:
      type: composite
      variables:
        label: { type: string, input: true }
        handled: { type: int, init: 0 }
      exit:
        - send:
            event: child_exited
            to: { external: true }
            payload: { label: label }
            correlation_id: "'worker-cleanup'"
      initial: { transition_to: ready }
      states:
        ready:
          on_events:
            work:
              action:
                - assign: { handled: "handled + 1" }
                - send:
                    event: worked
                    to: { owner: true }
            finish_child: { transition_to: complete }
        complete: { type: final }
```

### Bind and address by nominal identity

`spawn` creates and initializes the child in the owner's RTC step. `bind_to` writes a
non-null nominal reference only when the compatible holder is null. Its logical value
has exactly four fields:

```text
{
  root_instance_id,
  instance_id,
  machine_id,
  machine_version
}
```

All four fields participate in equality and target identity. It is not a user-created
string or a lookup by `machine_id`. Changing any field in a delivered target causes
`invalid_instance_target`.

`to: { instance: root_worker }` evaluates the reference and returns a targeted
internal envelope. The worker's `to: { owner: true }` reply targets its immediate
owner. `owner` is valid syntax for a reusable machine, but executing it in the
aggregate root faults because the root has no owner.

Contained runtimes can use the same pattern recursively: a spawned child may spawn its
own child, target it through a nominal reference, and receive the reply at its own
owner target.

### Holder lifetime is independent of the current value

The declaration used by `bind_to`, not the current variable contents, is the lifetime
holder. Clearing `scoped_worker` and reusing it does not detach either worker. Leaving
`holding` disposes both in spawn order before the state's exit action would run.

The root-scoped worker survives that transition. The unbound worker also survives
because it has no holder. It participates in owner/root completion cleanup.

A spawn that tries to bind a reference destroyed by the same transition is rejected at
load with `destroyed_reference_binding`. This prevents a newly created child from
starting with no valid lifetime contract.

### Cancellation and completion

`cancel` is intentionally idempotent:

- a live owned target is synchronously cascaded and disposed;
- a retained-faulted owned target is disposed without running frozen author exits;
- null, already disposed, foreign, or otherwise non-targetable values are successful
  no-ops.

The two cancels in `cleanup_references` therefore let the following assignment run
after the bound worker has completed: `never_assigned` is null and `root_worker` is a
retained but non-targetable reference.

Natural child completion has exact observable order:

1. actions before completion;
2. descendant cleanup;
3. active exits, including the `child_exited` output above;
4. reserved spawned-instance `done` to the immediate owner; then
5. disposal of the completed child.

The holder retains the nominal value for comparison and serialization, but it no
longer targets a runtime.

When the owner reaches its root final state, it uses the same postorder cascade for all
remaining children. In this example the unbound worker exits during that cascade. The
completed root retains terminal identity and diagnostics but no variables, components,
or owned instances.

### Exit-time rules

Automatic holder cleanup happens before the declaring state's exit actions.
Consequently:

- cancelling the now-disposed reference from an exit action is a harmless no-op;
- sending to that disposed instance from an exit action faults with
  `invalid_instance_target`;
- sending to a disposed component faults with `inactive_component_target`; and
- `spawn` is invalid in exit behavior, because it would create an orphan after cleanup.

Every cascade uses one deterministic order: component children first in the
specification's descending placement order, then bound and unbound spawned children in
the canonical holder/spawn order, recursively before their parent. If any eligible exit
action faults, the whole enclosing lifecycle step rolls back.

## 3. Run both traces with Python

The Python trace creates each aggregate, admits host input, and selects queued
runtime work explicitly. Internal sends already occupy the target mailbox; the trace
calls `step` instead of re-admitting them. Earlier FIFO entries are consumed before
a later selected delivery. All inspection reads the public version-1 typed projection.

<!-- determa-example: python/components_and_spawning.py -->
```python
from pathlib import Path
import sys
import determa.state as ds


def root_target(state):
    return {
        "root": {
            "root_instance_id": state["root_instance_id"],
            "root_runtime_id": state["root_runtime_id"],
        }
    }


def input_delivery(state, event, event_id, payload=None, target=None):
    return ds.portable_envelope(
        event, event_id, target or root_target(state), payload or {}
    )


def resolver(bundle):
    return ds.MemoryArtifactResolver(definitions={bundle.fingerprint: bundle})


def admit_delivery(bundle, state, envelope, mode="input"):
    delivery = {
        "delivery_mode": mode,
        "envelope": envelope,
        "envelope_digest": ds.delivery_request_digest(
            state["root_instance_id"], mode, envelope
        ),
    }
    return ds.admit(state, [delivery], resolver(bundle))


def root_runtime(state):
    return next(
        (
            item
            for item in state["runtimes"]
            if item["runtime_id"] == state["root_runtime_id"]
        )
    )


def components(state):
    return {
        item["target_identity"]["component"]["component_id"]: item
        for item in state["runtimes"]
        if item["relation"]["kind"] == "component"
    }


def component(state, component_id):
    return components(state)[component_id]


def owned(state):
    return [
        item
        for item in state["runtimes"]
        if item["relation"]["kind"] == "owned_spawned_instance"
    ]


def decode(value):
    if value[0] == "integer":
        return int(value[1])
    if value[0] == "map":
        return {name: decode(item) for name, item in value[1]}
    if value[0] == "list":
        return [decode(item) for item in value[1]]
    return None if value[0] == "null" else value[1]


def runtime_variables(runtime):
    return {
        item["variable_declaration_pointer"].rsplit("/", 1)[1]: decode(item["value"])
        for item in runtime["variables"]
    }


def envelope_for_emission(state, emission):
    return next(
        (
            entry["envelope"]
            for item in state["runtimes"]
            for entry in item["ready_mailbox"]
            if entry["envelope"]["event_id"] == emission["event_id"]
        )
    )


def event_for_emission(state, emission):
    return (
        emission["event"]
        if "event" in emission
        else envelope_for_emission(state, emission)["event"]
    )


def step_until(bundle, state, runtime_id, event_id):
    while True:
        runtime = next(
            (item for item in state["runtimes"] if item["runtime_id"] == runtime_id)
        )
        head = runtime["ready_mailbox"][0]["envelope"]["event_id"]
        result = ds.step(state, runtime_id, resolver(bundle))
        state = result["state"]
        if head == event_id:
            return result


def step_emission(bundle, state, emission):
    target_runtime = next(
        (
            item
            for item in state["runtimes"]
            if any(
                (
                    entry["envelope"]["event_id"] == emission["event_id"]
                    for entry in item["ready_mailbox"]
                )
            )
        )
    )
    return step_until(bundle, state, target_runtime["runtime_id"], emission["event_id"])


def send_input(bundle, state, event, sequence, payload=None):
    envelope = input_delivery(state, event, f"tutorial:{sequence}", payload=payload)
    admitted = admit_delivery(bundle, state, envelope)
    assert admitted["result"] == "accepted"
    result = step_until(
        bundle, admitted["state"], state["root_runtime_id"], envelope["event_id"]
    )
    assert result["disposition"] == "handled"
    return result


def run_components(machine_path):
    bundle = ds.load_bundle(Path(machine_path).read_text())
    created = ds.create(
        bundle,
        machine_id="order_coordinator",
        root_instance_id="order-42",
        creation_id="order-42:create",
        bindings={
            "input": {"order_id": "ORD-42"},
            "external": {"inventory_token": "token-1"},
        },
    )
    state = created["state"]
    started = send_input(bundle, state, "begin", "components:begin")
    state = started["state"]
    first_activation = started["emissions"]
    assert [event_for_emission(state, item) for item in first_activation] == [
        "component_work",
        "component_work",
    ]
    stale_envelope = envelope_for_emission(state, first_activation[1])
    assert runtime_variables(component(state, "inventory"))["handled"] == 0
    assert runtime_variables(component(state, "receipt"))["handled"] == 0
    inventory_work = step_emission(bundle, state, first_activation[0])
    state = inventory_work["state"]
    assert runtime_variables(component(state, "inventory"))["handled"] == 1
    assert runtime_variables(component(state, "receipt"))["handled"] == 0
    refreshed = send_input(
        bundle, state, "refresh_inventory", "components:refresh", {"token": "token-2"}
    )
    state = refreshed["state"]
    applied = step_emission(bundle, state, refreshed["emissions"][0])
    state = applied["state"]
    assert runtime_variables(component(state, "inventory"))["token"] == "token-2"
    assert runtime_variables(component(state, "receipt"))["token"] == "token-1"
    restarted = send_input(bundle, state, "restart", "components:restart")
    state = restarted["state"]
    assert components(state) == {}
    second_activation = send_input(bundle, state, "begin", "components:begin-again")
    state = second_activation["state"]
    stale = admit_delivery(bundle, state, stale_envelope, "internal")
    assert stale["result"] == "rejected"
    assert stale["rejection"]["code"] == "invalid_instance_target"
    assert stale["state"] == state
    current_inventory = component(state, "inventory")
    direct_host = admit_delivery(
        bundle,
        state,
        input_delivery(
            state,
            "component_host_work",
            "components:direct-host",
            target={
                "component": {
                    "root_instance_id": state["root_instance_id"],
                    "owner_runtime_id": state["root_runtime_id"],
                    "component_id": "inventory",
                    "component_runtime_id": current_inventory["runtime_id"],
                    "activation_sequence": current_inventory["target_identity"][
                        "component"
                    ]["activation_sequence"],
                }
            },
        ),
    )
    assert direct_host["result"] == "rejected"
    assert direct_host["rejection"]["code"] == "invalid_instance_target"
    assert direct_host["state"] == state
    left = send_input(
        bundle, state, "finish_inventory", "components:finish-inventory"
    )
    left_done = step_emission(bundle, left["state"], left["emissions"][0])
    state = left_done["state"]
    assert component(state, "inventory")["status"] == "completed"
    assert component(state, "receipt")["status"] == "running"
    right = send_input(bundle, state, "finish_receipt", "components:finish-receipt")
    right_done = step_emission(bundle, right["state"], right["emissions"][0])
    assert [
        event_for_emission(right_done["state"], item)
        for item in right_done["emissions"]
    ] == ["determa.component_completed", "done"]
    finished = step_emission(bundle, right_done["state"], right_done["emissions"][1])
    assert finished["status"] == "completed"
    assert components(finished["state"]) == {}
    return "components: isolated, refreshed, stale target rejected, completed"


def run_owned(machine_path):
    bundle = ds.load_bundle(Path(machine_path).read_text())
    created = ds.create(
        bundle,
        machine_id="owner",
        root_instance_id="owner-7",
        creation_id="owner-7:create",
        bindings={},
    )
    state = created["state"]
    prepared = send_input(bundle, state, "prepare", "owned:prepare")
    state = prepared["state"]
    assert len(owned(state)) == 4
    root_worker = runtime_variables(root_runtime(state))["root_worker"]
    assert set(root_worker) == {
        "root_instance_id",
        "instance_id",
        "machine_id",
        "machine_version",
    }
    requested = send_input(bundle, state, "request_bound_work", "owned:request")
    worked = step_emission(bundle, requested["state"], requested["emissions"][0])
    replied = step_emission(bundle, worked["state"], worked["emissions"][0])
    state = replied["state"]
    assert runtime_variables(root_runtime(state))["reply_count"] == 1
    left = send_input(bundle, state, "leave", "owned:leave")
    state = left["state"]
    assert [decode(item["payload"])["label"] for item in left["emissions"]] == [
        "scoped-one",
        "scoped-two",
    ]
    assert len(owned(state)) == 2
    finish_request = send_input(bundle, state, "finish_bound", "owned:finish-bound")
    completed = step_emission(
        bundle, finish_request["state"], finish_request["emissions"][0]
    )
    assert [
        event_for_emission(completed["state"], item) for item in completed["emissions"]
    ] == ["child_exited", "done"]
    state = completed["state"]
    assert len(owned(state)) == 1
    completion_seen = step_emission(bundle, state, completed["emissions"][1])
    state = completion_seen["state"]
    assert runtime_variables(root_runtime(state))["completed_count"] == 1
    cleaned = send_input(bundle, state, "cleanup_references", "owned:cleanup")
    state = cleaned["state"]
    assert runtime_variables(root_runtime(state))["cleanup_count"] == 1
    assert len(owned(state)) == 1
    owner_done = send_input(bundle, state, "finish_owner", "owned:finish-owner")
    assert owner_done["status"] == "completed"
    assert [decode(item["payload"])["label"] for item in owner_done["emissions"]] == [
        "unbound"
    ]
    assert owned(owner_done["state"]) == []
    return "owned: 4 spawned, 2 scoped disposed, bound completed, unbound cascaded"


if len(sys.argv) != 3:
    raise SystemExit("usage: components_and_spawning.py COMPONENTS_YAML OWNED_YAML")
print(run_components(sys.argv[1]))
print(run_owned(sys.argv[2]))
```

Expected output:

```text
components: isolated, refreshed, stale target rejected, completed
owned: 4 spawned, 2 scoped disposed, bound completed, unbound cascaded
```

## 4. Run the matching Rust trace

The Rust program consumes the same two bundles and asserts the same state changes,
emission order, stale-target rejection, and final output.

<!-- determa-example: rust/components-spawning/Cargo.toml -->
```toml
[package]
name = "determa-components-spawning"
version = "0.3.0"
edition = "2021"
publish = false

[dependencies]
determa-state = { git = "https://github.com/fruwehq/determa-state-rust", rev = "efaed0a21409f75ed55f159a6f8c833f3b62e88c" }
serde_json = "1"
serde_json_canonicalizer = "0.3"
sha2 = "0.10"
```

<!-- determa-example: rust/components-spawning/src/main.rs -->
```rust
use determa_state::{admit, create, load_bundle, restore_aggregate, step,
    AdmissionDelivery, Aggregate, Bindings, Bundle, InMemoryDefinitionResolver, Value as NativeValue,
    QueueEnvelope, TypedValue};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, env, fs};

fn load(path: &str) -> Bundle {
    load_bundle(&fs::read_to_string(path).unwrap()).unwrap()
}

fn root(state: &Aggregate) -> &Value {
    state.value()["runtimes"].as_array().unwrap().iter()
        .find(|runtime| runtime["runtime_id"] == state.value()["root_runtime_id"]).unwrap()
}

fn variable(state: &Aggregate, name: &str) -> Option<Value> {
    root(state)["variables"].as_array().unwrap().iter()
        .filter(|variable| variable["variable_declaration_pointer"].as_str().unwrap()
            .ends_with(&format!("/variables/{name}")))
        .max_by_key(|variable| variable["variable_declaration_pointer"].as_str().unwrap().len())
        .map(|variable| variable["value"].clone())
}

fn typed(value: &Value) -> TypedValue {
    match value {
        Value::Null => TypedValue::Null,
        Value::Bool(value) => TypedValue::Boolean(*value),
        Value::String(value) => TypedValue::String(value.clone()),
        Value::Number(value) => if value.is_i64() { TypedValue::Integer(value.as_i64().unwrap()) } else { TypedValue::Float(value.as_f64().unwrap()) },
        Value::Array(values) => TypedValue::List(values.iter().map(typed).collect()),
        Value::Object(values) => TypedValue::Map(values.iter().map(|(name, value)| (name.clone(), typed(value))).collect()),
    }
}

fn decode(value: &Value) -> Value {
    match value[0].as_str().unwrap() {
        "null" => Value::Null,
        "integer" => json!(value[1].as_str().unwrap().parse::<i64>().unwrap()),
        "float" => json!(f64::from_bits(u64::from_str_radix(value[1].as_str().unwrap(), 16).unwrap())),
        "list" => Value::Array(value[1].as_array().unwrap().iter().map(decode).collect()),
        "map" => Value::Object(value[1].as_array().unwrap().iter().map(|item|
            (item[0].as_str().unwrap().to_owned(), decode(&item[1]))).collect()),
        _ => value[1].clone(),
    }
}

fn logical(state: &Aggregate, name: &str) -> Value { decode(&variable(state, name).unwrap()) }

fn restored(bundle: &Bundle, result: &Value) -> Aggregate {
    let mut resolver = InMemoryDefinitionResolver::default();
    resolver.insert(bundle.clone(), true);
    restore_aggregate(&serde_json_canonicalizer::to_vec(&result["state"]).unwrap(), &resolver).unwrap()
}

fn component<'a>(state: &'a Aggregate, name: &str) -> &'a Value {
    state.value()["runtimes"].as_array().unwrap().iter().find(|runtime|
        runtime["target_identity"]["component"]["component_id"] == name).unwrap()
}

fn owned_count(state: &Aggregate) -> usize {
    state.value()["runtimes"].as_array().unwrap().iter().filter(|runtime|
        runtime["relation"]["kind"] == "owned_spawned_instance").count()
}

fn runtime_variable(runtime: &Value, name: &str) -> Value {
    decode(&runtime["variables"].as_array().unwrap().iter().find(|variable|
        variable["variable_declaration_pointer"].as_str().unwrap().ends_with(&format!("/variables/{name}"))).unwrap()["value"])
}

fn envelope_for(state: &Aggregate, emission: &Value) -> Value {
    state.value()["runtimes"].as_array().unwrap().iter().flat_map(|runtime|
        runtime["ready_mailbox"].as_array().unwrap().iter()).find(|entry|
        entry["envelope"]["event_id"] == emission["event_id"]).unwrap()["envelope"].clone()
}

fn event_for(state: &Aggregate, emission: &Value) -> Value {
    if emission.get("event").is_some() { emission["event"].clone() }
    else { envelope_for(state, emission)["event"].clone() }
}

fn admission(bundle: &Bundle, state: &Aggregate, envelope: QueueEnvelope, mode: &str) -> Result<Value, determa_state::ArtifactError> {
    let bytes = serde_json_canonicalizer::to_vec(&json!([
        "determa-inbox-envelope-digest-1", "1", state.value()["root_instance_id"], mode, envelope,
    ])).unwrap();
    admit(bundle, state, &[AdmissionDelivery { delivery_mode: mode.into(), envelope,
        envelope_digest: format!("sha256:{:x}", Sha256::digest(bytes)) }])
}

fn step_until(bundle: &Bundle, state: &Aggregate, runtime_id: &str, event_id: &str) -> (Aggregate, Value) {
    let mut state = state.clone();
    loop {
        let runtime = state.value()["runtimes"].as_array().unwrap().iter()
            .find(|runtime| runtime["runtime_id"] == runtime_id).unwrap();
        let head = runtime["ready_mailbox"][0]["envelope"]["event_id"].as_str().unwrap().to_owned();
        let result = step(bundle, &state, runtime_id).unwrap();
        state = restored(bundle, &result);
        if head == event_id { return (state, result); }
    }
}

fn step_emission(bundle: &Bundle, state: &Aggregate, emission: &Value) -> (Aggregate, Value) {
    let runtime = state.value()["runtimes"].as_array().unwrap().iter().find(|runtime|
        runtime["ready_mailbox"].as_array().unwrap().iter().any(|entry|
            entry["envelope"]["event_id"] == emission["event_id"])).unwrap();
    step_until(bundle, state, runtime["runtime_id"].as_str().unwrap(), emission["event_id"].as_str().unwrap())
}

fn input(bundle: &Bundle, state: &Aggregate, event: &str, sequence: u8, payload: Value) -> (Aggregate, Value) {
    let event_id = format!("tutorial-components:{sequence}");
    let envelope = QueueEnvelope { event: event.into(), event_id: event_id.clone(), cause_id: event_id.clone(),
        source: json!({"host": true}), target: root(state)["target_identity"].clone(), payload: typed(&payload), correlation_id: None };
    let accepted = admission(bundle, state, envelope, "input").unwrap();
    assert_eq!(accepted["result"], "accepted");
    let state = restored(bundle, &accepted);
    let (next, result) = step_until(bundle, &state, state.value()["root_runtime_id"].as_str().unwrap(), &event_id);
    assert_eq!(result["disposition"], "handled");
    (next, result)
}

fn main() {
    let paths: Vec<String> = env::args().skip(1).collect();
    let bundle = load(&paths[0]);
    let bindings = Bindings {
        input: BTreeMap::from([("order_id".into(), NativeValue::String("ORD-42".into()))]),
        external: BTreeMap::from([("inventory_token".into(), NativeValue::String("token-1".into()))]),
    };
    let state = create(&bundle, "order_coordinator", "order-42", "order-42:create", &bindings).unwrap();
    let (mut state, started) = input(&bundle, &state, "begin", 1, json!({}));
    let first = &started["emissions"];
    assert_eq!(first.as_array().unwrap().iter().map(|emission| event_for(&state, emission)).collect::<Vec<_>>(), vec![json!("component_work"), json!("component_work")]);
    let stale_envelope: QueueEnvelope = serde_json::from_value(envelope_for(&state, &first[1])).unwrap();
    assert_eq!(runtime_variable(component(&state, "inventory"), "handled"), json!(0));
    assert_eq!(runtime_variable(component(&state, "receipt"), "handled"), json!(0));
    state = step_emission(&bundle, &state, &first[0]).0;
    assert_eq!(runtime_variable(component(&state, "inventory"), "handled"), json!(1));
    assert_eq!(runtime_variable(component(&state, "receipt"), "handled"), json!(0));
    let (next, refresh) = input(&bundle, &state, "refresh_inventory", 2, json!({"token": "token-2"}));
    state = step_emission(&bundle, &next, &refresh["emissions"][0]).0;
    assert_eq!(runtime_variable(component(&state, "inventory"), "token"), "token-2");
    assert_eq!(runtime_variable(component(&state, "receipt"), "token"), "token-1");
    state = input(&bundle, &state, "restart", 3, json!({})).0;
    assert!(state.value()["runtimes"].as_array().unwrap().iter().all(|runtime| runtime["relation"]["kind"] != "component"));
    state = input(&bundle, &state, "begin", 4, json!({})).0;
    let before_rejections = state.value().clone();
    let stale = admission(&bundle, &state, stale_envelope, "internal").unwrap_err();
    assert_eq!(stale.code, "invalid_instance_target");
    assert_eq!(&before_rejections, state.value());
    let host_envelope = QueueEnvelope {
        event: "component_host_work".into(), event_id: "direct-host".into(), cause_id: "direct-host".into(),
        source: json!({"host": true}), target: component(&state, "inventory")["target_identity"].clone(),
        payload: TypedValue::Map(vec![]), correlation_id: None,
    };
    let direct = admission(&bundle, &state, host_envelope, "input").unwrap_err();
    assert_eq!(direct.code, "invalid_instance_target");
    assert_eq!(&before_rejections, state.value());
    let (next, left) = input(&bundle, &state, "finish_inventory", 5, json!({}));
    state = step_emission(&bundle, &next, &left["emissions"][0]).0;
    assert_eq!(component(&state, "inventory")["status"], "completed");
    assert_eq!(component(&state, "receipt")["status"], "running");
    let (next, right) = input(&bundle, &state, "finish_receipt", 6, json!({}));
    let (next, right_done) = step_emission(&bundle, &next, &right["emissions"][0]);
    assert_eq!(right_done["emissions"].as_array().unwrap().iter().map(|emission| event_for(&next, emission)).collect::<Vec<_>>(), vec![json!("determa.component_completed"), json!("done")]);
    let (state, finished) = step_emission(&bundle, &next, &right_done["emissions"][1]);
    assert_eq!(finished["status"], "completed");
    assert!(state.value()["runtimes"].as_array().unwrap().iter().all(|runtime| runtime["relation"]["kind"] != "component"));
    println!("components: isolated, refreshed, stale target rejected, completed");

    let bundle = load(&paths[1]);
    let state = create(&bundle, "owner", "owner-7", "owner-7:create", &Bindings::default()).unwrap();
    let mut state = input(&bundle, &state, "prepare", 20, json!({})).0;
    assert_eq!(owned_count(&state), 4);
    assert_eq!(logical(&state, "root_worker")["machine_id"], "worker");
    let (next, request) = input(&bundle, &state, "request_bound_work", 21, json!({}));
    let (next, worked) = step_emission(&bundle, &next, &request["emissions"][0]);
    state = step_emission(&bundle, &next, &worked["emissions"][0]).0;
    assert_eq!(logical(&state, "reply_count"), json!(1));
    let (next, left) = input(&bundle, &state, "leave", 22, json!({}));
    state = next;
    assert_eq!(left["emissions"].as_array().unwrap().iter().map(|emission| decode(&emission["payload"])["label"].clone()).collect::<Vec<_>>(), vec![json!("scoped-one"), json!("scoped-two")]);
    assert_eq!(owned_count(&state), 2);
    let (next, finish) = input(&bundle, &state, "finish_bound", 23, json!({}));
    let (next, completed) = step_emission(&bundle, &next, &finish["emissions"][0]);
    assert_eq!(completed["emissions"].as_array().unwrap().iter().map(|emission| event_for(&next, emission)).collect::<Vec<_>>(), vec![json!("child_exited"), json!("done")]);
    assert_eq!(owned_count(&next), 1);
    state = step_emission(&bundle, &next, &completed["emissions"][1]).0;
    assert_eq!(logical(&state, "completed_count"), json!(1));
    state = input(&bundle, &state, "cleanup_references", 24, json!({})).0;
    assert_eq!(logical(&state, "cleanup_count"), json!(1));
    assert_eq!(owned_count(&state), 1);
    let (state, done) = input(&bundle, &state, "finish_owner", 25, json!({}));
    assert_eq!(done["status"], "completed");
    assert_eq!(done["emissions"].as_array().unwrap().iter().map(|emission| decode(&emission["payload"])["label"].clone()).collect::<Vec<_>>(), vec![json!("unbound")]);
    assert_eq!(owned_count(&state), 0);
    println!("owned: 4 spawned, 2 scoped disposed, bound completed, unbound cascaded");
}
```

Run the extracted examples:

```sh
make extract
python .cache/examples/python/components_and_spawning.py \
  .cache/examples/machines/order-components.yaml \
  .cache/examples/machines/owned-workers.yaml
cargo run --quiet \
  --manifest-path .cache/examples/rust/components-spawning/Cargo.toml \
  -- \
  .cache/examples/machines/order-components.yaml \
  .cache/examples/machines/owned-workers.yaml
```

Both programs are part of `make check`; they are not pseudocode.

## 5. Lifecycle edge-case reference

The runnable path above demonstrates the ordinary workflow. These rules complete the
portable lifecycle model:

| Situation | Portable result |
|---|---|
| Component initialization faults | Retain a faulted diagnostic component, emit `determa.component_failed`, continue initializing later placements. |
| Spawned initialization faults | Retain the faulted child and emit `determa.spawned_instance_failed`; a later owner fault rolls the tentative spawn back with its owner step. |
| Unhandled contained failure | Delivering the reserved failure faults the owner with `contained_runtime_fault`. |
| Retained-faulted owned child | Ordinary delivery is rejected; explicit owner cancellation disposes the frozen subtree without author exits. |
| Component completes during initialization | Emit its completion immediately; for the last component, `determa.component_completed` precedes parallel `done`. |
| Component entry sends to itself | The pending identity may be targeted, but delivery happens only after the owner step commits and initialization has finished. |
| State-scoped holder exits | Dispose every child ever bound to that holder activation, even if the variable was cleared or reused. |
| Null or disposed cancellation | Successful no-op; later actions in the same list continue. |
| Direct host-to-component delivery | Reject atomically with `invalid_instance_target`; caller retains the envelope. |
| Old component envelope after re-entry | Refuse its removed runtime identity with `invalid_instance_target`; never retarget the new activation. |
| Root executes `to: { owner: true }` | Fault the root step with `invalid_instance_target`. |

## Coverage

This chapter covers specification
[§7](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#7-components-spawning-and-lifecycle),
[§7.1](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#71-lifecycle-bound-components),
[§7.2](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#72-owned-spawned-instances),
and
[§7.3](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#73-runtime-and-aggregate-root-completion).

The matching pinned 0.3.0 conformance cases are:

- [09 parallel components](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/09-parallel-components)
- [13 spawn completion](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/13-spawn-completion)
- [14 explicit targets](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/14-explicit-targets)
- [29 owned spawn](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/29-owned-spawn)
- [30 owned spawn cancel](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/30-owned-spawn-cancel)
- [38 destroyed reference binding](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/38-destroyed-reference-binding)
- [47 scoped owned-child lifetime](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/47-scoped-owned-child-lifetime)
- [48 null cancel](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/48-null-cancel)
- [49 exit-action cancel](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/49-exit-action-cancel)
- [51 component initialization fault](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/51-component-initialization-fault)
- [52 spawned initialization fault](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/52-spawned-initialization-fault)
- [54 stale component target](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/54-stale-component-target)
- [55 root owner target](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/55-root-owner-target)
- [73 synchronous initialization cycle](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/73-synchronous-initialization-cycle)
- [74 sibling cleanup order](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/74-sibling-cleanup-order)
- [78 component external refresh](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/78-component-external-refresh)
- [80 unbound owned child](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/80-unbound-owned-child)
- [81 holder reference reuse](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/81-holder-reference-reuse)
- [82 instance-reference target identity](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/82-instance-reference-target-identity)
- [83 contained dynamic instance send](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/83-contained-dynamic-instance-send)
- [86 initial component completion order](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/86-initial-component-completion-order)
- [87 internal env target mode](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/87-internal-env-target-mode)
- [91 component host-input rejection](https://github.com/fruwehq/determa-state-conformance/tree/affe3fe3bcc4d13fa7c5374471568e94af36f0d1/conformance/core/91-component-host-input-rejection)

Portable package imports and direct host-to-component input are deliberately not
introduced here.
