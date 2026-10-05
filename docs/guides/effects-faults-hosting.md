# Effects, faults, inspection, and hosting

Determa State's portable core is a foreground transform. `create` builds the initial aggregate, `admit` accepts complete input deliveries,
and `step` processes one selected runtime's ready-mailbox head. Processing returns
the next aggregate, ordered emission evidence, a disposition, and any engine fault. It does not perform
network I/O or retain hidden work.

This chapter separates that portable result from the host that stores state, queues
accepted work, calls external services after commit, schedules time, or exposes an MCP tool.

## Model external work as a request and a later result

The example has three public workflows:

- `start_payment` emits a `payment_requested` intent. A later
  `payment_succeeded` or `payment_rejected` input carries the same correlation ID.
- `wait` emits a `schedule_requested` intent. A host-provided timer extension may
  later deliver `schedule_elapsed`.
- `force_fault` emits a tentative audit intent and then divides by zero. The complete
  RTC step rolls back, including that tentative intent.

<!-- determa-example: machines/effects-faults-hosting.yaml -->
```yaml
format: 1
namespace: tutorial.effects_faults_hosting
events:
  start_payment:
    direction: input
    payload:
      request_id: { type: string, required: true }
      amount: { type: int, required: true }
  payment_requested:
    direction: output
    payload:
      amount: { type: int, required: true }
  payment_succeeded:
    direction: input
    correlates_to: payment_requested
    payload:
      receipt: { type: string, required: true }
  payment_rejected:
    direction: input
    correlates_to: payment_requested
    payload:
      reason: { type: string, required: true }
  wait:
    direction: input
    payload:
      request_id: { type: string, required: true }
      delay_seconds: { type: int, required: true }
  schedule_requested:
    direction: output
    payload:
      delay_seconds: { type: int, required: true }
  schedule_elapsed:
    direction: input
    correlates_to: schedule_requested
  audit_requested:
    direction: output
    payload:
      label: { type: string, required: true }
  force_fault: { direction: input }
  finish: { direction: input }
machines:
  - machine_id: workflow
    version: 1
    root:
      type: composite
      variables:
        attempts: { type: int, init: 0 }
        outcome: { type: string, init: pending }
        detail: { type: string, init: "" }
      initial: { transition_to: ready }
      on_events:
        force_fault:
          action:
            - send:
                event: audit_requested
                to: { external: true }
                correlation_id: "'fault-demo'"
                payload: { label: "'must-roll-back'" }
            - assign: { attempts: "attempts / 0" }
      states:
        ready:
          on_events:
            start_payment:
              transition_to: awaiting_payment
              action:
                - assign: { attempts: "attempts + 1" }
                - send:
                    event: payment_requested
                    to: { external: true }
                    correlation_id: "event.payload.request_id"
                    payload: { amount: "event.payload.amount" }
            wait:
              transition_to: awaiting_timer
              action:
                - send:
                    event: schedule_requested
                    to: { external: true }
                    correlation_id: "event.payload.request_id"
                    payload:
                      delay_seconds: "event.payload.delay_seconds"
            finish: { transition_to: completed }
        awaiting_payment:
          on_events:
            payment_succeeded:
              transition_to: completed
              action:
                - assign: { outcome: "'succeeded'" }
                - assign: { detail: "event.payload.receipt" }
            payment_rejected:
              transition_to: declined
              action:
                - assign: { outcome: "'declined'" }
                - assign: { detail: "event.payload.reason" }
        awaiting_timer:
          on_events:
            schedule_elapsed: { transition_to: completed }
        declined: {}
        completed: { type: final }
```

An output is an **intent**, not proof that payment or scheduling succeeded. The host
may persist and deliver the intent. Only a later declared input changes the machine
based on the external outcome.

Every send to `{ external: true }` must name a public output event and provide a
non-empty correlation ID. A correlated public input must name that output through
`correlates_to` and arrive with a correlation ID. Correlation remains envelope
metadata; CEL cannot read it.

