# Core statecharts

The first tutorial used one state and one guarded action. Real workflows need more:
nested phases, data with clear lifetimes, predictable entry and exit behavior, and a
way to resume interrupted work.

This chapter builds those ideas in layers. Every complete file is extracted from this
Markdown and run against Determa State 0.2.0 in both Python and Rust.

## 1. Read a statechart from the outside in

A machine is a tree rooted at `root`. A **composite** state owns child states and an
`initial` transition. A **simple** state is an active leaf. A **final** state completes
its containing runtime when entered.

The order-review machine below has this shape:

```text
root
|- work (composite, deep history)
|  |- review
|  |- decide (choice)
|  |- approved
|  `- rejected
|- paused
`- cancelled (final)
```

The runtime configuration contains the active path, not just the leaf. At creation it
is `root -> work -> review`.

Format 1 has four active-state types. `simple` is the default and has no children.
`composite` owns non-empty `states` plus `initial`. `parallel` owns at least two
isolated `components` instead of `states`, `initial`, or history; the components guide
develops that model. A `final` state may contain only `meta`, `variables`, and `entry`.
Choice objects are transient pseudostates, may contain only `choice` and `meta`, and
cannot be a machine or inline-component root.

State paths are relative to the machine root. `work.review` names a nested child and
the reserved literal `root` names the root itself; paths never start with `root.`.

### A complete order-review machine

<!-- determa-example: machines/core-order-review.yaml -->
```yaml
format: 1
namespace: tutorial.core_orders
events:
  add_note:
    direction: input
    payload:
      message: { type: string, default: "customer note" }
  submit:
    direction: input
    payload:
      amount: { type: int, required: true }
      priority: { type: string, default: normal }
      note: { type: string }
  local_review:
    direction: input
  reset_review:
    direction: input
  pause:
    direction: input
  resume:
    direction: input
  restart:
    direction: input
  root_restart:
    direction: input
  cancel:
    direction: input
machines:
  - machine_id: order_review
    version: 1
    root:
      type: composite
      variables:
        order_id: { type: string, input: true }
        channel: { type: string, input: true, init: web }
        region: { type: string, external: true }
        applied_region: { type: string, init: "" }
        amount: { type: int, init: 0 }
        priority: { type: string, init: "" }
        note_present: { type: bool, init: false }
        trail: { type: list, init: [] }
      entry:
        - assign: { trail: "trail + ['enter_root']" }
        - assign: { applied_region: region }
      initial:
        transition_to: work
        action:
          - assign: { trail: "trail + ['root_initial']" }
      on_events:
        env:
          guard: "event.payload.changed.region != region"
          action:
            - refresh: { only: [region] }
            - assign: { applied_region: region }
            - assign: { trail: "trail + ['refresh_region']" }
        root_restart:
          transition_to: work
      states:
        work:
          type: composite
          history: deep
          variables:
            visits: { type: int, init: 0 }
          entry:
            - assign: { visits: "visits + 1" }
            - assign: { trail: "trail + ['enter_work']" }
          exit:
            - assign: { trail: "trail + ['exit_work']" }
          initial:
            transition_to: work.review
            action:
              - assign: { trail: "trail + ['work_initial']" }
          on_events:
            local_review:
              transition_to: work.review
              local: true
            reset_review:
              transition_to: work.review
            pause:
              transition_to: paused
            cancel:
              transition_to: cancelled
          states:
            review:
              entry:
                - assign: { trail: "trail + ['enter_review']" }
              exit:
                - assign: { trail: "trail + ['exit_review']" }
              on_events:
                add_note:
                  action:
                    - assign: { visits: "visits + 1" }
                    - assign: { trail: "trail + [event.payload.message]" }
                submit:
                  transition_to: work.decide
                  action:
                    - assign: { amount: event.payload.amount }
                    - assign: { priority: event.payload.priority }
                    - assign: { note_present: "has(event.payload.note)" }
                    - assign: { trail: "trail + ['submit_action']" }
            decide:
              choice:
                - guard: "amount <= 100"
                  transition_to: work.approved
                  action:
                    - assign: { trail: "trail + ['approved_choice']" }
                - transition_to: work.rejected
                  action:
                    - assign: { trail: "trail + ['rejected_choice']" }
            approved:
              entry:
                - assign: { trail: "trail + ['enter_approved']" }
              exit:
                - assign: { trail: "trail + ['exit_approved']" }
            rejected:
              entry:
                - assign: { trail: "trail + ['enter_rejected']" }
              exit:
                - assign: { trail: "trail + ['exit_rejected']" }
        paused:
          on_events:
            resume:
              transition_to: { history: work }
            restart:
              transition_to: work
        cancelled:
          type: final
```

The root variables illustrate all three ordinary initialization sources:

