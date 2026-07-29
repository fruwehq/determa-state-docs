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
Author-directed communication uses an explicit `send`, returned as an immutable
emission for the host to deliver in a later foreground call. Reserved lifecycle
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

The Python trace creates each aggregate, delivers returned internal emissions
explicitly, and inspects only public logical state.

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
    return {
        "input": {
            "event": event,
            "event_id": event_id,
            "target": target or root_target(state),
            "payload": payload or {},
        }
    }


def internal_delivery(emission):
    envelope = {
        "event": emission["event"],
        "event_id": emission["event_id"],
        "target": emission["target"],
        "payload": emission["payload"],
    }
    if emission.get("correlation_id") is not None:
        envelope["correlation_id"] = emission["correlation_id"]
    return {"internal": envelope}


def root_runtime(state):
    return state["runtimes"][state["root_runtime_id"]]


def component(state, component_id):
    root = root_runtime(state)
    return state["runtimes"][root["components"][component_id]]


def owned(state):
    return [
        runtime
        for runtime in state["runtimes"].values()
        if runtime["role"] == "spawned"
    ]


def dispatch_input(bundle, state, event, sequence, payload=None):
    result = ds.dispatch(
        bundle,
        state,
        input_delivery(
            state,
            event,
            f"tutorial:{sequence}",
            payload=payload,
        ),
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

    started = dispatch_input(bundle, state, "begin", "components:begin")
    state = started["state"]
    first_activation = started["emissions"]
    assert [item["event"] for item in first_activation] == [
        "component_work",
        "component_work",
    ]
    assert component(state, "inventory")["scopes"]["root"]["handled"] == 0
    assert component(state, "receipt")["scopes"]["root"]["handled"] == 0

    inventory_work = ds.dispatch(
        bundle, state, internal_delivery(first_activation[0])
    )
    state = inventory_work["state"]
    assert component(state, "inventory")["scopes"]["root"]["handled"] == 1
    assert component(state, "receipt")["scopes"]["root"]["handled"] == 0

    refreshed = dispatch_input(
        bundle,
        state,
        "refresh_inventory",
        "components:refresh",
        {"token": "token-2"},
    )
    state = refreshed["state"]
    applied = ds.dispatch(
        bundle, state, internal_delivery(refreshed["emissions"][0])
    )
    state = applied["state"]
    assert component(state, "inventory")["scopes"]["root"]["token"] == "token-2"
    assert component(state, "receipt")["scopes"]["root"]["token"] == "token-1"

    restarted = dispatch_input(bundle, state, "restart", "components:restart")
    state = restarted["state"]
    assert root_runtime(state)["components"] == {}
    second_activation = dispatch_input(
        bundle, state, "begin", "components:begin-again"
    )
    state = second_activation["state"]

    stale = ds.dispatch(bundle, state, internal_delivery(first_activation[1]))
    assert stale["disposition"] == "rejected"
    assert stale["rejection"]["code"] == "inactive_component_target"
    assert stale["state"] == state

    current_inventory = component(state, "inventory")
    direct_host = ds.dispatch(
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
                    "activation_sequence": current_inventory[
                        "component_activation_sequence"
                    ],
                }
            },
        ),
    )
    assert direct_host["disposition"] == "rejected"
    assert direct_host["rejection"]["code"] == "invalid_instance_target"
    assert direct_host["state"] == state

    left = dispatch_input(
        bundle, state, "finish_inventory", "components:finish-inventory"
    )
    left_done = ds.dispatch(
        bundle, left["state"], internal_delivery(left["emissions"][0])
    )
    state = left_done["state"]
    assert component(state, "inventory")["status"] == "completed"
    assert component(state, "receipt")["status"] == "running"

    right = dispatch_input(
        bundle, state, "finish_receipt", "components:finish-receipt"
    )
    right_done = ds.dispatch(
        bundle, right["state"], internal_delivery(right["emissions"][0])
    )
    assert [item["event"] for item in right_done["emissions"]] == [
        "determa.component_completed",
        "done",
    ]
    finished = ds.dispatch(
        bundle,
        right_done["state"],
        internal_delivery(right_done["emissions"][1]),
    )
    assert finished["status"] == "completed"
    assert root_runtime(finished["state"])["components"] == {}
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

    prepared = dispatch_input(bundle, state, "prepare", "owned:prepare")
    state = prepared["state"]
    assert len(owned(state)) == 4
    root_worker = root_runtime(state)["scopes"]["root"]["root_worker"]
    assert set(root_worker) == {
        "root_instance_id",
        "instance_id",
        "machine_id",
        "machine_version",
    }

    requested = dispatch_input(
        bundle, state, "request_bound_work", "owned:request"
    )
    worked = ds.dispatch(
        bundle, requested["state"], internal_delivery(requested["emissions"][0])
    )
    replied = ds.dispatch(
        bundle, worked["state"], internal_delivery(worked["emissions"][0])
    )
    state = replied["state"]
    assert root_runtime(state)["scopes"]["root"]["reply_count"] == 1

    left = dispatch_input(bundle, state, "leave", "owned:leave")
    state = left["state"]
    assert [item["payload"]["label"] for item in left["emissions"]] == [
        "scoped-one",
        "scoped-two",
    ]
    assert len(owned(state)) == 2

    finish_request = dispatch_input(
        bundle, state, "finish_bound", "owned:finish-bound"
    )
    completed = ds.dispatch(
        bundle,
        finish_request["state"],
        internal_delivery(finish_request["emissions"][0]),
    )
    assert [item["event"] for item in completed["emissions"]] == [
        "child_exited",
        "done",
    ]
    state = completed["state"]
    assert len(owned(state)) == 1
    completion_seen = ds.dispatch(
        bundle, state, internal_delivery(completed["emissions"][1])
    )
    state = completion_seen["state"]
    assert root_runtime(state)["scopes"]["root"]["completed_count"] == 1

    cleaned = dispatch_input(
        bundle, state, "cleanup_references", "owned:cleanup"
    )
    state = cleaned["state"]
    assert root_runtime(state)["scopes"]["root"]["cleanup_count"] == 1
    assert len(owned(state)) == 1

    owner_done = dispatch_input(
        bundle, state, "finish_owner", "owned:finish-owner"
    )
    assert owner_done["status"] == "completed"
    assert [item["payload"]["label"] for item in owner_done["emissions"]] == [
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
version = "0.1.0"
edition = "2021"
publish = false

[dependencies]
determa-state = "=0.1.0"
```

<!-- determa-example: rust/components-spawning/src/main.rs -->
```rust
use determa_state::{
    create, dispatch, load_bundle, AggregateState, Bindings, Delivery, Disposition,
    Emission, Envelope, RuntimeStatus, Target, Value,
};
use std::{collections::BTreeMap, env, fs};

fn root_target(state: &AggregateState) -> Target {
    Target::Root {
        root_instance_id: state.root_instance_id.clone(),
        root_runtime_id: state.root.runtime_id.clone(),
    }
}

fn input(
    state: &AggregateState,
    event: &str,
    event_id: &str,
    payload: BTreeMap<String, Value>,
) -> Delivery {
    Delivery::Input(Envelope {
        event: event.to_string(),
        event_id: event_id.to_string(),
        target: root_target(state),
        payload,
        correlation_id: None,
    })
}

fn internal(emission: &Emission) -> Delivery {
    Delivery::Internal(
        emission
            .envelope()
            .expect("internal emission has an envelope"),
    )
}

fn component<'a>(
    state: &'a AggregateState,
    component_id: &str,
) -> &'a determa_state::format1::ComponentRuntime {
    state
        .root
        .components
        .iter()
        .find(|item| item.component_id == component_id)
        .expect("component is retained")
}