Public payload contracts use JSON-shaped values: strings are valid Unicode scalar
sequences, integers stay within signed 64-bit range, floats are finite binary64, and
lists/maps are recursively checked. The host transport must preserve those typed
values. Format 1 does not standardize one broker, HTTP, or MCP JSON envelope encoding.

## Run the complete Python trace

The trace retries the same uncommitted payment request from the same prior state. Both
attempts return the same effect identity, output sequence, state, and emission order.
It then demonstrates correlation rejection, an ordinary domain rejection, timer
adaptation, atomic engine-fault rollback, and terminal read-only inspection.

<!-- determa-example: python/effects_faults_hosting.py -->
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


def delivery(state, event, event_id, payload=None, correlation_id=None):
    return ds.portable_envelope(event, event_id, root_target(state), payload or {}, correlation_id=correlation_id)


def process(bundle, state, envelope):
    resolver = ds.MemoryArtifactResolver(definitions={bundle.fingerprint: bundle})
    admitted = ds.admit(state, [{"delivery_mode": "input", "envelope": envelope,
        "envelope_digest": ds.delivery_request_digest(state["root_instance_id"], "input", envelope)}], resolver)
    if admitted["result"] != "accepted":
        return admitted
    return ds.step(admitted["state"], state["root_runtime_id"], resolver)


def root_runtime(state):
    return next(item for item in state["runtimes"] if item["runtime_id"] == state["root_runtime_id"])


def decode(value):
    import struct

    tag = value[0]
    if tag == "integer":
        return int(value[1])
    if tag == "float":
        return struct.unpack("!d", bytes.fromhex(value[1]))[0]
    if tag == "list":
        return [decode(item) for item in value[1]]
    if tag == "map":
        return {name: decode(item) for name, item in value[1]}
    return None if tag == "null" else value[1]


def runtime_variables(runtime):
    return {item["variable_declaration_pointer"].rsplit("/", 1)[1]: decode(item["value"])
            for item in runtime["variables"]}


def create_state(bundle, machine_id, instance_id):
    result = ds.create(
        bundle,
        machine_id=machine_id,
        root_instance_id=instance_id,
        creation_id=f"{instance_id}:create",
        bindings={},
    )
    assert result["status"] == "running"
    return result["state"]

def create(bundle, suffix):
    result = ds.create(
        bundle,
        machine_id="workflow",
        root_instance_id=f"tutorial:{suffix}",
        creation_id=f"tutorial:{suffix}:create",
        bindings={},
    )
    assert result["status"] == "running"
    return result["state"]


bundle = ds.load_bundle(Path(sys.argv[1]).read_text())

payment_prior = create(bundle, "payment")
payment_input = delivery(
    payment_prior,
    "start_payment",
    "tutorial:payment:start",
    {"request_id": "payment-42", "amount": 1250},
)
payment = process(bundle, payment_prior, payment_input)
retry = process(bundle, payment_prior, payment_input)
assert payment == retry
assert payment["disposition"] == "handled"
assert payment["emissions"] == retry["emissions"]
intent = payment["emissions"][0]
assert intent["event"] == "payment_requested"
assert intent["correlation_id"] == "payment-42"
assert decode(intent["payload"]) == {"amount": 1250}
assert intent["effect_id"].startswith("sha256:")
assert intent["sequence"] == "0"
payment_state = payment["state"]

missing_correlation = process(
    bundle,
    payment_state,
    delivery(
        payment_state,
        "payment_succeeded",
        "tutorial:payment:missing-correlation",
        {"receipt": "receipt-1"},
    ),
)
assert missing_correlation["result"] == "rejected"
assert missing_correlation["rejection"] == {"code": "invalid_correlation"}
assert missing_correlation["state"] == payment_state

completed = process(
    bundle,
    payment_state,
    delivery(
        payment_state,
        "payment_succeeded",
        "tutorial:payment:succeeded",
        {"receipt": "receipt-1"},
        "payment-42",
    ),
)
assert completed["status"] == "completed"
completed_state = completed["state"]
# Reading the retained typed projection performs no engine call.
assert root_runtime(completed_state)["status"] == "completed"
assert root_runtime(completed_state)["ready_mailbox"] == []