- `order_id` is an input with no `init`, so creation must bind it.
- `channel` is an input with an `init`, so a binding may override its `web` default.
- `region` is external with no `init`, so creation must seed it from the host.
- the remaining ordinary variables have typed `init` values.

Creation bindings have separate `input` and `external` maps. Missing, extra, or
wrongly typed entries reject creation with `invalid_binding`; no state or emission is
created. Integer values supplied for a `float` declaration normalize to a double.
Instance references are different: they must be nullable, start at null, and can be
created only by the engine. Spawning is covered in the next guide.

## 2. Hierarchy, bubbling, and scope

An input is offered to the active leaf first. If the leaf has no enabled handler, the
engine walks outward through active ancestors.

After `submit`, `work.approved` is the active leaf. It has no `local_review` handler, so
the event bubbles to `work`. The built-in `env` event bubbles farther to `root`.
Handlers do not compete: the first enabled handler found from inner to outer wins.
If no enabled handler exists, dispatch returns `unhandled` with the exact prior state;
that is ordinary domain behavior, not an engine fault.

Variables follow the same lexical nesting:

- an action reads the nearest live declaration;
- an inner declaration shadows an outer declaration with the same name;
- entering a state initializes its variables;
- exiting destroys them after the exit action;
- re-entry creates fresh values from `init`.

The transition action runs while the source configuration is still active. It may read
or write source-scoped data that survives the transition, but the loader rejects a
write to a variable that the transition will destroy. This is
`destroyed_variable_write`, not a runtime surprise.

Entry and exit actions cannot read the current `event`. Copy event data into a
surviving variable in the transition action when later lifecycle actions need it.

## 3. Payloads are normalized before handlers run

The `submit` event requires an integer `amount`. Its optional `priority` receives the
default string `normal`; its optional `note` remains absent when omitted.

Defaults are materialized into the immutable envelope before guards and actions see
it. This makes:

```cel
event.payload.priority
```

safe for every accepted `submit`, while absence must still be tested for `note`:

```cel
has(event.payload.note)
```

Wrong types, missing required fields, extra fields, and undeclared input events are
rejected before an RTC step. The caller keeps its original input value and the machine
state remains exact.

Payload field types are `string`, `int`, `float`, `bool`, `map`, and `list`. A `float`
accepts integer or floating input and normalizes both to a portable double. An `int`
does not accept exponent or fractional source syntax, even when its mathematical value
is integral. A required field cannot also have a default, and every literal default is
type-checked when the bundle loads.

## 4. External values and `env`

An external variable is a host-sourced value copied into machine state. It is seeded at
creation and is read-only to `assign`.

The host proposes changes with the reserved `env` input:

```yaml
event: env
payload:
  changed:
    region: west
```

The handler may inspect the proposed `event.payload.changed` record. Nothing changes
unless a selected action executes `refresh`. In the example, `refresh.only: [region]`
adopts only that field, then later actions read the new `region`. A successful refresh
and the rest of its RTC commit atomically.

An `env` payload may contain only declared root external fields, with at least one
field. An unchanged proposal can be deliberately unhandled by a guard. The host does
not get an ambient mutable environment inside CEL.

## 5. Internal, local, and unmarked transitions

Transition spelling determines which lifecycle actions run.

### Internal reaction

`add_note` has no `transition_to`. Its actions run without any exit, entry, or initial
descent. Omitting `transition_to` is the only internal spelling; there is no
`internal: true` field. The same rule applies when an internal handler is selected on
an ancestor: the active descendants stay entered while the ancestor action runs.

### Local descendant transition

`local_review` is selected on composite `work` and targets its strict descendant
`work.review` with `local: true`. The current leaf exits, but `work` stays active.
Its `visits` variable and its entry/exit actions are preserved.

### Unmarked descendant transition

`reset_review` has the same source and target without `local: true`. It exits and
re-enters the non-root source `work`, so the whole subtree resets. `work.visits` is
destroyed and initialized again.

The relevant lifecycle order is:

```text
transition actions
-> capture history records for composites that exit
-> exits from inner to outer
-> entries from outer to inner
-> initial descent
```

For `work -> work.review`:

```text
local:       exit current leaf, enter review
unmarked:    exit current leaf, exit work, enter work, follow work.initial
```

`local: false`, `local` without a target, local self-transitions, and local transitions
to an ancestor or unrelated state are rejected.

### Ancestors and the root boundary

A transition from a child to a proper ancestor exits up to, but not including, that
ancestor, then follows its initial descent. The ancestor is not re-entered.

The machine root is invariant. A handler selected on `root` may target a descendant,
as `root_restart` does, but root variables and root entry/exit actions remain live.
Root self-transition, root history, and `local: true` on a root-selected transition are
rejected. Ordinary transitions cannot cross from one machine runtime into another.

## 6. Choices resolve before lifecycle changes

`work.decide` is a transient choice, not an active state. `submit` first assigns
`amount`, `priority`, and `note_present`; the choice then reads those new values.

