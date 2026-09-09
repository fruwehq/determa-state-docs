# Durable execution checkpoints

The pure Determa State engine handles one delivery and returns the next aggregate. In
many applications that is exactly the right boundary: the application already owns its
database transaction and queue. Determa State 0.2.0 also provides an optional
`ExecutionHost` for applications that want a portable, durable inbox, state, receipts,
and outbox around that same pure core.

An execution checkpoint belongs to one root ownership aggregate. It contains the
current serialized aggregate (or a terminal tombstone), accepted deliveries, operation
receipts, outbox records, retention evidence, and migration audit. A delivery that the
host reports as accepted is therefore not memory-only.

The checkpoint does not contain database credentials, locks, leases, broker
acknowledgement tokens, running network requests, timers, or plugin configuration.
Those remain host resources. An external effect intent can be serialized before an
adapter attempts it; the adapter's active HTTP call cannot. Stop accepting work, let
active adapter calls finish or record them as ambiguous according to host policy, and
the checkpoint remains portable and restartable.

## 1. Create the project

```sh
mkdir determa-checkpoint-tutorial
cd determa-checkpoint-tutorial
python -m venv .venv
. .venv/bin/activate
python -m pip install determa-state==0.2.0
```

This tutorial uses SQLite so that stopping the Python process does not erase accepted
work. The same host accepts an `ExecutionStore` object directly, so an application can
instead inject memory, file, PostgreSQL, or its own adapter.

## 2. Define a workflow

<!-- determa-example: checkpoint-tutorial/counter.yaml -->
```yaml
format: 1
namespace: tutorial.checkpoint
events:
  increment:
    direction: input
    payload:
      request_id: { type: string, required: true }
      amount: { type: int, required: true }
  count_changed:
    direction: output
    payload:
      count: { type: int, required: true }
machines:
  - machine_id: counter
    version: 1
    root:
      variables:
        count: { type: int, init: 0 }
      on_events:
        increment:
          action:
            - assign: { count: "count + event.payload.amount" }
            - send:
                event: count_changed
                to: { external: true }
                correlation_id: event.payload.request_id
                payload: { count: count }
```

Save this as `counter.yaml`. The action produces an external **intent**. Committing the
intent to the checkpoint outbox does not claim that another system received it.

Only current format-1 bundles are accepted. A current document must contain numeric
`format: 1`, a namespace, and a `machines` list. Determa does not infer the grammar from
an old document's shape or silently upgrade it.

## 3. Register and select storage

The registry starts empty. Bundled adapters are registered through the same public
operation used by third-party adapters; no scheme receives special treatment in the
host:

```python
registry = ds.ExecutionStoreRegistry()
ds.register_bundled_execution_stores(registry, include_postgresql=False)
store = registry.resolve(
    "sqlite:///absolute/path/state.db"
    "?replay_retention=permanent&outbox_retention=strict"
)
store.setup_schema()
```

URI resolution selects a factory by its lowercase scheme. The factory owns the rest of
the URI and its configuration. Applications that do not need discovery can instantiate
or implement `ExecutionStore` directly.

Storage setup is always explicit. Memory is ephemeral; file storage is restart
persistent; SQLite advertises durable single-writer behavior after validating its
schema and settings; PostgreSQL can provide concurrent compare-and-swap and a shared
application transaction. Required capabilities fail closed instead of silently
downgrading a requested guarantee.

## 4. Accept, restart, and process one event

