# Mailboxes, deferral and inspection

Admission and processing are separate foreground operations. `admit` validates a
complete normalized envelope and stores it in a runtime's ready mailbox. `step`
processes at most one ready head for the named runtime. The aggregate contains both
ready and deferred mailboxes, so an application can persist them with the rest of its
state and resume without a hidden worker.

Deferral is resolved from the active leaf toward its ancestors. At each state, an
enabled handler wins; otherwise a matching `deferred_events` declaration stops the
search. Thus child deferral can prevent an ancestor handler, while an enabled child
handler can override ancestor deferral. A guard fault becomes an engine fault rather
than a deferral. An unhandled event is consumed normally.

After a successful state change, eligible deferred events return to the ready tail.
Their acceptance identity stays fixed, while queue sequence records the new placement.
The runtime root's `deferred_event_capacity` bounds retained deferred work; overflow
fails deterministically. Deferral is durable core state, not a broker redelivery trick.

## Run a deferred input

<!-- determa-example: machines/mailbox-counter.yaml -->
```yaml
format: 1
namespace: tutorial.mailbox
events:
  add:
    direction: input
    payload:
      amount: { type: int, required: true }
  open:
    direction: input
machines:
  - machine_id: counter
    version: 1
    root:
      type: composite
      deferred_event_capacity: 2
      variables:
        count: { type: int, init: 0 }
      initial: { transition_to: closed }
      states:
        closed:
          deferred_events: [add]
          on_events:
            open: { transition_to: accepting }
        accepting:
          on_events:
            add:
              action:
                - assign: { count: "count + event.payload.amount" }
```

<!-- determa-example: python/mailbox_counter.py -->
```python
from pathlib import Path
import sys
import determa.state as ds

bundle = ds.load_bundle(Path(sys.argv[1]).read_text())
resolver = ds.MemoryArtifactResolver(definitions={bundle.fingerprint: bundle})
state = ds.create(bundle, "counter", "mailbox-1", "mailbox-1:create", {})["state"]


def root():
    return next(runtime for runtime in state["runtimes"]
                if runtime["runtime_id"] == state["root_runtime_id"])


def admit(event, event_id, payload):
    global state
    envelope = ds.portable_envelope(event, event_id, root()["target_identity"], payload)
    delivery = {"delivery_mode": "input", "envelope": envelope,
                "envelope_digest": ds.delivery_request_digest("mailbox-1", "input", envelope)}
    result = ds.admit(state, [delivery], resolver)
    assert result["result"] == "accepted"
    state = result["state"]


def step():
    global state
    result = ds.step(state, state["root_runtime_id"], resolver)
    state = result["state"]
    return result


admit("add", "add-1", {"amount": 4})
assert step()["disposition"] == "deferred"
retained = root()["deferred_mailbox"][0]
assert not root()["ready_mailbox"]
admit("open", "open-1", {})
assert step()["disposition"] == "handled"
released = root()["ready_mailbox"][0]
assert released["envelope"] == retained["envelope"]
assert released["acceptance_sequence"] == retained["acceptance_sequence"]
assert released["queue_sequence"] != retained["queue_sequence"]
assert not root()["deferred_mailbox"]
assert step()["disposition"] == "handled"
count = next(item["value"] for item in root()["variables"]
             if item["variable_declaration_pointer"].endswith("/count"))
assert count == ["integer", "4"]
assert not root()["ready_mailbox"]
print("deferred=retained; release=tail; acceptance=preserved; count=4")
```

Run the same assertions with Rust. Both programs use public v1 APIs.

<!-- determa-example: rust/mailbox-counter/Cargo.toml -->
```toml
[package]
name = "determa-mailbox-counter"
version = "0.3.0"
edition = "2021"
publish = false

[dependencies]
determa-state = { git = "https://github.com/fruwehq/determa-state-rust", rev = "efaed0a21409f75ed55f159a6f8c833f3b62e88c" }
serde_json = "1"
serde_json_canonicalizer = "0.3"
sha2 = "0.10"
```