Choice branches are ordered:

1. evaluate guards in order;
2. select the first true branch;
3. use the final unguarded branch as the required default.

An event handler may likewise be an ordered transition list. It selects the first true
guard, and an unguarded fallback must be last.

A choice may target another choice. The originating transition action and every
selected choice action run as one compound transition. Only after the complete chain
has a final active target does the engine compute one exit/entry boundary.

Choice guards and actions use the originating transition's lexical scope, including
writes made by earlier actions in the chain, but they do not receive an `event`
binding. The loader rejects a missing default, an unguarded non-final branch, an
unresolved target, or a choice that is unreachable from any valid transition.

## 7. Reachability and initialization are checked at load

Static validation proves that every declared state is reachable through one of:

- a composite's `initial` transition;
- an event transition;
- a choice branch; or
- the initial descent from a reachable transition target.

An initial transition stays inside its owning composite, has no guard, and targets a
plain state path rather than history. Every reachable composite has exactly the
initial descent required by its grammar.

Determa also rejects cycles in the synchronous initialization dependency graph. That
graph includes statically placed components and spawns reachable from entry actions,
initial-transition actions, or initialization choices. Guarded choice branches all
count because initialization must terminate for every possible value. A spawn that can
run only from an ordinary event handler does not add a creation-time initialization
dependency edge from that handler's machine. If the handler later runs, however, the
spawn synchronously creates and initializes the child inside that same atomic event
RTC; child initialization is neither deferred nor asynchronous. The target machine's
own initialization graph must still be acyclic.

The components guide exercises these cross-machine cases. The authoring rule here is
simple: creation and entry must always reach a stable configuration in finite,
statically checkable steps.

## 8. History remembers configuration, not data

The next machine puts equivalent nested configurations behind shallow and deep history.

<!-- determa-example: machines/core-history-tour.yaml -->
```yaml
format: 1
namespace: tutorial.core_history
events:
  advance:
    direction: input
  leave_shallow:
    direction: input
  resume_shallow:
    direction: input
  enter_deep:
    direction: input
  leave_deep:
    direction: input
  resume_deep:
    direction: input
machines:
  - machine_id: history_tour
    version: 1
    root:
      type: composite
      initial: { transition_to: shallow_zone }
      states:
        shallow_zone:
          type: composite
          history: shallow
          initial: { transition_to: shallow_outer }
          on_events:
            leave_shallow: { transition_to: between }
            enter_deep: { transition_to: deep_zone }
          states:
            shallow_outer:
              type: composite
              initial: { transition_to: shallow_first }
              states:
                shallow_first:
                  on_events:
                    advance: { transition_to: shallow_second }
                shallow_second: {}
        between:
          on_events:
            resume_shallow: { transition_to: { history: shallow_zone } }
            enter_deep: { transition_to: deep_zone }
        deep_zone:
          type: composite
          history: deep
          initial: { transition_to: deep_outer }
          on_events:
            leave_deep: { transition_to: after_deep }
          states:
            deep_outer:
              type: composite
              variables:
                visits: { type: int, init: 10 }
              initial: { transition_to: deep_first }
              states:
                deep_first:
                  on_events:
                    advance:
                      transition_to: deep_second
                      action:
                        - assign: { visits: "visits + 1" }
                deep_second: {}
        after_deep:
          on_events:
            resume_deep: { transition_to: { history: deep_zone } }
```

History is recorded only when its owning composite exits. Changing descendants while
the composite remains active does not update the record.

- Shallow history records the active direct child, then follows that child's normal
  initial descent. It resumes `shallow_outer.shallow_first`.
- Deep history records the complete descendant path. It resumes
  `deep_outer.deep_second`.
- With no prior record, a history target follows the composite's initial transition.
- A plain target such as `transition_to: deep_zone` ignores a record and restarts.

Restoration enters every recorded state again, outermost to innermost. Entry actions
rerun and state-scoped variables are freshly initialized. In the example,
`deep_outer.visits` becomes 11 before leaving, but is 10 after deep-history restoration.

A composite may transition to its own history. That is a real self-transition: it
captures, exits, re-enters, restores the same descendant path, reruns lifecycle
actions, and reinitializes scoped variables. A local transition may target history only
when the history-owning composite is a strict descendant of its composite source.

## 9. Parsed values are deliberately portable

Determa does not accept every value that a YAML library can produce. Machine sources
use the YAML 1.2 core model narrowed to an acyclic JSON-compatible tree.

Every current document must carry the numeric value `format: 1`. Omission, a quoted
`"1"`, or any other value is `unsupported_format`; loaders never guess the nearest
grammar. This format identifier is separate from the released package/specification
version 0.2.0 and from each author's machine `version`.