<!-- determa-example: checkpoint-tutorial/app.py -->
```python
from pathlib import Path
import sys

import determa.state as ds


def open_host(machine_path, database_path):
    bundle = ds.load_bundle(Path(machine_path).read_text())
    resolver = ds.MemoryArtifactResolver(
        definitions={bundle.fingerprint: bundle}
    )
    registry = ds.ExecutionStoreRegistry()
    ds.register_bundled_execution_stores(
        registry, include_postgresql=False
    )
    uri = (
        f"sqlite://{Path(database_path).resolve()}"
        "?replay_retention=permanent&outbox_retention=strict"
    )
    store = registry.resolve(uri)
    store.setup_schema()
    required = {
        ds.DURABLE_SINGLE_WRITER,
        ds.ROOT_IDENTITY_RETENTION,
        ds.PERMANENT_RECEIPT_RETENTION,
        ds.PERMANENT_OUTBOX_TERMINAL_RETENTION,
    }
    host = ds.ExecutionHost(
        store,
        resolver,
        required_capabilities=required,
        profile="exactly_once_committed_processing",
    )
    return bundle, host


def delivery(checkpoint):
    aggregate = checkpoint["root_record"]["aggregate_state"]
    return {
        "root_instance_id": checkpoint["root_instance_id"],
        "delivery_mode": "input",
        "origin": {"kind": "host_input"},
        "envelope": ds.portable_envelope(
            "increment",
            "counter:increment:1",
            {
                "root": {
                    "root_instance_id": checkpoint["root_instance_id"],
                    "root_runtime_id": aggregate["root_runtime_id"],
                }
            },
            {"request_id": "request-1", "amount": 4},
        ),
    }


machine_path, database_path = sys.argv[1:]
database = Path(database_path)
if database.exists():
    database.unlink()

bundle, host = open_host(machine_path, database)
created = host.create(
    bundle,
    machine_id="counter",
    root_instance_id="counter-1",
    creation_id="counter-1:create",
    bindings={},
)
assert created["result"] == "committed"

checkpoint = host.read_checkpoint("counter-1").document
candidate = delivery(checkpoint)
pending = host.accept_delivery(
    "counter-1",
    candidate,
    expected_revision=checkpoint["revision"],
    expected_checkpoint_digest=checkpoint["execution_checkpoint_digest"],
)
assert pending["result"] == "pending"

# Recreate the store and host to prove the accepted event was not process memory.
bundle, restarted = open_host(machine_path, database)
accepted = restarted.read_checkpoint("counter-1").document
assert len(accepted["pending_deliveries"]) == 1
committed = restarted.process_pending_delivery(
    "counter-1",
    candidate,
    expected_revision=accepted["revision"],
    expected_checkpoint_digest=accepted["execution_checkpoint_digest"],
)
assert committed["result"] == "committed"
assert committed["receipt"]["outcome"]["disposition"] == "handled"

final = restarted.read_checkpoint("counter-1")
assert final.aggregate is not None
root = final.aggregate.state["runtimes"][
    final.aggregate.state["root_runtime_id"]
]
assert root["scopes"]["root"]["count"] == 4
assert final.document["revision"] == "2"
assert len(final.document["pending_deliveries"]) == 0
assert len(final.document["operation_receipts"]) == 2
assert len(final.document["pending_outbox_intents"]) == 1

replay = restarted.accept_delivery(
    "counter-1",
    candidate,
    expected_revision=checkpoint["revision"],
    expected_checkpoint_digest=checkpoint["execution_checkpoint_digest"],
)
assert replay == committed
print(
    "revision=2; count=4; receipts=2; "
    "pending=0; outbox=1; replay=committed"
)
```

Save it as `app.py`, then run:

```sh
python app.py counter.yaml state.db
```

Expected output:

```text
revision=2; count=4; receipts=2; pending=0; outbox=1; replay=committed
```

Creation commits revision `0`. Accepting the event commits revision `1` with the full
envelope in `pending_deliveries`. Processing it commits revision `2`, consumes the
pending item, adds a durable receipt, updates the aggregate, and adds the complete
external intent to the outbox. Re-presenting the same event ID and bytes returns the
committed receipt without calling the engine again. Reusing the ID with different
content is a conflict.

## 5. Choose the foreground boundary deliberately

`accept_delivery` followed by `process_pending_delivery` is useful when acceptance and
execution happen at different times. `foreground_process_delivery` performs both in
one checkpoint transaction. Both paths have the same committed receipt and replay
rules.

An application may also skip `ExecutionHost` and call the pure `create`, `dispatch`,
serialization, and migration functions inside its own transaction. The optional host
is a library layer, not a daemon and not a required executable.