<!-- determa-example: rust/mailbox-counter/src/main.rs -->
```rust
use determa_state::{admit, create, load_bundle, restore_aggregate, step,
    AdmissionDelivery, Aggregate, Bindings, Bundle, InMemoryDefinitionResolver,
    QueueEnvelope, TypedValue};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, fs};

fn root(state: &Aggregate) -> &Value {
    state.value()["runtimes"].as_array().unwrap().iter()
        .find(|runtime| runtime["runtime_id"] == state.value()["root_runtime_id"]).unwrap()
}

fn restored(bundle: &Bundle, result: &Value) -> Aggregate {
    let mut resolver = InMemoryDefinitionResolver::default();
    resolver.insert(bundle.clone(), true);
    restore_aggregate(&serde_json_canonicalizer::to_vec(&result["state"]).unwrap(), &resolver).unwrap()
}


fn accept(bundle: &Bundle, state: &Aggregate, event: &str, id: &str, payload: TypedValue) -> Aggregate {
    let envelope = QueueEnvelope { event: event.into(), event_id: id.into(), cause_id: id.into(),
        source: json!({"host":true}), target: root(state)["target_identity"].clone(), payload, correlation_id: None };
    let bytes = serde_json_canonicalizer::to_vec(&json!([
        "determa-inbox-envelope-digest-1", "1", "mailbox-1", "input", envelope,
    ])).unwrap();
    let accepted = admit(bundle, state, &[AdmissionDelivery { delivery_mode: "input".into(), envelope,
        envelope_digest: format!("sha256:{:x}", Sha256::digest(bytes)) }]).unwrap();
    restored(bundle, &accepted)
}

fn advance(bundle: &Bundle, state: &Aggregate, disposition: &str) -> Aggregate {
    let result = step(bundle, state, state.value()["root_runtime_id"].as_str().unwrap()).unwrap();
    assert_eq!(result["disposition"], disposition);
    restored(bundle, &result)
}

fn main() {
    let bundle = load_bundle(&fs::read_to_string(env::args().nth(1).unwrap()).unwrap()).unwrap();
    let state = create(&bundle, "counter", "mailbox-1", "mailbox-1:create", &Bindings::default()).unwrap();
    let state = accept(&bundle, &state, "add", "add-1", TypedValue::Map(
        [("amount".into(), TypedValue::Integer(4))].into()));
    let state = advance(&bundle, &state, "deferred");
    let retained = root(&state)["deferred_mailbox"][0].clone();
    assert_eq!(root(&state)["ready_mailbox"], json!([]));
    let state = accept(&bundle, &state, "open", "open-1", TypedValue::Map(Default::default()));
    let state = advance(&bundle, &state, "handled");
    let released = &root(&state)["ready_mailbox"][0];
    assert_eq!(released["envelope"], retained["envelope"]);
    assert_eq!(released["acceptance_sequence"], retained["acceptance_sequence"]);
    assert_ne!(released["queue_sequence"], retained["queue_sequence"]);
    assert_eq!(root(&state)["deferred_mailbox"], json!([]));
    let state = advance(&bundle, &state, "handled");
    let count = root(&state)["variables"].as_array().unwrap().iter()
        .find(|item| item["variable_declaration_pointer"].as_str().unwrap().ends_with("/count")).unwrap();
    assert_eq!(count["value"], json!(["integer", "4"]));
    assert_eq!(root(&state)["ready_mailbox"], json!([]));
    println!("deferred=retained; release=tail; acceptance=preserved; count=4");
}
```

## Inspect without executing

Exact candidate inspection accepts a portable aggregate and an exact candidate input.
It validates target identity, event shape and correlation and reports structural
routing evidence without committing an admission or running actions. Optional safe
semantic inspection additionally evaluates supported guards against an isolated view.
Unknown or unavailable evidence remains unknown: an inspection result is never a
reservation or proof that a later CAS commit will succeed.

Candidate inspection leaves ready and deferred mailboxes unchanged. A UI can use it
to explain a disabled command, but the real admission and processing path must still
validate the command at its current revision. Introspection returns portable values;
it cannot expose SDK objects, transactions, callbacks or live adapter handles.

The complete core vectors exercise parallel-state selection, false guards, capacity,
release ordering, source identity and lifecycle disposal. The separate introspection
profile tests exact inspection and optional semantic capability negotiation.

## Normative coverage

[§6.7 automatic deferral](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#67-automatic-deferral)
and [§12 inspection and visualization](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#12-inspection-and-visualization)
are authoritative. See the pinned [117 mailbox case](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core/117-version1-mailboxes)
and [introspection profile](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/profiles/introspection).