Identifiers match `^[A-Za-z_][A-Za-z0-9_]*$`; namespaces are dot-separated
identifiers. Every string in source, creation bindings, event envelopes, and logical
state must be valid Unicode scalar values. Runtime boundary validation happens before
CEL or state mutation.

The following machine relies on the important YAML 1.2 rule that `no`, `off`, `yes`,
and `on` are strings, not Booleans.

<!-- determa-example: machines/core-yaml-values.yaml -->
```yaml
format: 1
namespace: tutorial.core_yaml_values
events:
  no:
    direction: input
    payload:
      value: { type: string, default: no }
  off:
    direction: input
    payload:
      value: { type: string, default: off }
  yes:
    direction: input
    payload:
      value: { type: string, default: yes }
  on:
    direction: input
    payload:
      value: { type: string, default: on }
machines:
  - machine_id: yaml_value_cycle
    version: 1
    root:
      type: composite
      variables:
        observed_value: { type: string, init: "" }
      initial: { transition_to: no }
      states:
        no:
          on_events:
            no:
              transition_to: off
              action:
                - assign: { observed_value: event.payload.value }
        off:
          on_events:
            off:
              transition_to: yes
              action:
                - assign: { observed_value: event.payload.value }
        yes:
          on_events:
            yes:
              transition_to: on
              action:
                - assign: { observed_value: event.payload.value }
        on:
          on_events:
            on:
              transition_to: no
              action:
                - assign: { observed_value: event.payload.value }
```

The loader also rejects duplicate keys, non-string map keys, anchors, aliases, merge
keys, explicit tags, invalid Unicode, non-finite numbers, out-of-range integers, and
non-JSON numeric spellings such as hexadecimal or a leading plus sign.
These source-layer failures use the exact codes `duplicate_key`,
`non_string_map_key`, `unsupported_yaml_feature`, `non_json_value`,
`invalid_unicode`, `invalid_numeric_syntax`, `invalid_boolean_syntax`,
`invalid_null_syntax`, or `numeric_value_out_of_range` before schema and semantic
validation begin.

Plain lowercase `true` and `false` are Booleans; titlecase and uppercase forms are
invalid. Plain lowercase `null` is null; `Null`, `NULL`, `~`, and empty scalar values
are invalid. Quoted forms are always strings. Numeric tokens use the exact JSON number
grammar, so `1` is an integer while `1e0` is the double `1.0`.

Quote Boolean-like identifiers when a machine may pass through YAML 1.1 tooling. A
conforming Determa loader still resolves the original source tokens itself so a
library cannot silently collapse distinct state names.

## 10. `stop` interrupts the current runtime

`stop` commits earlier actions in the RTC but abandons the remaining transition or
initialization path. This small machine emits one trace before stopping inside a choice.

<!-- determa-example: machines/core-choice-stop.yaml -->
```yaml
format: 1
namespace: tutorial.core_stop
events:
  go:
    direction: input
  trace:
    direction: output
    payload:
      stage: { type: string, required: true }
machines:
  - machine_id: choice_stop
    version: 1
    root:
      type: composite
      initial: { transition_to: waiting }
      states:
        waiting:
          on_events:
            go: { transition_to: choose_stop }
        choose_stop:
          choice:
            - guard: "true"
              action:
                - send:
                    event: trace
                    to: { external: true }
                    payload: { stage: "'before_stop'" }
                    correlation_id: "'core-choice-stop'"
                - stop: {}
              transition_to: choose_after
            - transition_to: fallback
        choose_after:
          choice:
            - guard: "true"
              transition_to: reached_after
            - transition_to: fallback
        reached_after:
          entry:
            - send:
                event: trace
                to: { external: true }
                payload: { stage: "'after_stop'" }
                correlation_id: "'core-choice-stop'"
        fallback: {}
```

The `before_stop` emission remains. `choose_after` and `reached_after` never run, and
the root completes through its normal cleanup path.

The same interruption rule applies in an entry action and an initial-transition
action. Entry-time stop skips the rest of that runtime's descent, then exits the
partially entered configuration. Earlier writes remain visible to later exit actions
while their scopes are live. Cleanup failure rolls the whole RTC back and becomes an
engine fault.

## 11. Run the complete trace with Python

The program below creates and advances all four machines. It asserts exact active
states, normalized values, lifecycle effects, history behavior, YAML 1.2 strings, and
stop completion.