domain_prior = create(bundle, "domain")
domain_started = process(
    bundle,
    domain_prior,
    delivery(
        domain_prior,
        "start_payment",
        "tutorial:domain:start",
        {"request_id": "payment-declined", "amount": 50},
    ),
)
domain_state = domain_started["state"]
declined = process(
    bundle,
    domain_state,
    delivery(
        domain_state,
        "payment_rejected",
        "tutorial:domain:declined",
        {"reason": "card_declined"},
        "payment-declined",
    ),
)
assert declined["status"] == "running"
assert declined["disposition"] == "handled"
assert declined["fault"] is None
declined_state = declined["state"]
declined_root = root_runtime(declined_state)
assert declined_root["active_leaf_state_definition_pointers"] == ["/machines/0/root/states/declined"]
assert runtime_variables(declined_root)["outcome"] == "declined"

timer_prior = create(bundle, "timer")
scheduled = process(
    bundle,
    timer_prior,
    delivery(
        timer_prior,
        "wait",
        "tutorial:timer:wait",
        {"request_id": "timer-7", "delay_seconds": 30},
    ),
)
schedule_intent = scheduled["emissions"][0]
assert schedule_intent["event"] == "schedule_requested"
assert schedule_intent["correlation_id"] == "timer-7"
timer_state = scheduled["state"]
elapsed = process(
    bundle,
    timer_state,
    delivery(
        timer_state,
        "schedule_elapsed",
        "tutorial:timer:elapsed",
        correlation_id="timer-7",
    ),
)
assert elapsed["status"] == "completed"

fault_prior = create(bundle, "fault")
faulted = process(
    bundle,
    fault_prior,
    delivery(fault_prior, "force_fault", "tutorial:fault:force"),
)
assert faulted["status"] == "faulted"
assert faulted["disposition"] == "faulted"
assert faulted["emissions"] == []
assert faulted["fault"]["code"] == "action_fault"
fault_state = faulted["state"]
fault_root = root_runtime(fault_state)
assert runtime_variables(fault_root)["attempts"] == 0

assert fault_root["status"] == "faulted"
assert fault_root["fault"]["code"] == faulted["fault"]["code"]
assert fault_root["ready_mailbox"] == []
blocked = process(
    bundle,
    fault_state,
    delivery(
        fault_state,
        "start_payment",
        "tutorial:fault:blocked",
        {"request_id": "never", "amount": 1},
    ),
)
assert blocked["result"] == "rejected"
assert blocked["rejection"] == {"code": "invalid_instance_target"}
assert blocked["state"] == fault_state

print(
    "effect=deterministic; correlation=enforced; domain=handled; "
    "timer=host-event; fault=rolled-back; terminal=stable"
)
```

## Run the same trace with Rust

The Rust program consumes the same bundle and asserts the same portable observations.

<!-- determa-example: rust/effects-faults-hosting/Cargo.toml -->
```toml
[package]
name = "determa-effects-faults-hosting"
version = "0.3.0"
edition = "2021"
publish = false

[dependencies]
determa-state = { git = "https://github.com/fruwehq/determa-state-rust.git", rev = "efaed0a21409f75ed55f159a6f8c833f3b62e88c" }
serde_json = "1"
serde_json_canonicalizer = "0.3"
sha2 = "0.10"
```

<!-- determa-example: rust/effects-faults-hosting/src/main.rs -->
```rust
use determa_state::{admit, create, load_bundle, restore_aggregate, step,
    AdmissionDelivery, Aggregate, Bindings, Bundle, InMemoryDefinitionResolver,
    QueueEnvelope, TypedValue};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, fs};

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

fn initial(bundle: &Bundle, suffix: &str) -> Aggregate {
    let instance = format!("tutorial:{suffix}");
    create(bundle, "workflow", &instance, &format!("{instance}:create"), &Bindings::default()).unwrap()
}