fn int_variable(
    runtime: &determa_state::format1::RuntimeState,
    name: &str,
) -> i64 {
    match runtime.visible_variables().get(name) {
        Some(Value::Int(value)) => *value,
        other => panic!("{name} is not an int: {other:?}"),
    }
}

fn string_variable(
    runtime: &determa_state::format1::RuntimeState,
    name: &str,
) -> String {
    match runtime.visible_variables().get(name) {
        Some(Value::String(value)) => value.clone(),
        other => panic!("{name} is not a string: {other:?}"),
    }
}

fn handled_input(
    bundle: &determa_state::Bundle,
    state: &AggregateState,
    event: &str,
    event_id: &str,
    payload: BTreeMap<String, Value>,
) -> determa_state::CoreResult {
    let result = dispatch(
        bundle,
        state,
        Some(input(state, event, event_id, payload)),
    );
    assert_eq!(result.disposition, Some(Disposition::Handled));
    result
}

fn run_components(path: &str) -> String {
    let bundle = load_bundle(&fs::read_to_string(path).expect("components bundle"))
        .expect("valid components bundle");
    let bindings = Bindings {
        input: BTreeMap::from([(
            "order_id".to_string(),
            Value::String("ORD-42".to_string()),
        )]),
        external: BTreeMap::from([(
            "inventory_token".to_string(),
            Value::String("token-1".to_string()),
        )]),
    };
    let created = create(
        &bundle,
        "order_coordinator",
        "order-42",
        "order-42:create",
        &bindings,
    );
    let mut state = created.state.expect("creation succeeds");

    let started = handled_input(
        &bundle,
        &state,
        "begin",
        "components:begin",
        BTreeMap::new(),
    );
    state = started.state.expect("begin state");
    let first_activation = started.emissions;
    assert_eq!(
        first_activation
            .iter()
            .map(|item| item.event.as_str())
            .collect::<Vec<_>>(),
        vec!["component_work", "component_work"]
    );
    assert_eq!(int_variable(&component(&state, "inventory").runtime, "handled"), 0);
    assert_eq!(int_variable(&component(&state, "receipt").runtime, "handled"), 0);

    let inventory_work = dispatch(
        &bundle,
        &state,
        Some(internal(&first_activation[0])),
    );
    state = inventory_work.state.expect("inventory work state");
    assert_eq!(int_variable(&component(&state, "inventory").runtime, "handled"), 1);
    assert_eq!(int_variable(&component(&state, "receipt").runtime, "handled"), 0);

    let refreshed = handled_input(
        &bundle,
        &state,
        "refresh_inventory",
        "components:refresh",
        BTreeMap::from([(
            "token".to_string(),
            Value::String("token-2".to_string()),
        )]),
    );
    state = refreshed.state.expect("refresh request state");
    let applied = dispatch(
        &bundle,
        &state,
        Some(internal(&refreshed.emissions[0])),
    );
    state = applied.state.expect("refresh delivery state");
    assert_eq!(
        string_variable(&component(&state, "inventory").runtime, "token"),
        "token-2"
    );
    assert_eq!(
        string_variable(&component(&state, "receipt").runtime, "token"),
        "token-1"
    );

    let restarted = handled_input(
        &bundle,
        &state,
        "restart",
        "components:restart",
        BTreeMap::new(),
    );
    state = restarted.state.expect("restart state");
    assert!(state.root.components.is_empty());
    let second_activation = handled_input(
        &bundle,
        &state,
        "begin",
        "components:begin-again",
        BTreeMap::new(),
    );
    state = second_activation.state.expect("second activation state");

    let stale = dispatch(
        &bundle,
        &state,
        Some(internal(&first_activation[1])),
    );
    assert_eq!(stale.disposition, Some(Disposition::Rejected));
    assert_eq!(
        stale.rejection.expect("stale rejection").code,
        "inactive_component_target"
    );
    assert_eq!(stale.state.as_ref(), Some(&state));

    let current_inventory = component(&state, "inventory");
    let direct_host = dispatch(
        &bundle,
        &state,
        Some(Delivery::Input(Envelope {
            event: "component_host_work".to_string(),
            event_id: "components:direct-host".to_string(),
            target: Target::Component {
                root_instance_id: state.root_instance_id.clone(),
                owner_runtime_id: state.root.runtime_id.clone(),
                component_id: "inventory".to_string(),
                component_runtime_id: current_inventory.runtime.runtime_id.clone(),
                activation_sequence: current_inventory.activation_sequence.clone(),
            },
            payload: BTreeMap::new(),
            correlation_id: None,
        })),
    );
    assert_eq!(direct_host.disposition, Some(Disposition::Rejected));
    assert_eq!(
        direct_host.rejection.expect("host rejection").code,
        "invalid_instance_target"
    );
    assert_eq!(direct_host.state.as_ref(), Some(&state));

    let left = handled_input(
        &bundle,
        &state,
        "finish_inventory",
        "components:finish-inventory",
        BTreeMap::new(),
    );
    let left_state = left.state.expect("left request state");
    let left_done = dispatch(
        &bundle,
        &left_state,
        Some(internal(&left.emissions[0])),
    );
    state = left_done.state.expect("left completion state");
    assert_eq!(
        component(&state, "inventory").runtime.status,
        RuntimeStatus::Completed
    );
    assert_eq!(
        component(&state, "receipt").runtime.status,
        RuntimeStatus::Running
    );

    let right = handled_input(
        &bundle,
        &state,
        "finish_receipt",
        "components:finish-receipt",
        BTreeMap::new(),
    );
    let right_state = right.state.expect("right request state");
    let right_done = dispatch(
        &bundle,
        &right_state,
        Some(internal(&right.emissions[0])),
    );
    assert_eq!(
        right_done
            .emissions
            .iter()
            .map(|item| item.event.as_str())
            .collect::<Vec<_>>(),
        vec!["determa.component_completed", "done"]
    );
    let completion_state = right_done.state.expect("component completion state");
    let finished = dispatch(
        &bundle,
        &completion_state,
        Some(internal(&right_done.emissions[1])),
    );
    assert_eq!(finished.status, determa_state::ResultStatus::Completed);
    assert!(
        finished
            .state
            .expect("finished state")
            .root
            .components
            .is_empty()
    );
    "components: isolated, refreshed, stale target rejected, completed".to_string()
}