Every mutation uses the expected checkpoint revision and digest. A stale writer fails
instead of replacing newer work. PostgreSQL applications can compose one checkpoint
mutation with their own rows in a shared serializable transaction. SQLite provides a
durable single-writer profile, not cross-process distributed ACID.

## 6. Treat the outbox as unfinished work

External output records move through an explicit lifecycle. A delivery worker may
claim an intent, record success, record a known failure, or record an ambiguous result
when it cannot know whether the remote side accepted the request. Strict retention
keeps terminal records; compact retention keeps identity evidence while allowing full
terminal payloads to be removed.

Exactly-once **committed processing** means an accepted event ID is committed once
within one authorized store scope. It does not mean an HTTP request, broker publish, or
payment happens exactly once. External delivery still needs `effect_id` idempotency and
reconciliation. Broker acknowledgement happens only after the checkpoint transaction
commits.

A checkpoint can remain dormant indefinitely because no hidden engine worker must be
kept alive. Before pausing a host, stop new claims and account for already active
adapter calls. The portable checkpoint records pending and ambiguous intent state, not
the transient call stack of an adapter.

## 7. Retention, terminal roots, and migration

Permanent receipt retention preserves replay decisions and root non-reuse. Bounded
retention deliberately weakens those guarantees after its declared horizon. Completed
or faulted roots can be replaced by a tombstone only after pending delivery and outbox
requirements are satisfied; a tombstoned root identity cannot be recreated.

Definition migration remains the pure, explicit process taught in the
[persistence and migration tutorial](persistence-and-migration.md). A checkpoint host
can apply a keyed migration operation and retain its receipt and ordered audit in the
same transaction. It never guesses that the latest YAML is compatible.

Store scopes are host-selected trust boundaries. Scope identity and authorization are
not fields in portable machine, aggregate, event, intent, or checkpoint bytes. Equal
portable identities may exist independently in two correctly isolated scopes.

## 8. What 0.2.0 deliberately does not provide

The released checkpoint host does not provide a broker, delivery daemon, socket
service, remote client, native effect handler, timer scheduler, backup/relocation
protocol, or candidate-enabledness API. It also does not make active adapter calls
serializable. Those are separate host concerns or future work, not implied by this
tutorial.

Timer durability is reserved for future design. Today a machine can emit a declared
scheduling intent and later accept a declared event from an external scheduler, as
shown in [effects, faults, and hosting](effects-faults-hosting.md). No timer record is
part of execution-checkpoint schema version 1.

## Normative coverage

This guide explains the released execution-checkpoint contract:

- [§17 portable execution checkpoints and hosting adapters](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#17-portable-execution-checkpoints-and-hosting-adapters)
- [§17.1 scope and compatibility](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#171-scope-and-compatibility)
- [§17.2 closed checkpoint artifact](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#172-closed-checkpoint-artifact)
- [§17.3 durable operation receipts and replay](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#173-durable-operation-receipts-and-replay)
- [§17.4 unified pending deliveries](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#174-unified-pending-deliveries)
- [§17.5 maintenance-migration operations](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#175-maintenance-migration-operations)
- [§17.6 durable outbox lifecycle](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#176-durable-outbox-lifecycle)
- [§17.7 migration audit and canonical ordering](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#177-migration-audit-and-canonical-ordering)
- [§17.8 replay retention and root lifecycle](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#178-replay-retention-and-root-lifecycle)
- [§17.9 transaction and concurrency ordering](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#179-transaction-and-concurrency-ordering)
- [§17.10 execution-store registration and resolution](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#1710-execution-store-registration-and-resolution)
- [§17.11 execution-store capabilities and composed host profiles](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#1711-execution-store-capabilities-and-composed-host-profiles)
- [§17.12 exact guarantee boundary](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#1712-exact-guarantee-boundary)
- [§17.13 cluster checkpoint composition](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#1713-cluster-checkpoint-composition)
- [§17.14 future timer durability](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#1714-future-timer-durability)