<!-- determa-example: python/core_statecharts.py -->
```python
from pathlib import Path
import sys

import determa.state as determa_state


def load(examples: Path, name: str):
    return determa_state.load_bundle((examples / "machines" / name).read_text())


def root_runtime(state):
    return state["runtimes"][state["root_runtime_id"]]


def variables(state):
    visible = {}
    for scope in root_runtime(state)["scopes"].values():
        visible.update(scope)
    return visible


def send(bundle, state, event, sequence, payload=None):
    envelope = {
        "event": event,
        "event_id": f"tutorial-core:{sequence}",
        "target": {
            "root": {
                "root_instance_id": state["root_instance_id"],
                "root_runtime_id": state["root_runtime_id"],
            }
        },
        "payload": payload or {},
    }
    result = determa_state.dispatch(bundle, state, {"input": envelope})
    assert result["disposition"] == "handled"
    return result


examples = Path(sys.argv[1])

order_bundle = load(examples, "core-order-review.yaml")
created = determa_state.create(
    order_bundle,
    machine_id="order_review",
    root_instance_id="order-1001",
    creation_id="order-1001:create",
    bindings={
        "input": {"order_id": "1001"},
        "external": {"region": "east"},
    },
)
assert created["status"] == "running"
order_state = created["state"]
assert root_runtime(order_state)["active"] == ["root", "work", "work.review"]
assert variables(order_state)["channel"] == "web"
assert variables(order_state)["region"] == "east"
assert variables(order_state)["visits"] == 1

result = send(order_bundle, order_state, "add_note", 1)
order_state = result["state"]
assert root_runtime(order_state)["active"] == ["root", "work", "work.review"]
assert variables(order_state)["visits"] == 2
assert variables(order_state)["trail"][-1] == "customer note"

result = send(
    order_bundle,
    order_state,
    "submit",
    2,
    {"amount": 80},
)
order_state = result["state"]
assert root_runtime(order_state)["active"] == ["root", "work", "work.approved"]
assert variables(order_state)["priority"] == "normal"
assert variables(order_state)["note_present"] is False
assert variables(order_state)["trail"][-3:] == [
    "approved_choice",
    "exit_review",
    "enter_approved",
]

result = send(order_bundle, order_state, "local_review", 3)
order_state = result["state"]
assert root_runtime(order_state)["active"] == ["root", "work", "work.review"]
assert variables(order_state)["visits"] == 2
assert "exit_work" not in variables(order_state)["trail"][-2:]

result = send(order_bundle, order_state, "reset_review", 4)
order_state = result["state"]
assert root_runtime(order_state)["active"] == ["root", "work", "work.review"]
assert variables(order_state)["visits"] == 1
assert variables(order_state)["trail"][-4:] == [
    "exit_review",
    "exit_work",
    "enter_work",
    "enter_review",
]

result = send(
    order_bundle,
    order_state,
    "submit",
    5,
    {"amount": 500, "note": "manual review"},
)
order_state = result["state"]
assert root_runtime(order_state)["active"] == ["root", "work", "work.rejected"]
assert variables(order_state)["note_present"] is True

result = send(order_bundle, order_state, "pause", 6)
order_state = result["state"]
assert root_runtime(order_state)["active"] == ["root", "paused"]
assert "visits" not in variables(order_state)

result = send(order_bundle, order_state, "resume", 7)
order_state = result["state"]
assert root_runtime(order_state)["active"] == ["root", "work", "work.rejected"]
assert variables(order_state)["visits"] == 1

order_state = send(order_bundle, order_state, "pause", 8)["state"]
order_state = send(order_bundle, order_state, "restart", 9)["state"]
assert root_runtime(order_state)["active"] == ["root", "work", "work.review"]
assert variables(order_state)["visits"] == 1

result = send(
    order_bundle,
    order_state,
    "env",
    10,
    {"changed": {"region": "west"}},
)
order_state = result["state"]
assert variables(order_state)["region"] == "west"
assert variables(order_state)["applied_region"] == "west"
assert root_runtime(order_state)["active"] == ["root", "work", "work.review"]

result = send(order_bundle, order_state, "root_restart", 11)
order_state = result["state"]
assert root_runtime(order_state)["active"] == ["root", "work", "work.review"]
assert variables(order_state)["region"] == "west"
assert variables(order_state)["trail"].count("enter_root") == 1

history_bundle = load(examples, "core-history-tour.yaml")
created = determa_state.create(
    history_bundle,
    machine_id="history_tour",
    root_instance_id="history-tour",
    creation_id="history-tour:create",
    bindings={},
)
history_state = created["state"]
for sequence, event in enumerate(
    ["advance", "leave_shallow", "resume_shallow"],
    start=20,
):
    history_state = send(
        history_bundle,
        history_state,
        event,
        sequence,
    )["state"]
assert root_runtime(history_state)["active"] == [
    "root",
    "shallow_zone",
    "shallow_zone.shallow_outer",
    "shallow_zone.shallow_outer.shallow_first",
]

for sequence, event in enumerate(
    ["enter_deep", "advance", "leave_deep", "resume_deep"],
    start=23,
):
    history_state = send(
        history_bundle,
        history_state,
        event,
        sequence,
    )["state"]
active = root_runtime(history_state)["active"]
assert active == ["root", "deep_zone", "deep_zone.deep_outer", "deep_zone.deep_outer.deep_second"]
assert variables(history_state)["visits"] == 10

yaml_bundle = load(examples, "core-yaml-values.yaml")
created = determa_state.create(
    yaml_bundle,
    machine_id="yaml_value_cycle",
    root_instance_id="yaml-cycle",
    creation_id="yaml-cycle:create",
    bindings={},
)
yaml_state = created["state"]
for sequence, event in enumerate(["no", "off", "yes", "on"], start=40):
    yaml_state = send(yaml_bundle, yaml_state, event, sequence)["state"]
assert root_runtime(yaml_state)["active"] == ["root", "no"]
assert variables(yaml_state)["observed_value"] == "on"

stop_bundle = load(examples, "core-choice-stop.yaml")
created = determa_state.create(
    stop_bundle,
    machine_id="choice_stop",
    root_instance_id="choice-stop",
    creation_id="choice-stop:create",
    bindings={},
)
stop_result = send(stop_bundle, created["state"], "go", 50)
assert stop_result["status"] == "completed"
assert [emission["payload"]["stage"] for emission in stop_result["emissions"]] == [
    "before_stop"
]

print(
    "order=work.review; history=deep_second; "
    "yaml=no; stop=completed"
)
```