fn input(state: &Aggregate, event: &str, event_id: &str, payload: Value, correlation: Option<&str>) -> QueueEnvelope {
    QueueEnvelope { event: event.into(), event_id: event_id.into(), cause_id: event_id.into(),
        source: json!({"host": true}), target: root(state)["target_identity"].clone(), payload: typed(&payload),
        correlation_id: correlation.map(str::to_owned) }
}

fn process(bundle: &Bundle, state: &Aggregate, envelope: QueueEnvelope) -> Result<(Aggregate, Value), determa_state::ArtifactError> {
    let bytes = serde_json_canonicalizer::to_vec(&json!([
        "determa-inbox-envelope-digest-1", "1", state.value()["root_instance_id"], "input", envelope,
    ])).unwrap();
    let accepted = admit(bundle, state, &[AdmissionDelivery { delivery_mode: "input".into(), envelope,
        envelope_digest: format!("sha256:{:x}", Sha256::digest(bytes)) }])?;
    let accepted = restored(bundle, &accepted);
    let result = step(bundle, &accepted, accepted.value()["root_runtime_id"].as_str().unwrap())?;
    Ok((restored(bundle, &result), result))
}

fn main() {
    let path = env::args().nth(1).expect("machine path");
    let bundle = load(&path);
    let prior = initial(&bundle, "payment");
    let request = input(&prior, "start_payment", "tutorial:payment:start", json!({"request_id": "payment-42", "amount": 1250}), None);
    let (payment_state, payment) = process(&bundle, &prior, request.clone()).unwrap();
    let (_, retry) = process(&bundle, &prior, request).unwrap();
    assert_eq!(payment, retry);
    assert_eq!(payment["disposition"], "handled");
    let intent = &payment["emissions"][0];
    assert_eq!(intent["event"], "payment_requested");
    assert_eq!(intent["correlation_id"], "payment-42");
    assert_eq!(decode(&intent["payload"]), json!({"amount": 1250}));
    assert!(intent["effect_id"].as_str().unwrap().starts_with("sha256:"));
    assert_eq!(intent["sequence"], "0");
    let before_refusal = payment_state.value().clone();
    let missing = process(&bundle, &payment_state, input(&payment_state, "payment_succeeded",
        "tutorial:payment:missing-correlation", json!({"receipt": "receipt-1"}), None)).unwrap_err();
    assert_eq!(missing.code, "invalid_correlation");
    assert_eq!(&before_refusal, payment_state.value());
    let (completed_state, completed) = process(&bundle, &payment_state, input(&payment_state,
        "payment_succeeded", "tutorial:payment:succeeded", json!({"receipt": "receipt-1"}), Some("payment-42"))).unwrap();
    assert_eq!(completed["status"], "completed");
    assert_eq!(root(&completed_state)["status"], "completed");
    assert_eq!(root(&completed_state)["ready_mailbox"], json!([]));
    let prior = initial(&bundle, "domain");
    let (state, _) = process(&bundle, &prior, input(&prior, "start_payment", "tutorial:domain:start",
        json!({"request_id": "payment-declined", "amount": 50}), None)).unwrap();
    let (state, declined) = process(&bundle, &state, input(&state, "payment_rejected", "tutorial:domain:declined",
        json!({"reason": "card_declined"}), Some("payment-declined"))).unwrap();
    assert_eq!(declined["status"], "running");
    assert_eq!(declined["disposition"], "handled");
    assert_eq!(declined["fault"], Value::Null);
    assert_eq!(root(&state)["active_leaf_state_definition_pointers"], json!(["/machines/0/root/states/declined"]));
    assert_eq!(logical(&state, "outcome"), "declined");
    let prior = initial(&bundle, "timer");
    let (state, scheduled) = process(&bundle, &prior, input(&prior, "wait", "tutorial:timer:wait",
        json!({"request_id": "timer-7", "delay_seconds": 30}), None)).unwrap();
    assert_eq!(scheduled["emissions"][0]["event"], "schedule_requested");
    assert_eq!(scheduled["emissions"][0]["correlation_id"], "timer-7");
    let (_, elapsed) = process(&bundle, &state, input(&state, "schedule_elapsed", "tutorial:timer:elapsed",
        json!({}), Some("timer-7"))).unwrap();
    assert_eq!(elapsed["status"], "completed");
    let prior = initial(&bundle, "fault");
    let (state, faulted) = process(&bundle, &prior, input(&prior, "force_fault", "tutorial:fault:force", json!({}), None)).unwrap();
    assert_eq!(faulted["status"], "faulted");
    assert_eq!(faulted["disposition"], "faulted");
    assert_eq!(faulted["fault"]["code"], "action_fault");
    assert_eq!(faulted["emissions"], json!([]));
    assert_eq!(logical(&state, "attempts"), json!(0));
    assert_eq!(root(&state)["status"], "faulted");
    assert_eq!(root(&state)["fault"]["code"], "action_fault");
    assert_eq!(root(&state)["ready_mailbox"], json!([]));
    let before = state.value().clone();
    let blocked = process(&bundle, &state, input(&state, "start_payment", "tutorial:fault:blocked",
        json!({"request_id": "never", "amount": 1}), None)).unwrap_err();
    assert_eq!(blocked.code, "invalid_instance_target");
    assert_eq!(&before, state.value());
    println!("effect=deterministic; correlation=enforced; domain=handled; timer=host-event; fault=rolled-back; terminal=stable");
}
```

Run either extracted trace directly, or let `make check` run both:

```sh
python .cache/examples/python/effects_faults_hosting.py \
  .cache/examples/machines/effects-faults-hosting.yaml