fn run_owned(path: &str) -> String {
    let bundle = load_bundle(&fs::read_to_string(path).expect("owned bundle"))
        .expect("valid owned bundle");
    let created = create(
        &bundle,
        "owner",
        "owner-7",
        "owner-7:create",
        &Bindings::default(),
    );
    let mut state = created.state.expect("creation succeeds");

    let prepared = handled_input(
        &bundle,
        &state,
        "prepare",
        "owned:prepare",
        BTreeMap::new(),
    );
    state = prepared.state.expect("prepared state");
    assert_eq!(state.root.owned_instances.len(), 4);
    match state.root.visible_variables().get("root_worker") {
        Some(Value::InstanceReference(reference)) => {
            assert_eq!(reference.root_instance_id, "owner-7");
            assert_eq!(reference.machine_id, "worker");
            assert_eq!(reference.machine_version, 1);
            assert!(!reference.instance_id.is_empty());
        }
        other => panic!("root_worker is not a reference: {other:?}"),
    }

    let requested = handled_input(
        &bundle,
        &state,
        "request_bound_work",
        "owned:request",
        BTreeMap::new(),
    );
    let requested_state = requested.state.expect("request state");
    let worked = dispatch(
        &bundle,
        &requested_state,
        Some(internal(&requested.emissions[0])),
    );
    let worked_state = worked.state.expect("worked state");
    let replied = dispatch(
        &bundle,
        &worked_state,
        Some(internal(&worked.emissions[0])),
    );
    state = replied.state.expect("reply state");
    assert_eq!(int_variable(&state.root, "reply_count"), 1);

    let left = handled_input(
        &bundle,
        &state,
        "leave",
        "owned:leave",
        BTreeMap::new(),
    );
    state = left.state.expect("left holding state");
    assert_eq!(
        left.emissions
            .iter()
            .map(|item| item.payload["label"].clone())
            .collect::<Vec<_>>(),
        vec![
            Value::String("scoped-one".to_string()),
            Value::String("scoped-two".to_string()),
        ]
    );
    assert_eq!(state.root.owned_instances.len(), 2);

    let finish_request = handled_input(
        &bundle,
        &state,
        "finish_bound",
        "owned:finish-bound",
        BTreeMap::new(),
    );
    let finish_state = finish_request.state.expect("finish request state");
    let completed = dispatch(
        &bundle,
        &finish_state,
        Some(internal(&finish_request.emissions[0])),
    );
    assert_eq!(
        completed
            .emissions
            .iter()
            .map(|item| item.event.as_str())
            .collect::<Vec<_>>(),
        vec!["child_exited", "done"]
    );
    state = completed.state.expect("child completed state");
    assert_eq!(state.root.owned_instances.len(), 1);
    let completion_seen = dispatch(
        &bundle,
        &state,
        Some(internal(&completed.emissions[1])),
    );
    state = completion_seen.state.expect("completion observed state");
    assert_eq!(int_variable(&state.root, "completed_count"), 1);

    let cleaned = handled_input(
        &bundle,
        &state,
        "cleanup_references",
        "owned:cleanup",
        BTreeMap::new(),
    );
    state = cleaned.state.expect("cleanup state");
    assert_eq!(int_variable(&state.root, "cleanup_count"), 1);
    assert_eq!(state.root.owned_instances.len(), 1);

    let owner_done = handled_input(
        &bundle,
        &state,
        "finish_owner",
        "owned:finish-owner",
        BTreeMap::new(),
    );
    assert_eq!(owner_done.status, determa_state::ResultStatus::Completed);
    assert_eq!(
        owner_done.emissions[0].payload["label"],
        Value::String("unbound".to_string())
    );
    assert!(
        owner_done
            .state
            .expect("owner completed state")
            .root
            .owned_instances
            .is_empty()
    );
    "owned: 4 spawned, 2 scoped disposed, bound completed, unbound cascaded".to_string()
}

