# CEL and structured actions

Determa State uses [CEL](https://cel.dev/) for guards and computed action values.
The machine file remains data: the engine parses and type-checks every expression when
the bundle loads, then evaluates only the expressions selected by an event.

This chapter uses the closed portable CEL profile from Determa State 0.0.7. It does not
use host functions or implementation-specific CEL extensions.

## Start with ordered guards

A handler may be one transition or an ordered list. The engine tests list entries from
top to bottom and selects the first guard that is `true`. An unguarded fallback, when
present, must be last.

<!-- determa-example: machines/guard-order.yaml -->
```yaml
format: 1
namespace: tutorial.guard_order
events:
  check:
    direction: input
    payload:
      quantity: { type: int, required: true }
  reset: { direction: input }
machines:
  - machine_id: guard_order
    version: 1
    root:
      type: composite
      initial: { transition_to: waiting }
      states:
        waiting:
          on_events:
            check:
              - guard: event.payload.quantity > 10
                transition_to: bulk
              - guard: event.payload.quantity > 0
                transition_to: standard
              - transition_to: empty
        bulk:
          on_events:
            reset: { transition_to: waiting }
        standard:
          on_events:
            reset: { transition_to: waiting }
        empty:
          on_events:
            reset: { transition_to: waiting }
```

For `quantity: 20`, both guarded conditions are true, but the first branch wins. For
`quantity: 3`, only the second guard is true. For zero, neither guard is true, so the
unguarded fallback wins. If no branch is enabled and there is no fallback, the event is
`unhandled`; that is not an engine fault.

A guard must produce `bool`. A value-dependent evaluation error, such as division by
zero, is a `guard_fault`; the engine does not continue to a later branch.

## Know what portable CEL contains

The portable profile is an allowlist. An engine may use a larger CEL library
internally, but a format-1 bundle cannot use anything outside this list.

### Types

| Determa type | Portable CEL value |
|---|---|
| `bool` | `true` or `false` |
| `int` | signed 64-bit integer |
| `float` | finite IEEE 754 binary64 `double` |
| `string` | Unicode scalar-value string |
| `list` | `list(dyn)` |
| `map` | `map(string, dyn)` |
| nullable `instance_reference` | engine-created nominal reference or `null` |
| event and owner records | closed, location-specific typed records |

`instance_reference` values are deliberately opaque. CEL may compare compatible
references for equality or compare one with `null`, but cannot construct, inspect,
order, or convert them to strings.

### Expressions and functions

The complete portable expression surface is:

- literals, `event.payload.field`, `owner.variables.field`, map field selection, and
  list/map indexing;
- the conditional operator `condition ? selected : unselected`;
- `!`, `&&`, `||`, and `in`;
- same-type equality and comparison;
- checked numeric `+`, `-`, `*`, `/`, and `%`;
- string and list `+`;
- `size(value)`;
- `has(map.field)` and `has(event.payload.declared_field)`;
- `double(int)`, `int(double)`, and
  `string(bool|int|double|string)`.

There are no other portable functions, macros, or receiver methods. In particular,
portable CEL has no comprehensions, iteration, regular expressions, `uint`, bytes,
timestamps, durations, optional types, protobuf construction, random values, clocks,
I/O, host callbacks, or ambient engine state.

The activation is closed too. `event` contains only `payload`; it does not expose an
event ID, event name, target, correlation ID, or transport metadata. `owner` contains
only `variables` and is available only in component placement bindings.

### Numbers are exact at their boundaries

An `int` remains an integer from
`-9223372036854775808` through `9223372036854775807`. Overflow is an evaluation error.
Integer division truncates toward zero and remainder keeps the dividend's sign, so
`-7 / 3` is `-2` and `-7 % 3` is `-1`.

A `float` is finite binary64. Negative zero is normalized to positive zero, and a
non-finite result is an error. The only implicit widening is from `int` to a declared
`float` destination. Mixed numeric operators are rejected at load, so write
`double(count) * rate`, not `count * rate`.

Conversions are explicit inside an expression:

```text
double(9007199254740993) == 9007199254740992.0
int(-2.9) == -2
string(1.5) == "1.5"
```

The first result reflects binary64 round-to-nearest, ties-to-even. String conversion
uses canonical finite-number spelling.

Inside a list or map, integer-form literals remain `int` and fractional or
exponent-form literals remain `double`. Container members do not receive automatic
numeric widening merely because the container is dynamic.

### Lists, maps, and strings

Lists compare in order. Maps compare the exact key/value set without considering
member order, while dynamic numeric members remain type-sensitive. These are portable:

```text
["vip"] + ["calculated"]
tags[0]
"vip" in tags
{"a": 1, "b": [2]} == {"b": [2], "a": 1}
has(labels.priority)
labels["priority"]
```

Missing map keys and negative or out-of-range list indexes are evaluation errors.
`has(map.field)` checks presence without reading a missing value.

Strings are not Unicode-normalized. `"é"` and `"é"` are different strings.
`size("é")` is `1`, while the decomposed spelling has size `2`. Relational operators
compare Unicode scalar values.

For an optional payload field, use `has` before selecting it:

```text
has(event.payload.note)
  ? event.payload.note
  : "no note"
```

A required field, or an optional field whose default was materialized, is present.
Reading an absent optional field is an evaluation error.

## Boolean errors are absorbed only by a decisive value

Portable CEL's `&&` and `||` are commutative and error-absorbing. The result does not
depend on which pure operand an implementation evaluates first.

For `&&`:

| left | right | result |
|---|---|---|
| `false` | error | `false` |
| error | `false` | `false` |
| `true` | error | error |
| error | `true` | error |

For `||`:

| left | right | result |
|---|---|---|
| `true` | error | `true` |
| error | `true` | `true` |
| `false` | error | error |
| error | `false` | error |

`false` decides an AND, and `true` decides an OR. The other two Boolean values cannot
hide an error. A conditional expression is different: it evaluates the condition and
exactly one selected branch, never the unselected branch.

## Build a workflow from structured actions

Structured actions are data with fixed shapes:

| Action | Shape | Purpose |
|---|---|---|
| assign | `{ assign: { variable: CEL } }` | write one typed variable |
| send | `{ send: { event, to? \| targets?, payload?, correlation_id? } }` | create ordered immutable emissions |
| refresh | `{ refresh: { only?: [name, ...] } }` | adopt selected values from `env.changed` |
| spawn | `{ spawn: { machine_id, bindings?, bind_to? } }` | create an owned same-bundle runtime |
| cancel | `{ cancel: { instance: CEL } }` | cancel an owned runtime addressed by a reference |
| stop | `{ stop: {} }` | complete the executing runtime |

The next bundle uses every action. It creates an audit worker during root entry,
refreshes a host-provided rate, computes a quote, sends one internal audit event and
one external intent, then cancels the worker and stops.

<!-- determa-example: machines/cel-actions.yaml -->
```yaml
format: 1
namespace: tutorial.cel_actions
events:
  evaluate:
    direction: input
    payload:
      quantity: { type: int, required: true }
      request_id: { type: string, required: true }
      note: { type: string }
  release_worker: { direction: input }
  shutdown: { direction: input }
  audit:
    direction: internal
    payload:
      summary: { type: string, required: true }
  quote_ready:
    direction: output
    payload:
      total: { type: float, required: true }
      summary: { type: string, required: true }
      tags: { type: list, required: true }
      priority: { type: bool, required: true }
      rounded: { type: float, required: true }
machines:
  - machine_id: checkout
    version: 1
    root:
      type: composite
      variables:
        rate: { type: float, external: true, init: 1.0 }
        worker:
          type: instance_reference
          machine_id: audit_worker
          nullable: true
          init: null
        quantity: { type: int, init: 0 }
        subtotal: { type: float, init: 0.0 }
        total: { type: float, init: 0.0 }
        labels:
          type: map
          init: { vip: priority, standard: standard }
        tags: { type: list, init: [vip, new] }
        summary: { type: string, init: "" }
        has_note: { type: bool, init: false }
        priority: { type: bool, init: false }
        maps_equal: { type: bool, init: false }
        unicode_rules_hold: { type: bool, init: false }
        rounded: { type: float, init: 0.0 }
        truncated: { type: int, init: 0 }
        false_and_error: { type: bool, init: true }
        error_and_false: { type: bool, init: true }
        true_or_error: { type: bool, init: false }
        error_or_true: { type: bool, init: false }
      entry:
        - spawn:
            machine_id: audit_worker
            bindings:
              input:
                prefix: '"audit"'
            bind_to: worker
      initial: { transition_to: ready }
      states:
        ready:
          on_events:
            env:
              action:
                - refresh: { only: [rate] }
            evaluate:
              - guard: event.payload.quantity > 0 && size(tags) > 0
                action:
                  - assign: { quantity: event.payload.quantity }
                  - assign: { subtotal: quantity }
                  - assign: { total: subtotal * rate }
                  - assign: { has_note: has(event.payload.note) }
                  - assign: { priority: '"vip" in tags && labels["vip"] == "priority"' }
                  - assign: { maps_equal: 'labels == {"standard": "standard", "vip": "priority"}' }
                  - assign: { unicode_rules_hold: 'size("é") == 1 && "a" < "é"' }
                  - assign: { rounded: double(9007199254740993) }
                  - assign: { truncated: int(-2.9) }
                  - assign: { summary: '"priority" + ":" + "vip" + ":" + string(total)' }
                  - assign: { tags: 'tags + ["calculated"]' }
                  - assign: { false_and_error: "false && (1 / 0 == 0)" }
                  - assign: { error_and_false: "(1 / 0 == 0) && false" }
                  - assign: { true_or_error: "true || (1 / 0 == 0)" }
                  - assign: { error_or_true: "(1 / 0 == 0) || true" }
                  - send:
                      event: audit
                      to: { instance: worker }
                      payload:
                        summary: summary
                  - send:
                      event: quote_ready
                      to: { external: true }
                      payload:
                        total: total
                        summary: summary
                        tags: tags
                        priority: priority
                        rounded: rounded
                      correlation_id: event.payload.request_id
              - action:
                  - assign: { summary: '"quantity must be positive"' }
            release_worker:
              action:
                - cancel: { instance: worker }
                - assign: { worker: "null" }
            shutdown:
              action:
                - stop: {}
  - machine_id: audit_worker
    version: 1
    root:
      variables:
        prefix: { type: string, input: true }
        last_summary: { type: string, init: "" }
      on_events:
        audit:
          action:
            - assign: { last_summary: 'prefix + ":" + event.payload.summary' }
```

Several details are intentional:

- `subtotal` is a `float` destination, so assigning the `int` quantity performs the
  one allowed implicit widening. The next action sees that tentative `float`.
- The optional `note` is absent in the trace, so `has_note` becomes `false` without
  reading the missing field.
- The internal target is the nominal `worker` reference created by `spawn`; it is not
  an arbitrary string.
- Each send is an immutable emission. Internal sends do not recursively dispatch;
  the host explicitly delivers the returned internal envelope.
- `cancel` makes a null, disposed, or otherwise non-targetable owned reference a
  no-op. The following assignment clears the nullable holder.
- `stop` is the final action. It completes this root instead of entering another
  target. `stop` cannot appear before another action or in exit behavior; `spawn`
  cannot appear in exit behavior either.

`refresh` is reserved for the accepted `env` envelope. `refresh: {}` selects every
field in `changed`; `refresh.only` selects exactly the listed fields. A selected name
that is absent from `changed` faults the complete step.

## Expression snapshots and deterministic order

An action list is sequential. Each action observes tentative writes made by earlier
actions in the same run-to-completion step. If the step later faults, none of those
writes commit.

Expression maps do not use YAML or JSON member order. One `send` action takes one
state snapshot, then follows this exact order:

1. payload expressions by ascending identifier UTF-8 byte order;
2. `correlation_id`;
3. dynamic `{ instance: CEL }` expressions in target-list order;
4. payload defaults and numeric normalization;
5. target resolution and eligibility in target-list order;
6. identity allocation and immutable emission creation in target-list order.

The first failure decides the fault locator. No later expression runs, and no partial
emission or identity allocation survives.

`targets` is an explicit non-empty ordered fan-out list and cannot be combined with
`to`. Omitting both targets means `self`. Each target gets an independent emission;
there is no implicit broadcast. Static targets are:

```yaml
{ self: true }
{ owner: true }
{ component: component_id }
{ external: true }
```

The dynamic target is `{ instance: CEL }`, whose expression must infer
`instance_reference`. Target expressions are all evaluated before target eligibility
checks, so a later inactive target cannot hide an earlier expression fault.

Component and spawn binding maps have a related one-snapshot rule. `input` expressions
run first, then `external`, with names sorted by UTF-8 bytes inside each map. Every
expression sees the same owner snapshot; computed members cannot observe one another.

## CEL visibility follows lifecycle boundaries

| Location | Bare lexical variables | `event.payload` | `owner.variables` |
|---|---:|---:|---:|
| selected event guard | yes | yes | no |
| selected event action | yes | yes | no |
| entry or exit action | yes | no | no |
| initial-transition action | yes | no | no |
| choice guard or action | yes | no | no |
| spawn binding | yes | only when the spawn action is in a selected event action | no |
| component `with` binding | no | no | yes |

Entry and exit behavior therefore cannot reach backward into the event that caused a
transition. Copy needed event data into a variable during the selected transition
action, while `event` is visible and the source scope is still alive.

## Static mistakes fail when the bundle loads

Every expression is parsed, name-resolved, and type-checked against its exact location.
For example, a guard must infer `bool`, an assignment must fit its destination, a send
payload must fit the event declaration, and a dynamic target must infer
`instance_reference`.

These three complete bundles are intentionally invalid and are checked by repository
validation.

An ambient host clock is not portable:

<!-- determa-example: invalid/cel-host-extension.yaml -->
```yaml
format: 1
namespace: tutorial.invalid_host_extension
events:
  check: { direction: input }
machines:
  - machine_id: invalid_host_extension
    root:
      on_events:
        check:
          guard: now() != null
```

A string cannot flow into an integer destination:

<!-- determa-example: invalid/cel-type-mismatch.yaml -->
```yaml
format: 1
namespace: tutorial.invalid_type
events:
  check: { direction: input }
machines:
  - machine_id: invalid_type
    root:
      variables:
        count: { type: int, init: 0 }
      on_events:
        check:
          action:
            - assign: { count: '"not an integer"' }
```

`event` is unavailable during lifecycle entry:

<!-- determa-example: invalid/cel-lifecycle-event.yaml -->
```yaml
format: 1
namespace: tutorial.invalid_lifecycle_event
events:
  start:
    direction: input
    payload:
      value: { type: string, required: true }
machines:
  - machine_id: invalid_lifecycle_event
    root:
      variables:
        copied: { type: string, init: "" }
      entry:
        - assign: { copied: event.payload.value }
```

Unavailable profile symbols or overloads use `cel_profile_error`. Other CEL
parse/name/type failures use `semantic_validation`. Schema-invalid activation-name or
keyword declarations fail even earlier with `structural_validation`.

## Runtime faults roll back the complete step

A valid expression may still fail for a value-dependent reason. The following bundle
collects focused fault paths. Each event is run against a fresh aggregate in the
executable trace.

<!-- determa-example: machines/cel-faults.yaml -->
```yaml
format: 1
namespace: tutorial.cel_faults
events:
  action_boom: { direction: input }
  guard_boom: { direction: input }
  choice_boom: { direction: input }
  payload_order: { direction: input }
  correlation_order: { direction: input }
  target_order: { direction: input }
  and_boom: { direction: input }
  reversed_and_boom: { direction: input }
  or_boom: { direction: input }
  reversed_or_boom: { direction: input }
  work: { direction: internal }
  result:
    direction: output
    payload:
      alpha: { type: int, required: true }
      beta: { type: int, required: true }
machines:
  - machine_id: fault_lab
    version: 1
    root:
      type: composite
      variables:
        value: { type: int, init: 7 }
        flag: { type: bool, init: false }
        token: { type: string, external: true, init: old }
        region: { type: string, external: true, init: east }
        first_reference:
          type: instance_reference
          machine_id: worker
          nullable: true
          init: null
        second_reference:
          type: instance_reference
          machine_id: worker
          nullable: true
          init: null
      initial: { transition_to: running }
      states:
        running:
          on_events:
            env:
              action:
                - refresh: { only: [token] }
            action_boom:
              action:
                - assign: { value: value + 1 }
                - assign: { value: value / 0 }
            guard_boom:
              guard: 1 / 0 == 0
              action:
                - assign: { value: "99" }
            choice_boom:
              transition_to: deciding
            payload_order:
              action:
                - send:
                    event: result
                    to: { external: true }
                    payload:
                      beta: 2 / 0
                      alpha: 1 / 0
                    correlation_id: string(3 / 0)
            correlation_order:
              action:
                - send:
                    event: work
                    to:
                      instance: "(1 / 0 == 0) ? first_reference : first_reference"
                    correlation_id: string(2 / 0)
            target_order:
              action:
                - send:
                    event: work
                    targets:
                      - instance: "(1 / 0 == 0) ? first_reference : first_reference"
                      - instance: "(2 / 0 == 0) ? second_reference : second_reference"
            and_boom:
              action:
                - assign: { flag: "true && (1 / 0 == 0)" }
            reversed_and_boom:
              action:
                - assign: { flag: "(1 / 0 == 0) && true" }
            or_boom:
              action:
                - assign: { flag: "false || (1 / 0 == 0)" }
            reversed_or_boom:
              action:
                - assign: { flag: "(1 / 0 == 0) || false" }
        deciding:
          choice:
            - guard: 1 / 0 == 0
              transition_to: finished
            - transition_to: running
        finished:
          type: final
  - machine_id: worker
    version: 1
    root: {}
```

For `action_boom`, the first assignment tentatively changes `value` to 8, then the
second action divides by zero. The complete step rolls back, so the committed faulted
aggregate still has `value: 7` and no emissions. `payload_order` faults at `alpha`
because payload keys are evaluated in UTF-8 order, regardless of source member order.
`correlation_order` faults before its dynamic target expression, and `target_order`
faults at target zero.

The four Boolean fault events cover the non-absorbed cells in both truth tables.
`choice_boom` demonstrates that a value-dependent choice guard also rolls back the
transition that reached the choice.

`env` supplies only `region`, while `refresh.only` requires `token`. That produces an
`action_fault`; both external variables retain their old values.

An ordinary action-expression error is `action_fault`; a guard or choice-guard error is
`guard_fault`. The failing input remains caller-owned, the faulting step emits nothing,
and a root fault is terminal.

## Run the complete trace with Python

Install the pinned engine:

```sh
python -m pip install determa-state==0.0.7
```

<!-- determa-example: python/cel_actions.py -->
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


def input_delivery(state, event, event_id, payload=None):
    return {
        "input": {
            "event": event,
            "event_id": event_id,
            "target": root_target(state),
            "payload": payload or {},
        }
    }


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


def root_variables(state):
    root = state["runtimes"][state["root_runtime_id"]]
    return root["scopes"]["root"]


def check_guards(bundle):
    state = create_state(bundle, "guard_order", "tutorial-guards")
    observed = []
    for quantity, expected in ((3, "standard"), (20, "bulk"), (0, "empty")):
        checked = ds.dispatch(
            bundle,
            state,
            input_delivery(
                state,
                "check",
                f"tutorial-guards:check:{quantity}",
                {"quantity": quantity},
            ),
        )
        state = checked["state"]
        observed.append(state["runtimes"][state["root_runtime_id"]]["active"][-1])
        assert observed[-1] == expected
        if quantity != 0:
            reset = ds.dispatch(
                bundle,
                state,
                input_delivery(
                    state,
                    "reset",
                    f"tutorial-guards:reset:{quantity}",
                ),
            )
            state = reset["state"]
    assert observed == ["standard", "bulk", "empty"]


def check_actions(bundle):
    state = create_state(bundle, "checkout", "tutorial-actions")
    variables = root_variables(state)
    worker_reference = variables["worker"]
    assert worker_reference["machine_id"] == "audit_worker"

    refreshed = ds.dispatch(
        bundle,
        state,
        input_delivery(
            state,
            "env",
            "tutorial-actions:env",
            {"changed": {"rate": 1.5}},
        ),
    )
    assert refreshed["disposition"] == "handled"
    state = refreshed["state"]
    assert root_variables(state)["rate"] == 1.5

    evaluated = ds.dispatch(
        bundle,
        state,
        input_delivery(
            state,
            "evaluate",
            "tutorial-actions:evaluate",
            {"quantity": 3, "request_id": "quote-42"},
        ),
    )
    assert evaluated["disposition"] == "handled"
    assert [emission["event"] for emission in evaluated["emissions"]] == [
        "audit",
        "quote_ready",
    ]
    state = evaluated["state"]
    variables = root_variables(state)
    assert variables["subtotal"] == 3.0
    assert variables["total"] == 4.5
    assert variables["has_note"] is False
    assert variables["priority"] is True
    assert variables["maps_equal"] is True
    assert variables["unicode_rules_hold"] is True
    assert variables["rounded"] == 9007199254740992.0
    assert variables["truncated"] == -2
    assert variables["tags"] == ["vip", "new", "calculated"]
    assert variables["false_and_error"] is False
    assert variables["error_and_false"] is False
    assert variables["true_or_error"] is True
    assert variables["error_or_true"] is True

    internal = evaluated["emissions"][0]
    external = evaluated["emissions"][1]
    assert external["target"] == "external"
    assert external["payload"]["total"] == 4.5
    assert external["correlation_id"] == "quote-42"

    audited = ds.dispatch(bundle, state, {"internal": internal})
    assert audited["disposition"] == "handled"
    state = audited["state"]
    worker = state["runtimes"][worker_reference["instance_id"]]
    audit_summary = worker["scopes"]["root"]["last_summary"]
    assert audit_summary == "audit:priority:vip:4.5"

    released = ds.dispatch(
        bundle,
        state,
        input_delivery(
            state,
            "release_worker",
            "tutorial-actions:release-worker",
        ),
    )
    assert released["status"] == "running"
    state = released["state"]
    assert root_variables(state)["worker"] is None
    assert len(state["runtimes"]) == 1

    stopped = ds.dispatch(
        bundle,
        state,
        input_delivery(state, "shutdown", "tutorial-actions:shutdown"),
    )
    assert stopped["status"] == "completed"
    assert len(stopped["state"]["runtimes"]) == 1
    return audit_summary


def assert_fault(bundle, event, code, locator):
    state = create_state(bundle, "fault_lab", f"tutorial-fault:{event}")
    result = ds.dispatch(
        bundle,
        state,
        input_delivery(state, event, f"tutorial-fault:{event}:input"),
    )
    assert result["status"] == "faulted"
    assert result["disposition"] == "faulted"
    assert result["fault"]["code"] == code
    assert result["fault"]["source_locator"] == locator
    assert root_variables(result["state"])["value"] == 7
    assert result["emissions"] == []


def check_faults(bundle):
    base = "/machines/0/root/states/running/on_events"
    cases = {
        "action_boom": (
            "action_fault",
            f"{base}/action_boom/action/1/assign/value",
        ),
        "guard_boom": ("guard_fault", f"{base}/guard_boom/guard"),
        "payload_order": (
            "action_fault",
            f"{base}/payload_order/action/0/send/payload/alpha",
        ),
        "correlation_order": (
            "action_fault",
            f"{base}/correlation_order/action/0/send/correlation_id",
        ),
        "target_order": (
            "action_fault",
            f"{base}/target_order/action/0/send/targets/0/instance",
        ),
        "and_boom": (
            "action_fault",
            f"{base}/and_boom/action/0/assign/flag",
        ),
        "reversed_and_boom": (
            "action_fault",
            f"{base}/reversed_and_boom/action/0/assign/flag",
        ),
        "or_boom": (
            "action_fault",
            f"{base}/or_boom/action/0/assign/flag",
        ),
        "reversed_or_boom": (
            "action_fault",
            f"{base}/reversed_or_boom/action/0/assign/flag",
        ),
        "choice_boom": (
            "guard_fault",
            "/machines/0/root/states/deciding/choice/0/guard",
        ),
    }
    for event, (code, locator) in cases.items():
        assert_fault(bundle, event, code, locator)

    state = create_state(bundle, "fault_lab", "tutorial-fault:refresh")
    refreshed = ds.dispatch(
        bundle,
        state,
        input_delivery(
            state,
            "env",
            "tutorial-fault:refresh:input",
            {"changed": {"region": "west"}},
        ),
    )
    assert refreshed["status"] == "faulted"
    assert refreshed["fault"]["code"] == "action_fault"
    assert refreshed["fault"]["source_locator"].endswith(
        "/on_events/env/action/0/refresh/only/0"
    )
    variables = root_variables(refreshed["state"])
    assert variables["token"] == "old"
    assert variables["region"] == "east"


def check_invalid(paths):
    expected = {
        "cel-host-extension.yaml": "cel_profile_error",
        "cel-type-mismatch.yaml": "semantic_validation",
        "cel-lifecycle-event.yaml": "semantic_validation",
    }
    for path in paths:
        try:
            ds.load_bundle(path.read_text())
        except ds.ValidationError as error:
            assert error.code == expected[path.name]
        else:
            raise AssertionError(f"{path} unexpectedly loaded")


guard_path, actions_path, faults_path, *invalid_paths = map(Path, sys.argv[1:])
guard_bundle = ds.load_bundle(guard_path.read_text())
actions_bundle = ds.load_bundle(actions_path.read_text())
faults_bundle = ds.load_bundle(faults_path.read_text())

check_guards(guard_bundle)
audit_summary = check_actions(actions_bundle)
check_faults(faults_bundle)
check_invalid(invalid_paths)
print(f"guards=standard,bulk,empty; total=4.5; audit={audit_summary}; faults=11")
```

## Run the same trace with Rust

<!-- determa-example: rust/cel-actions/Cargo.toml -->
```toml
[package]
name = "determa-cel-actions"
version = "0.1.0"
edition = "2021"
publish = false

[dependencies]
determa-state = "=0.0.7"
```

<!-- determa-example: rust/cel-actions/src/main.rs -->
```rust
use determa_state::{
    create, dispatch, load_bundle, AggregateState, Bindings, Delivery, Disposition,
    Envelope, LoadErrorCode, ResultStatus, Target, Value,
};
use std::{collections::BTreeMap, env, fs, path::Path};

fn root_target(state: &AggregateState) -> Target {
    Target::Root {
        root_instance_id: state.root_instance_id.clone(),
        root_runtime_id: state.root.runtime_id.clone(),
    }
}

fn input_delivery(
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

fn create_state(
    bundle: &determa_state::Bundle,
    machine_id: &str,
    instance_id: &str,
) -> AggregateState {
    let created = create(
        bundle,
        machine_id,
        instance_id,
        &format!("{instance_id}:create"),
        &Bindings::default(),
    );
    assert_eq!(created.status, ResultStatus::Running);
    created.state.expect("creation succeeds")
}

fn check_guards(bundle: &determa_state::Bundle) {
    let mut state = create_state(bundle, "guard_order", "tutorial-guards");
    let mut observed = Vec::new();
    for (quantity, expected) in [(3, "standard"), (20, "bulk"), (0, "empty")] {
        let checked = dispatch(
            bundle,
            &state,
            Some(input_delivery(
                &state,
                "check",
                &format!("tutorial-guards:check:{quantity}"),
                BTreeMap::from([("quantity".to_string(), Value::Int(quantity))]),
            )),
        );
        state = checked.state.expect("guard dispatch succeeds");
        observed.push(state.root.config()[0].clone());
        assert_eq!(observed.last().map(String::as_str), Some(expected));
        if quantity != 0 {
            let reset = dispatch(
                bundle,
                &state,
                Some(input_delivery(
                    &state,
                    "reset",
                    &format!("tutorial-guards:reset:{quantity}"),
                    BTreeMap::new(),
                )),
            );
            state = reset.state.expect("reset succeeds");
        }
    }
    assert_eq!(observed, ["standard", "bulk", "empty"]);
}

fn check_actions(bundle: &determa_state::Bundle) -> String {
    let mut state = create_state(bundle, "checkout", "tutorial-actions");
    let worker_reference = match &state.root.visible_variables()["worker"] {
        Value::InstanceReference(reference) => reference.clone(),
        value => panic!("expected worker reference, found {value:?}"),
    };
    assert_eq!(worker_reference.machine_id, "audit_worker");

    let refreshed = dispatch(
        bundle,
        &state,
        Some(input_delivery(
            &state,
            "env",
            "tutorial-actions:env",
            BTreeMap::from([(
                "changed".to_string(),
                Value::Map(BTreeMap::from([(
                    "rate".to_string(),
                    Value::Float(1.5),
                )])),
            )]),
        )),
    );
    assert_eq!(refreshed.disposition, Some(Disposition::Handled));
    state = refreshed.state.expect("refresh succeeds");
    assert_eq!(state.root.visible_variables()["rate"], Value::Float(1.5));

    let evaluated = dispatch(
        bundle,
        &state,
        Some(input_delivery(
            &state,
            "evaluate",
            "tutorial-actions:evaluate",
            BTreeMap::from([
                ("quantity".to_string(), Value::Int(3)),
                (
                    "request_id".to_string(),
                    Value::String("quote-42".to_string()),
                ),
            ]),
        )),
    );
    assert_eq!(evaluated.disposition, Some(Disposition::Handled));
    assert_eq!(
        evaluated
            .emissions
            .iter()
            .map(|emission| emission.event.as_str())
            .collect::<Vec<_>>(),
        ["audit", "quote_ready"]
    );
    let emissions = evaluated.emissions.clone();
    state = evaluated.state.expect("evaluation succeeds");
    let variables = state.root.visible_variables();
    assert_eq!(variables["subtotal"], Value::Float(3.0));
    assert_eq!(variables["total"], Value::Float(4.5));
    assert_eq!(variables["has_note"], Value::Bool(false));
    assert_eq!(variables["priority"], Value::Bool(true));
    assert_eq!(variables["maps_equal"], Value::Bool(true));
    assert_eq!(variables["unicode_rules_hold"], Value::Bool(true));
    assert_eq!(
        variables["rounded"],
        Value::Float(9007199254740992.0)
    );
    assert_eq!(variables["truncated"], Value::Int(-2));
    assert_eq!(
        variables["tags"],
        Value::List(vec![
            Value::String("vip".to_string()),
            Value::String("new".to_string()),
            Value::String("calculated".to_string()),
        ])
    );
    assert_eq!(variables["false_and_error"], Value::Bool(false));
    assert_eq!(variables["error_and_false"], Value::Bool(false));
    assert_eq!(variables["true_or_error"], Value::Bool(true));
    assert_eq!(variables["error_or_true"], Value::Bool(true));

    assert!(matches!(emissions[1].target, Target::External));
    assert_eq!(emissions[1].payload["total"], Value::Float(4.5));
    assert_eq!(emissions[1].correlation_id.as_deref(), Some("quote-42"));

    let audited = dispatch(
        bundle,
        &state,
        Some(Delivery::Internal(
            emissions[0].envelope().expect("internal emission has envelope"),
        )),
    );
    assert_eq!(audited.disposition, Some(Disposition::Handled));
    state = audited.state.expect("audit delivery succeeds");
    let worker = state
        .root
        .owned_instances
        .iter()
        .find(|owned| owned.reference == worker_reference)
        .expect("worker remains owned");
    let audit_summary = match &worker.runtime.visible_variables()["last_summary"] {
        Value::String(value) => value.clone(),
        value => panic!("expected audit summary, found {value:?}"),
    };
    assert_eq!(audit_summary, "audit:priority:vip:4.5");

    let released = dispatch(
        bundle,
        &state,
        Some(input_delivery(
            &state,
            "release_worker",
            "tutorial-actions:release-worker",
            BTreeMap::new(),
        )),
    );
    assert_eq!(released.status, ResultStatus::Running);
    state = released.state.expect("release returns running state");
    assert_eq!(state.root.visible_variables()["worker"], Value::Null);
    assert!(state.root.owned_instances.is_empty());

    let stopped = dispatch(
        bundle,
        &state,
        Some(input_delivery(
            &state,
            "shutdown",
            "tutorial-actions:shutdown",
            BTreeMap::new(),
        )),
    );
    assert_eq!(stopped.status, ResultStatus::Completed);
    let stopped_state = stopped.state.expect("stop returns completed state");
    assert!(stopped_state.root.owned_instances.is_empty());
    audit_summary
}

fn assert_fault(
    bundle: &determa_state::Bundle,
    event: &str,
    code: &str,
    locator: &str,
) {
    let state = create_state(bundle, "fault_lab", &format!("tutorial-fault:{event}"));
    let result = dispatch(
        bundle,
        &state,
        Some(input_delivery(
            &state,
            event,
            &format!("tutorial-fault:{event}:input"),
            BTreeMap::new(),
        )),
    );
    assert_eq!(result.status, ResultStatus::Faulted);
    assert_eq!(result.disposition, Some(Disposition::Faulted));
    let fault = result.fault.expect("fault record");
    assert_eq!(fault.code, code);
    assert_eq!(fault.source_locator, locator);
    let faulted = result.state.expect("fault returns diagnostic state");
    assert_eq!(faulted.root.visible_variables()["value"], Value::Int(7));
    assert!(result.emissions.is_empty());
}

fn check_faults(bundle: &determa_state::Bundle) {
    let base = "/machines/0/root/states/running/on_events";
    let cases = [
        (
            "action_boom",
            "action_fault",
            format!("{base}/action_boom/action/1/assign/value"),
        ),
        (
            "guard_boom",
            "guard_fault",
            format!("{base}/guard_boom/guard"),
        ),
        (
            "payload_order",
            "action_fault",
            format!("{base}/payload_order/action/0/send/payload/alpha"),
        ),
        (
            "correlation_order",
            "action_fault",
            format!("{base}/correlation_order/action/0/send/correlation_id"),
        ),
        (
            "target_order",
            "action_fault",
            format!("{base}/target_order/action/0/send/targets/0/instance"),
        ),
        (
            "and_boom",
            "action_fault",
            format!("{base}/and_boom/action/0/assign/flag"),
        ),
        (
            "reversed_and_boom",
            "action_fault",
            format!("{base}/reversed_and_boom/action/0/assign/flag"),
        ),
        (
            "or_boom",
            "action_fault",
            format!("{base}/or_boom/action/0/assign/flag"),
        ),
        (
            "reversed_or_boom",
            "action_fault",
            format!("{base}/reversed_or_boom/action/0/assign/flag"),
        ),
        (
            "choice_boom",
            "guard_fault",
            "/machines/0/root/states/deciding/choice/0/guard".to_string(),
        ),
    ];
    for (event, code, locator) in cases {
        assert_fault(bundle, event, code, &locator);
    }

    let state = create_state(bundle, "fault_lab", "tutorial-fault:refresh");
    let refreshed = dispatch(
        bundle,
        &state,
        Some(input_delivery(
            &state,
            "env",
            "tutorial-fault:refresh:input",
            BTreeMap::from([(
                "changed".to_string(),
                Value::Map(BTreeMap::from([(
                    "region".to_string(),
                    Value::String("west".to_string()),
                )])),
            )]),
        )),
    );
    assert_eq!(refreshed.status, ResultStatus::Faulted);
    let fault = refreshed.fault.expect("refresh fault");
    assert_eq!(fault.code, "action_fault");
    assert!(
        fault
            .source_locator
            .ends_with("/on_events/env/action/0/refresh/only/0")
    );
    let faulted = refreshed.state.expect("refresh returns diagnostic state");
    let variables = faulted.root.visible_variables();
    assert_eq!(variables["token"], Value::String("old".to_string()));
    assert_eq!(variables["region"], Value::String("east".to_string()));
}

fn check_invalid(paths: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    let expected = [
        ("cel-host-extension.yaml", LoadErrorCode::CelProfileError),
        ("cel-type-mismatch.yaml", LoadErrorCode::SemanticValidation),
        (
            "cel-lifecycle-event.yaml",
            LoadErrorCode::SemanticValidation,
        ),
    ];
    for path in paths {
        let name = Path::new(path)
            .file_name()
            .and_then(|name| name.to_str())
            .expect("UTF-8 fixture name");
        let expected_code = expected
            .iter()
            .find(|(candidate, _)| *candidate == name)
            .map(|(_, code)| code)
            .expect("known invalid fixture");
        let error = load_bundle(&fs::read_to_string(path)?).expect_err("bundle must fail");
        assert_eq!(&error.code, expected_code);
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let paths = env::args().skip(1).collect::<Vec<_>>();
    let guard_bundle = load_bundle(&fs::read_to_string(&paths[0])?)?;
    let actions_bundle = load_bundle(&fs::read_to_string(&paths[1])?)?;
    let faults_bundle = load_bundle(&fs::read_to_string(&paths[2])?)?;

    check_guards(&guard_bundle);
    let audit_summary = check_actions(&actions_bundle);
    check_faults(&faults_bundle);
    check_invalid(&paths[3..])?;
    println!(
        "guards=standard,bulk,empty; total=4.5; audit={audit_summary}; faults=11"
    );
    Ok(())
}
```

Extract and run the authored files:

```sh
make extract
python .cache/examples/python/cel_actions.py \
  .cache/examples/machines/guard-order.yaml \
  .cache/examples/machines/cel-actions.yaml \
  .cache/examples/machines/cel-faults.yaml \
  .cache/examples/invalid/cel-host-extension.yaml \
  .cache/examples/invalid/cel-type-mismatch.yaml \
  .cache/examples/invalid/cel-lifecycle-event.yaml
cargo run --manifest-path .cache/examples/rust/cel-actions/Cargo.toml -- \
  .cache/examples/machines/guard-order.yaml \
  .cache/examples/machines/cel-actions.yaml \
  .cache/examples/machines/cel-faults.yaml \
  .cache/examples/invalid/cel-host-extension.yaml \
  .cache/examples/invalid/cel-type-mismatch.yaml \
  .cache/examples/invalid/cel-lifecycle-event.yaml
```

Both programs print:

```text
guards=standard,bulk,empty; total=4.5; audit=audit:priority:vip:4.5; faults=11
```

Repository validation parses every extracted YAML document as YAML 1.2, checks it
against the pinned schema, checks the expected semantic result, and executes both
language traces. The code above is the tested source, not pseudocode.

## Coverage

This chapter covers the format-1 structured-action and CEL rules linked below. The
matching Determa State v0.0.7 conformance cases are:

- [12 guarded list](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/12-guarded-list)
- [17 action fault](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/17-action-fault)
- [61 expression map order](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/61-expression-map-order)
- [64 dynamic target expression order](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/64-dynamic-target-expression-order)
- [65 portable CEL profile](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/65-portable-cel-profile)
- [66 CEL profile rejections](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/66-cel-profile-rejections)
- [68 CEL AND non-absorbed error](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/68-cel-and-nonabsorbed-error)
- [69 CEL OR non-absorbed error](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/69-cel-or-nonabsorbed-error)
- [70 dynamic target list order](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/70-dynamic-target-list-order)
- [71 reversed CEL AND non-absorbed error](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/71-cel-reversed-and-nonabsorbed-error)
- [72 reversed CEL OR non-absorbed error](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/72-cel-reversed-or-nonabsorbed-error)
- [79 missing refresh field](https://github.com/fruwehq/determa-state-conformance/tree/v0.0.7/conformance/core/79-missing-refresh-field)

Normative references:
[structured actions §4.8](https://github.com/fruwehq/determa-state-spec/blob/v0.0.7/SPEC.md#48-structured-actions),
[static validation and CEL §5](https://github.com/fruwehq/determa-state-spec/blob/v0.0.7/SPEC.md#5-static-validation-and-cel),
[portable CEL profile](https://github.com/fruwehq/determa-state-spec/blob/v0.0.7/SPEC.md#portable-cel-profile),
and
[faults §10](https://github.com/fruwehq/determa-state-spec/blob/v0.0.7/SPEC.md#10-faults-and-envelope-disposition).
