# Effects, faults, inspection, and hosting

Determa State's portable core is a foreground transform. One call receives a bundle,
prior aggregate state, and at most one envelope. It returns the next state, ordered
emissions, a disposition, and any rejection or engine fault. It does not perform
network I/O or retain hidden work.

This chapter separates that portable result from the host that stores state, queues
events, calls external services, schedules time, or exposes an MCP tool.

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
    envelope = {
        "event": event,
        "event_id": event_id,
        "target": root_target(state),
        "payload": payload or {},
    }
    if correlation_id is not None:
        envelope["correlation_id"] = correlation_id
    return {"input": envelope}


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
payment = ds.dispatch(bundle, payment_prior, payment_input)
retry = ds.dispatch(bundle, payment_prior, payment_input)
assert payment == retry
assert payment["disposition"] == "handled"
assert payment["emissions"] == retry["emissions"]
intent = payment["emissions"][0]
assert intent["event"] == "payment_requested"
assert intent["target"] == "external"
assert intent["correlation_id"] == "payment-42"
assert intent["payload"] == {"amount": 1250}
assert intent["effect_id"].startswith("sha256:")
assert intent["sequence"] == 0
payment_state = payment["state"]

missing_correlation = ds.dispatch(
    bundle,
    payment_state,
    delivery(
        payment_state,
        "payment_succeeded",
        "tutorial:payment:missing-correlation",
        {"receipt": "receipt-1"},
    ),
)
assert missing_correlation["disposition"] == "rejected"
assert missing_correlation["rejection"] == {"code": "invalid_correlation"}
assert missing_correlation["state"] == payment_state