## 12. Run the same trace with Rust

The Rust program uses the same four extracted YAML files and checks the same outcomes.

<!-- determa-example: rust/core-statecharts/Cargo.toml -->
```toml
[package]
name = "determa-core-statecharts"
version = "0.2.0"
edition = "2021"
publish = false

[dependencies]
determa-state = "=0.2.0"
```

<!-- determa-example: rust/core-statecharts/src/main.rs -->
```rust
use determa_state::{
    create, dispatch, load_bundle, AggregateState, Bindings, Bundle, Delivery,
    Disposition, Envelope, ResultStatus, Target, Value,
};
use std::{collections::BTreeMap, env, fs, path::Path};

fn load(examples: &Path, name: &str) -> Result<Bundle, Box<dyn std::error::Error>> {
    Ok(load_bundle(&fs::read_to_string(
        examples.join("machines").join(name),
    )?)?)
}

fn input(
    state: &AggregateState,
    event: &str,
    sequence: u8,
    payload: BTreeMap<String, Value>,
) -> Delivery {
    Delivery::Input(Envelope {
        event: event.to_string(),
        event_id: format!("tutorial-core:{sequence}"),
        target: Target::Root {
            root_instance_id: state.root_instance_id.clone(),
            root_runtime_id: state.root.runtime_id.clone(),
        },
        payload,
        correlation_id: None,
    })
}

fn send(
    bundle: &Bundle,
    state: &AggregateState,
    event: &str,
    sequence: u8,
    payload: BTreeMap<String, Value>,
) -> determa_state::CoreResult {
    let result = dispatch(
        bundle,
        state,
        Some(input(state, event, sequence, payload)),
    );
    assert_eq!(result.disposition, Some(Disposition::Handled));
    result
}

fn no_payload() -> BTreeMap<String, Value> {
    BTreeMap::new()
}

fn active(state: &AggregateState, path: &str) -> bool {
    state.root.active.contains(path)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let examples_argument = env::args().nth(1).expect("examples directory");
    let examples = Path::new(&examples_argument);

    let order_bundle = load(examples, "core-order-review.yaml")?;
    let order_bindings = Bindings {
        input: BTreeMap::from([(
            "order_id".to_string(),
            Value::String("1001".to_string()),
        )]),
        external: BTreeMap::from([(
            "region".to_string(),
            Value::String("east".to_string()),
        )]),
    };
    let created = create(
        &order_bundle,
        "order_review",
        "order-1001",
        "order-1001:create",
        &order_bindings,
    );
    assert_eq!(created.status, ResultStatus::Running);
    let mut order_state = created.state.expect("order creation succeeds");
    assert!(active(&order_state, "work.review"));
    assert_eq!(
        order_state.root.visible_variables()["channel"],
        Value::String("web".to_string())
    );
    assert_eq!(
        order_state.root.visible_variables()["visits"],
        Value::Int(1)
    );

    order_state = send(
        &order_bundle,
        &order_state,
        "add_note",
        1,
        no_payload(),
    )
    .state
    .expect("note succeeds");
    assert_eq!(
        order_state.root.visible_variables()["visits"],
        Value::Int(2)
    );

    order_state = send(
        &order_bundle,
        &order_state,
        "submit",
        2,
        BTreeMap::from([("amount".to_string(), Value::Int(80))]),
    )
    .state
    .expect("submit succeeds");
    assert!(active(&order_state, "work.approved"));
    assert_eq!(
        order_state.root.visible_variables()["priority"],
        Value::String("normal".to_string())
    );
    assert_eq!(
        order_state.root.visible_variables()["note_present"],
        Value::Bool(false)
    );

    order_state = send(
        &order_bundle,
        &order_state,
        "local_review",
        3,
        no_payload(),
    )
    .state
    .expect("local transition succeeds");
    assert!(active(&order_state, "work.review"));
    assert_eq!(
        order_state.root.visible_variables()["visits"],
        Value::Int(2)
    );

    order_state = send(
        &order_bundle,
        &order_state,
        "reset_review",
        4,
        no_payload(),
    )
    .state
    .expect("unmarked transition succeeds");
    assert_eq!(
        order_state.root.visible_variables()["visits"],
        Value::Int(1)
    );

    order_state = send(
        &order_bundle,
        &order_state,
        "submit",
        5,
        BTreeMap::from([
            ("amount".to_string(), Value::Int(500)),
            (
                "note".to_string(),
                Value::String("manual review".to_string()),
            ),
        ]),
    )
    .state
    .expect("second submit succeeds");
    assert!(active(&order_state, "work.rejected"));

    order_state = send(
        &order_bundle,
        &order_state,
        "pause",
        6,
        no_payload(),
    )
    .state
    .expect("pause succeeds");
    assert!(active(&order_state, "paused"));
    assert!(!order_state.root.visible_variables().contains_key("visits"));

    order_state = send(
        &order_bundle,
        &order_state,
        "resume",
        7,
        no_payload(),
    )
    .state
    .expect("history resume succeeds");
    assert!(active(&order_state, "work.rejected"));
    assert_eq!(
        order_state.root.visible_variables()["visits"],
        Value::Int(1)
    );

    order_state = send(
        &order_bundle,
        &order_state,
        "pause",
        8,
        no_payload(),
    )
    .state
    .expect("second pause succeeds");
    order_state = send(
        &order_bundle,
        &order_state,
        "restart",
        9,
        no_payload(),
    )
    .state
    .expect("plain restart succeeds");
    assert!(active(&order_state, "work.review"));

    let changed = Value::Map(BTreeMap::from([(
        "region".to_string(),
        Value::String("west".to_string()),
    )]));
    order_state = send(
        &order_bundle,
        &order_state,
        "env",
        10,
        BTreeMap::from([("changed".to_string(), changed)]),
    )
    .state
    .expect("external refresh succeeds");
    assert_eq!(
        order_state.root.visible_variables()["region"],
        Value::String("west".to_string())
    );

    order_state = send(
        &order_bundle,
        &order_state,
        "root_restart",
        11,
        no_payload(),
    )
    .state
    .expect("root-selected transition succeeds");
    assert!(active(&order_state, "work.review"));

    let history_bundle = load(examples, "core-history-tour.yaml")?;
    let created = create(
        &history_bundle,
        "history_tour",
        "history-tour",
        "history-tour:create",
        &Bindings::default(),
    );
    let mut history_state = created.state.expect("history creation succeeds");
    for (sequence, event) in ["advance", "leave_shallow", "resume_shallow"]
    .into_iter()
    .enumerate()
    {
        history_state = send(
            &history_bundle,
            &history_state,
            event,
            20 + sequence as u8,
            no_payload(),
        )
        .state
        .expect("history step succeeds");
    }
    assert!(active(
        &history_state,
        "shallow_zone.shallow_outer.shallow_first"
    ));
    for (sequence, event) in [
        "enter_deep",
        "advance",
        "leave_deep",
        "resume_deep",
    ]
    .into_iter()
    .enumerate()
    {
        history_state = send(
            &history_bundle,
            &history_state,
            event,
            23 + sequence as u8,
            no_payload(),
        )
        .state
        .expect("deep history step succeeds");
    }
    assert!(active(
        &history_state,
        "deep_zone.deep_outer.deep_second"
    ));
    assert_eq!(
        history_state.root.visible_variables()["visits"],
        Value::Int(10)
    );

    let yaml_bundle = load(examples, "core-yaml-values.yaml")?;
    let created = create(
        &yaml_bundle,
        "yaml_value_cycle",
        "yaml-cycle",
        "yaml-cycle:create",
        &Bindings::default(),
    );
    let mut yaml_state = created.state.expect("YAML cycle creation succeeds");
    for (sequence, event) in ["no", "off", "yes", "on"].into_iter().enumerate() {
        yaml_state = send(
            &yaml_bundle,
            &yaml_state,
            event,
            40 + sequence as u8,
            no_payload(),
        )
        .state
        .expect("YAML cycle step succeeds");
    }
    assert!(active(&yaml_state, "no"));
    assert_eq!(
        yaml_state.root.visible_variables()["observed_value"],
        Value::String("on".to_string())
    );

    let stop_bundle = load(examples, "core-choice-stop.yaml")?;
    let created = create(
        &stop_bundle,
        "choice_stop",
        "choice-stop",
        "choice-stop:create",
        &Bindings::default(),
    );
    let stop_state = created.state.expect("stop creation succeeds");
    let stopped = send(
        &stop_bundle,
        &stop_state,
        "go",
        50,
        no_payload(),
    );
    assert_eq!(stopped.status, ResultStatus::Completed);
    assert_eq!(stopped.emissions.len(), 1);
    assert_eq!(
        stopped.emissions[0].payload["stage"],
        Value::String("before_stop".to_string())
    );

    println!(
        "order=work.review; history=deep_second; \
         yaml=no; stop=completed"
    );
    Ok(())
}
```