cargo run \
  --manifest-path .cache/examples/rust/effects-faults-hosting/Cargo.toml \
  -- .cache/examples/machines/effects-faults-hosting.yaml
```

Expected output:

```text
effect=deterministic; correlation=enforced; domain=handled; timer=host-event; fault=rolled-back; terminal=stable
```

## Read the result before choosing host policy

The core result tells the host what happened:

| Field | Meaning |
|---|---|
| `status` | Existing aggregate is `running`, `completed`, or `faulted`; rejected creation has no aggregate. |
| `disposition` | A `step` was `handled`, `deferred`, `unhandled`, `not_runnable`, `rejected`, or `faulted`. Creation and admission have separate result shapes. |
| `state` | Resulting typed aggregate. Refusal preserves it; unhandled or faulted accepted processing consumes the selected mailbox entry. |
| `emissions` | Ordered internal mailbox references and external effect intents from processing. Internal envelopes are already queued in the resulting aggregate. |
| `fault` | Committed engine-fault record when this call exposes one. |
| `rejection` | Pre-step validation code; rejection is not an engine fault. |

`unhandled` is ordinary statechart behavior. A declared event such as
`payment_rejected` is an ordinary domain outcome. An engine fault means a valid,
accepted RTC step could not obey the machine contract. The engine rolls that step back,
commits one diagnostic fault record, consumes one logical step sequence, and returns no
author intent from the failed step.

After the root is `faulted`, ordinary delivery is rejected without changing the
aggregate. After it is `completed`, ordinary delivery is likewise terminal. Inspect a retained terminal aggregate directly or use the explicit inspection API.
`step` cannot process a terminal runtime; there is no null-delivery dispatch API.

The in-memory aggregate can be inspected for identities, status, active configuration,
variables, ownership, history, counters, and fault records. This is the complete version-1 typed logical-state projection, including explicit
ready and deferred mailboxes. Determa State 0.3.0 also defines portable aggregate serialization,
restoration, definition migration, and optional durable execution checkpoints. Start
with the [durable checkpoint host](execution-checkpoint-hosting.md), build the
lower-level database-backed host in the
[persistence and migration tutorial](persistence-and-migration.md), then run packages,
complete transforms, terminal maintenance, and security limits in the
[persistence reference lab](persistence-migration-reference.md).

## Keep host responsibilities outside the bundle

| Boundary | Portable core | Host or plugin |
|---|---|---|
| Queue | Owns explicit runtime mailbox placement and FIFO processing within the returned aggregate. | Owns accepted ingress, durable checkpoint commit, foreground runtime selection, external delivery, acknowledgement and dead-letter policy. |
| Timer | Emits a declared scheduling request and later accepts a declared correlated input. | Owns the clock, scheduler, durability, cancellation, lateness, and duplicate policy. |
| Database | Produces deterministic state and output intents for one foreground call. | Chooses storage representation and may transactionally combine its own inbox, aggregate storage, business data, and outbox. |
| Broker | Gives every internal envelope an event ID and every external intent an effect ID. | Owns publishing, acknowledgement, redelivery, deduplication, and broker-native dead letters. |
| MCP | Public input declarations can define adapter-visible requests. | Owns tool naming, authentication, authorization, tenancy, transport, and presentation. |

The deterministic IDs make idempotent host designs possible; they do not promise
delivery exactly once. A database transaction is local host behavior, not distributed
ACID with a broker or payment provider. A scheduling intent is not a portable timer,
and a delivered intent is not remote success.

## Know the format-1 completeness boundary

Format 1 has explicit portable mailboxes and event deferral. It deliberately has no
native clocks, timers, sleeps, external delivery/retry workers, broker acknowledgements,
or native dead-letter store, implicit parallel broadcast, shared
runtime variables, direct host-to-component delivery, cross-runtime transitions,
remote or detached spawn, package imports, implicit definition hot-swap,
an execution CLI, root re-entry, distributed exactly-once transactions, or hard real-time
guarantees. Optional version-1 registry, authority, effects, ingress, timer, archive,
recovery and public-host contracts require their separately verified host capabilities;
a contract's existence does not install a provider or run a background service.

Those names are not reserved extension fields. A host may provide applicable behavior
outside the core through declared events and plugins, but a format-1 machine cannot
inspect it or rely on an undeclared portable guarantee. Existing portable alternatives
remain explicit: isolated components instead of regions, public events instead of
shared runtime variables/state, scheduling requests instead of native timers, and read-only
aggregate inspection instead of executable observers.

## Normative coverage

The exact pinned specification sections explained here are:

- [§9 deterministic identities and emissions](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#9-deterministic-identities-and-emissions);
- [§10 faults and envelope disposition](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#10-faults-and-envelope-disposition);
- [§10.1 engine faults](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#101-engine-faults);
- [§10.2 contained runtime faults](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#102-contained-runtime-faults);
- [§10.3 domain failures](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#103-domain-failures);
- [§11 plugins and hosting](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#11-plugins-and-hosting);
- [§11.1 queue plugins](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#111-queue-plugins);
- [§11.2 timer extensions](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#112-timer-extensions);
- [§11.3 external effects](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#113-external-effects);
- [§11.4 hosting profiles](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#114-hosting-profiles);
- [§12 inspection and visualization](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#12-inspection-and-visualization);
- [§13 deliberately unsupported in format 1](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#13-deliberately-unsupported-in-format-1).

Pinned candidate conformance examples:

- [16 timer extension](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/16-timer-extension)
- [18 domain failure](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/18-domain-failure)
- [19 public event contract](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/19-public-event-contract)
- [20 invalid public correlation](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/20-invalid-public-correlation)
- [46 root boundary validation](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/46-root-boundary-validation)
- [50 root fault terminal aggregate](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/50-root-fault-terminal-aggregate)
- [67 bundle/state binding](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/67-bundle-state-binding)
- [75 root initialization fault](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/75-root-initialization-fault)
- [76 invalid creation Unicode](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/76-invalid-create-unicode)
- [77 invalid dispatch Unicode](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/77-invalid-dispatch-unicode)
- [85 initialization emission rollback](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/85-initialization-emission-rollback)
- [88 reserved payload validation](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/88-reserved-payload-validation)
- [89 non-finite creation binding](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/89-nonfinite-creation-binding)
- [90 host numeric normalization](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/90-host-numeric-normalization)
- [92 faulted-root/component precedence](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/92-faulted-root-component-precedence)
- [93 optional correlation](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/93-optional-correlation)