completed = ds.dispatch(
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
terminal_read = ds.dispatch(bundle, completed_state, None)
assert terminal_read["state"] == completed_state
assert terminal_read["disposition"] is None
assert terminal_read["emissions"] == []

domain_prior = create(bundle, "domain")
domain_started = ds.dispatch(
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
declined = ds.dispatch(
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
declined_root = declined_state["runtimes"][declined_state["root_runtime_id"]]
assert declined_root["active"] == ["root", "declined"]
assert declined_root["scopes"]["root"]["outcome"] == "declined"

timer_prior = create(bundle, "timer")
scheduled = ds.dispatch(
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
elapsed = ds.dispatch(
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
faulted = ds.dispatch(
    bundle,
    fault_prior,
    delivery(fault_prior, "force_fault", "tutorial:fault:force"),
)
assert faulted["status"] == "faulted"
assert faulted["disposition"] == "faulted"
assert faulted["emissions"] == []
assert faulted["fault"]["code"] == "action_fault"
fault_state = faulted["state"]
fault_root = fault_state["runtimes"][fault_state["root_runtime_id"]]
assert fault_root["scopes"]["root"]["attempts"] == 0

fault_read = ds.dispatch(bundle, fault_state, None)
assert fault_read["state"] == fault_state
assert fault_read["fault"] == faulted["fault"]
assert fault_read["emissions"] == []
blocked = ds.dispatch(
    bundle,
    fault_state,
    delivery(
        fault_state,
        "start_payment",
        "tutorial:fault:blocked",
        {"request_id": "never", "amount": 1},
    ),
)
assert blocked["disposition"] == "rejected"
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
version = "0.1.0"
edition = "2021"
publish = false

[dependencies]
determa-state = "=0.1.0"
```

<!-- determa-example: rust/effects-faults-hosting/src/main.rs -->
```rust
use determa_state::{
    create, dispatch, load_bundle, Bindings, Delivery, Disposition, Envelope,
    ResultStatus, Target, Value,
};
use std::{collections::BTreeMap, env, fs};

fn root_target(state: &determa_state::AggregateState) -> Target {
    Target::Root {
        root_instance_id: state.root_instance_id.clone(),
        root_runtime_id: state.root.runtime_id.clone(),
    }
}

fn input(
    state: &determa_state::AggregateState,
    event: &str,
    event_id: &str,
    payload: BTreeMap<String, Value>,
    correlation_id: Option<&str>,
) -> Delivery {
    Delivery::Input(Envelope {
        event: event.to_string(),
        event_id: event_id.to_string(),
        target: root_target(state),
        payload,
        correlation_id: correlation_id.map(str::to_string),
    })
}

fn create_state(bundle: &determa_state::Bundle, suffix: &str) -> determa_state::AggregateState {
    create(
        bundle,
        "workflow",
        &format!("tutorial:{suffix}"),
        &format!("tutorial:{suffix}:create"),
        &Bindings::default(),
    )
    .state
    .expect("creation succeeds")
}

fn text(value: &str) -> Value {
    Value::String(value.to_string())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let machine_path = env::args().nth(1).expect("machine path");
    let bundle = load_bundle(&fs::read_to_string(machine_path)?)?;

    let payment_prior = create_state(&bundle, "payment");
    let payment_input = input(
        &payment_prior,
        "start_payment",
        "tutorial:payment:start",
        BTreeMap::from([
            ("request_id".to_string(), text("payment-42")),
            ("amount".to_string(), Value::Int(1250)),
        ]),
        None,
    );
    let payment = dispatch(&bundle, &payment_prior, Some(payment_input.clone()));
    let retry = dispatch(&bundle, &payment_prior, Some(payment_input));
    assert_eq!(payment.disposition, Some(Disposition::Handled));
    assert_eq!(payment.emissions, retry.emissions);
    assert_eq!(payment.state, retry.state);
    let intent = &payment.emissions[0];
    assert_eq!(intent.event, "payment_requested");
    assert_eq!(intent.target, Target::External);
    assert_eq!(intent.correlation_id.as_deref(), Some("payment-42"));
    assert_eq!(intent.payload["amount"], Value::Int(1250));
    assert!(intent
        .effect_id
        .as_deref()
        .is_some_and(|value| value.starts_with("sha256:")));
    assert_eq!(intent.sequence.as_ref().map(ToString::to_string).as_deref(), Some("0"));
    let payment_state = payment.state.expect("payment state");

    let missing_correlation = dispatch(
        &bundle,
        &payment_state,
        Some(input(
            &payment_state,
            "payment_succeeded",
            "tutorial:payment:missing-correlation",
            BTreeMap::from([("receipt".to_string(), text("receipt-1"))]),
            None,
        )),
    );
    assert_eq!(missing_correlation.disposition, Some(Disposition::Rejected));
    assert_eq!(
        missing_correlation
            .rejection
            .as_ref()
            .map(|value| value.code.as_str()),
        Some("invalid_correlation")
    );
    assert_eq!(missing_correlation.state.as_ref(), Some(&payment_state));

    let completed = dispatch(
        &bundle,
        &payment_state,
        Some(input(
            &payment_state,
            "payment_succeeded",
            "tutorial:payment:succeeded",
            BTreeMap::from([("receipt".to_string(), text("receipt-1"))]),
            Some("payment-42"),
        )),
    );
    assert_eq!(completed.status, ResultStatus::Completed);
    let completed_state = completed.state.expect("completed state");
    let terminal_read = dispatch(&bundle, &completed_state, None);
    assert_eq!(terminal_read.state.as_ref(), Some(&completed_state));
    assert_eq!(terminal_read.disposition, None);
    assert!(terminal_read.emissions.is_empty());

    let domain_prior = create_state(&bundle, "domain");
    let domain_started = dispatch(
        &bundle,
        &domain_prior,
        Some(input(
            &domain_prior,
            "start_payment",
            "tutorial:domain:start",
            BTreeMap::from([
                ("request_id".to_string(), text("payment-declined")),
                ("amount".to_string(), Value::Int(50)),
            ]),
            None,
        )),
    )
    .state
    .expect("domain started");
    let declined = dispatch(
        &bundle,
        &domain_started,
        Some(input(
            &domain_started,
            "payment_rejected",
            "tutorial:domain:declined",
            BTreeMap::from([("reason".to_string(), text("card_declined"))]),
            Some("payment-declined"),
        )),
    );
    assert_eq!(declined.status, ResultStatus::Running);
    assert_eq!(declined.disposition, Some(Disposition::Handled));
    assert!(declined.fault.is_none());
    let declined_state = declined.state.expect("declined state");
    assert_eq!(declined_state.root.config(), vec!["declined"]);
    assert_eq!(
        declined_state.root.visible_variables()["outcome"],
        text("declined")
    );

    let timer_prior = create_state(&bundle, "timer");
    let scheduled = dispatch(
        &bundle,
        &timer_prior,
        Some(input(
            &timer_prior,
            "wait",
            "tutorial:timer:wait",
            BTreeMap::from([
                ("request_id".to_string(), text("timer-7")),
                ("delay_seconds".to_string(), Value::Int(30)),
            ]),
            None,
        )),
    );
    assert_eq!(scheduled.emissions[0].event, "schedule_requested");
    assert_eq!(
        scheduled.emissions[0].correlation_id.as_deref(),
        Some("timer-7")
    );
    let timer_state = scheduled.state.expect("timer state");
    let elapsed = dispatch(
        &bundle,
        &timer_state,
        Some(input(
            &timer_state,
            "schedule_elapsed",
            "tutorial:timer:elapsed",
            BTreeMap::new(),
            Some("timer-7"),
        )),
    );
    assert_eq!(elapsed.status, ResultStatus::Completed);

    let fault_prior = create_state(&bundle, "fault");
    let faulted = dispatch(
        &bundle,
        &fault_prior,
        Some(input(
            &fault_prior,
            "force_fault",
            "tutorial:fault:force",
            BTreeMap::new(),
            None,
        )),
    );
    assert_eq!(faulted.status, ResultStatus::Faulted);
    assert_eq!(faulted.disposition, Some(Disposition::Faulted));
    assert!(faulted.emissions.is_empty());
    assert_eq!(faulted.fault.as_ref().map(|fault| fault.code.as_str()), Some("action_fault"));
    let fault_state = faulted.state.expect("fault state");
    assert_eq!(fault_state.root.visible_variables()["attempts"], Value::Int(0));

    let fault_read = dispatch(&bundle, &fault_state, None);
    assert_eq!(fault_read.state.as_ref(), Some(&fault_state));
    assert_eq!(fault_read.fault, faulted.fault);
    assert!(fault_read.emissions.is_empty());
    let blocked = dispatch(
        &bundle,
        &fault_state,
        Some(input(
            &fault_state,
            "start_payment",
            "tutorial:fault:blocked",
            BTreeMap::from([
                ("request_id".to_string(), text("never")),
                ("amount".to_string(), Value::Int(1)),
            ]),
            None,
        )),
    );
    assert_eq!(blocked.disposition, Some(Disposition::Rejected));
    assert_eq!(
        blocked.rejection.as_ref().map(|value| value.code.as_str()),
        Some("invalid_instance_target")
    );
    assert_eq!(blocked.state.as_ref(), Some(&fault_state));

    println!(
        "effect=deterministic; correlation=enforced; domain=handled; \
timer=host-event; fault=rolled-back; terminal=stable"
    );
    Ok(())
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
| `disposition` | Delivery was `handled`, `unhandled`, `rejected`, or `faulted`; a read-only call uses null. |
| `state` | New aggregate state, or the exact prior state on rejection/unhandled/read-only processing. |
| `emissions` | Ordered internal envelopes and external effect intents produced by this call. |
| `fault` | Committed engine-fault record when this call exposes one. |
| `rejection` | Pre-step validation code; rejection is not an engine fault. |

`unhandled` is ordinary statechart behavior. A declared event such as
`payment_rejected` is an ordinary domain outcome. An engine fault means a valid,
accepted RTC step could not obey the machine contract. The engine rolls that step back,
commits one diagnostic fault record, consumes one logical step sequence, and returns no
author intent from the failed step.

After the root is `faulted`, ordinary delivery is rejected without changing the
aggregate. After it is `completed`, ordinary delivery is likewise terminal. A null
delivery is a read-only inspection call for either terminal state and returns unchanged
state, no disposition, and no new emissions.

The in-memory aggregate can be inspected for identities, status, active configuration,
variables, ownership, history, counters, and fault records. This is an abstract
logical-state API. Determa State 0.1.0 also defines portable aggregate serialization,
restoration, and definition migration. Build the database-backed host in the
[persistence and migration tutorial](persistence-and-migration.md), then run packages,
complete transforms, terminal maintenance, and security limits in the
[persistence reference lab](persistence-migration-reference.md).

## Keep host responsibilities outside the bundle

| Boundary | Portable core | Host or plugin |
|---|---|---|
| Queue | Returns ordered immutable emissions. | Chooses ordering across calls, delivery attempts, retry, acknowledgement, deduplication, backpressure, and dead-letter policy. |
| Timer | Emits a declared scheduling request and later accepts a declared correlated input. | Owns the clock, scheduler, durability, cancellation, lateness, and duplicate policy. |
| Database | Produces deterministic state and output intents for one foreground call. | Chooses storage representation and may transactionally combine its own inbox, aggregate storage, business data, and outbox. |
| Broker | Gives every internal envelope an event ID and every external intent an effect ID. | Owns publishing, acknowledgement, redelivery, deduplication, and broker-native dead letters. |
| MCP | Public input declarations can define adapter-visible requests. | Owns tool naming, authentication, authorization, tenancy, transport, and presentation. |

The deterministic IDs make idempotent host designs possible; they do not promise
delivery exactly once. A database transaction is local host behavior, not distributed
ACID with a broker or payment provider. A scheduling intent is not a portable timer,
and a delivered intent is not remote success.

## Know the format-1 completeness boundary

Format 1 deliberately has no native clocks, timers, sleeps, queues, retries,
acknowledgements, deferrals, dead-letter store, implicit parallel broadcast, shared
runtime variables, direct host-to-component delivery, cross-runtime transitions,
remote or detached spawn, package imports, definition hot-swap, portable snapshot
wire, standardized store/CLI protocol, root-fault recovery, root re-entry, distributed
exactly-once transaction, hard real-time guarantee, or standardized plugin
configuration.

Those names are not reserved extension fields. A host may provide applicable behavior
outside the core through declared events and plugins, but a format-1 machine cannot
inspect it or rely on an undeclared portable guarantee. Existing portable alternatives
remain explicit: isolated components instead of regions, public events instead of
shared runtime variables/state, scheduling requests instead of native timers, and read-only
aggregate inspection instead of executable observers.

## Normative coverage

The exact released specification sections explained here are:

- [§9 deterministic identities and emissions](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#9-deterministic-identities-and-emissions);
- [§10 faults and envelope disposition](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#10-faults-and-envelope-disposition);
- [§10.1 engine faults](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#101-engine-faults);
- [§10.2 contained runtime faults](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#102-contained-runtime-faults);
- [§10.3 domain failures](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#103-domain-failures);
- [§11 plugins and hosting](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#11-plugins-and-hosting);
- [§11.1 queue plugins](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#111-queue-plugins);
- [§11.2 timer extensions](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#112-timer-extensions);
- [§11.3 external effects](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#113-external-effects);
- [§11.4 hosting profiles](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#114-hosting-profiles);
- [§12 inspection and visualization](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#12-inspection-and-visualization);
- [§13 deliberately unsupported in format 1](https://github.com/fruwehq/determa-state-spec/blob/v0.1.0/SPEC.md#13-deliberately-unsupported-in-format-1).

Released conformance examples:

- [16 timer extension](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/16-timer-extension)
- [18 domain failure](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/18-domain-failure)
- [19 public event contract](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/19-public-event-contract)
- [20 invalid public correlation](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/20-invalid-public-correlation)
- [46 root boundary validation](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/46-root-boundary-validation)
- [50 root fault terminal aggregate](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/50-root-fault-terminal-aggregate)
- [67 bundle/state binding](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/67-bundle-state-binding)
- [75 root initialization fault](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/75-root-initialization-fault)
- [76 invalid creation Unicode](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/76-invalid-create-unicode)
- [77 invalid dispatch Unicode](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/77-invalid-dispatch-unicode)
- [85 initialization emission rollback](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/85-initialization-emission-rollback)
- [88 reserved payload validation](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/88-reserved-payload-validation)
- [89 non-finite creation binding](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/89-nonfinite-creation-binding)
- [90 host numeric normalization](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/90-host-numeric-normalization)
- [92 faulted-root/component precedence](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/92-faulted-root-component-precedence)
- [93 optional correlation](https://github.com/fruwehq/determa-state-conformance/tree/v0.1.0/conformance/core/93-optional-correlation)