fn main() {
    let mut args = env::args().skip(1);
    let components = args.next().expect("components bundle path");
    let owned = args.next().expect("owned bundle path");
    assert!(args.next().is_none(), "expected exactly two bundle paths");
    println!("{}", run_components(&components));
    println!("{}", run_owned(&owned));
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
| Old component envelope after re-entry | Reject with `inactive_component_target`; never retarget the new activation. |
| Root executes `to: { owner: true }` | Fault the root step with `invalid_instance_target`. |

## Coverage

This chapter covers specification
[§7](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#7-components-spawning-and-lifecycle),
[§7.1](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#71-lifecycle-bound-components),
[§7.2](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#72-owned-spawned-instances),
and
[§7.3](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#73-runtime-and-aggregate-root-completion).

The matching v0.1.0 conformance cases are:

- [09 parallel components](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/09-parallel-components)
- [13 spawn completion](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/13-spawn-completion)
- [14 explicit targets](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/14-explicit-targets)
- [29 owned spawn](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/29-owned-spawn)
- [30 owned spawn cancel](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/30-owned-spawn-cancel)
- [38 destroyed reference binding](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/38-destroyed-reference-binding)
- [47 scoped owned-child lifetime](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/47-scoped-owned-child-lifetime)
- [48 null cancel](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/48-null-cancel)
- [49 exit-action cancel](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/49-exit-action-cancel)
- [51 component initialization fault](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/51-component-initialization-fault)
- [52 spawned initialization fault](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/52-spawned-initialization-fault)
- [54 stale component target](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/54-stale-component-target)
- [55 root owner target](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/55-root-owner-target)
- [73 synchronous initialization cycle](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/73-synchronous-initialization-cycle)
- [74 sibling cleanup order](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/74-sibling-cleanup-order)
- [78 component external refresh](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/78-component-external-refresh)
- [80 unbound owned child](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/80-unbound-owned-child)
- [81 holder reference reuse](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/81-holder-reference-reuse)
- [82 instance-reference target identity](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/82-instance-reference-target-identity)
- [83 contained dynamic instance send](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/83-contained-dynamic-instance-send)
- [86 initial component completion order](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/86-initial-component-completion-order)
- [87 internal env target mode](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/87-internal-env-target-mode)
- [91 component host-input rejection](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/91-component-host-input-rejection)

Portable package imports and direct host-to-component input are deliberately not
introduced here.