Run the extracted programs:

```sh
make extract
python .cache/examples/python/core_statecharts.py .cache/examples
cargo run --manifest-path \
  .cache/examples/rust/core-statecharts/Cargo.toml -- \
  .cache/examples
```

Both print:

```text
order=work.review; history=deep_second; yaml=no; stop=completed
```

## 13. Authoring checklist

Before relying on a machine:

1. Give every ordinary variable a typed `init`; bind required root inputs and external
   values at creation.
2. Declare every host event and payload field. Use defaults only on optional fields.
3. Expect events to bubble from the active leaf to ancestors.
4. Omit `transition_to` for an internal reaction. Use `local: true` only for a
   composite-to-strict-descendant transition.
5. Put one unguarded default last in every transition list and choice.
6. Use `{ history: composite_path }` only when that composite declares shallow or deep
   history. Use a plain path to restart.
7. Remember that history restores state configuration but reinitializes variables and
   reruns lifecycle actions.
8. Keep initialization acyclic and every state reachable.
9. Parse source with Determa's YAML 1.2-compatible loader rather than a generic YAML
   1.1 conversion step.
10. Treat `stop` as committed interruption of the current runtime, followed by normal
    cleanup.

## 14. Conformance coverage

The executable arbiter for these explanations is the pinned Determa State conformance
suite. This chapter covers these exact v0.2.0 cases:

- Hierarchy, initialization, scope, payloads, transitions, and external values:
  [02-hierarchy-bubbling](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/02-hierarchy-bubbling),
  [03-initial-action](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/03-initial-action),
  [05-variable-scope](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/05-variable-scope),
  [06-payload-typing](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/06-payload-typing),
  [07-internal-external](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/07-internal-external),
  [08-local-vs-external](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/08-local-vs-external), and
  [15-external-env-refresh](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/15-external-env-refresh).
- Choices and reachability:
  [23-choice](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/23-choice),
  [24-choice-chain](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/24-choice-chain),
  [25-choice-invalid](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/25-choice-invalid),
  [26-unreachable](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/26-unreachable),
  [27-dead-branch](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/27-dead-branch),
  [28-reachable-ok](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/28-reachable-ok), and
  [53-compound-choice-lifecycle](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/53-compound-choice-lifecycle).
- History, lifecycle, and transition boundaries:
  [10-history-deep](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/10-history-deep),
  [11-history-shallow](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/11-history-shallow),
  [32-history-resume-restart](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/32-history-resume-restart),
  [33-history-capture-timing](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/33-history-capture-timing),
  [34-history-first-entry](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/34-history-first-entry),
  [35-shallow-deep-history](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/35-shallow-deep-history),
  [36-history-variable-reinitialization](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/36-history-variable-reinitialization),
  [37-destroyed-variable-write](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/37-destroyed-variable-write),
  [39-ancestor-internal-transition](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/39-ancestor-internal-transition),
  [40-noncanonical-transitions](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/40-noncanonical-transitions),
  [42-initial-history-rejection](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/42-initial-history-rejection),
  [43-self-history-lifecycle](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/43-self-history-lifecycle),
  [44-local-history](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/44-local-history), and
  [45-proper-ancestor-target](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/45-proper-ancestor-target).
- Variable creation, defaults, parsing, and stop interruption:
  [56-variable-initialization](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/56-variable-initialization),
  [57-creation-binding-defaults](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/57-creation-binding-defaults),
  [58-missing-creation-binding](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/58-missing-creation-binding),
  [59-payload-default-materialization](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/59-payload-default-materialization),
  [60-payload-default-validation](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/60-payload-default-validation),
  [62-parsed-value-model](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/62-parsed-value-model),
  [63-entry-stop-interruption](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/63-entry-stop-interruption),
  [84-choice-stop-chain](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/84-choice-stop-chain), and
  [116-legacy-format-policy](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/116-legacy-format-policy).

Normative references:
[parsing and format identity §2](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#2-conformance-parsing-and-format-identity),
[states §4.6](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#46-state-nodes),
[transitions §4.7](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#47-transitions),
[hierarchical dispatch §6.3](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#63-hierarchical-dispatch),
[execution order §6.4](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#64-transition-execution-order),
[choice and history §6.5](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#65-choice-and-history),
and
[stop interruption §6.6](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#66-stop-interruption).
