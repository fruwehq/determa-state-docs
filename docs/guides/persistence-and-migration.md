# Persistence and definition migration

This tutorial starts in an empty directory and builds a small, complete SQLite host.
It stores a portable aggregate, ignores a duplicate input, records an output intent,
restarts between commands, and lazily upgrades a live order from machine version 1 to
version 2.

The tutorial uses Determa State 0.2.0 and numeric `format: 1`. The normative rules are
in [specification section 16](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#16-portable-persistence-and-definition-migration).

## 1. Create an empty project

```sh
mkdir determa-persistence-tutorial
cd determa-persistence-tutorial
python3 -m venv .venv
. .venv/bin/activate
python -m pip install determa-state==0.2.0
mkdir -p rust/src
```

Nothing below depends on this documentation repository. Each file is shown in full.

## 2. Define version 1

The first definition accepts an order, emits a shipment intent, and waits in
`awaiting_fulfillment`.

<!-- determa-example: persistence-tutorial/order-v1.yaml -->
```yaml
format: 1
namespace: tutorial.persistence
events:
  submit:
    direction: input
    payload:
      order_id: { type: string, required: true }
  complete:
    direction: input
  shipment_requested:
    direction: output
    payload:
      order_id: { type: string, required: true }
machines:
  - machine_id: order
    version: 1
    root:
      type: composite
      variables:
        order_id: { type: string, init: "" }
      initial: { transition_to: pending }
      states:
        pending:
          on_events:
            submit:
              transition_to: awaiting_fulfillment
              action:
                - assign: { order_id: "event.payload.order_id" }
                - send:
                    event: shipment_requested
                    to: { external: true }
                    correlation_id: "event.payload.order_id"
                    payload:
                      order_id: "event.payload.order_id"
        awaiting_fulfillment:
          on_events:
            complete: { transition_to: done }
        done: { type: final }
```

Save it as `order-v1.yaml`.

## 3. Define version 2

Version 2 renames the live state to `awaiting_shipping`. That is a state-bearing
change: an aggregate already in the deleted v1 state cannot simply be opened with v2.

<!-- determa-example: persistence-tutorial/order-v2.yaml -->
```yaml
format: 1
namespace: tutorial.persistence
meta:
  release: v2
events:
  submit:
    direction: input
    payload:
      order_id: { type: string, required: true }
  complete:
    direction: input
  shipment_requested:
    direction: output
    payload:
      order_id: { type: string, required: true }
machines:
  - machine_id: order
    version: 2
    root:
      type: composite
      variables:
        order_id: { type: string, init: "" }
      initial: { transition_to: pending }
      states:
        pending:
          on_events:
            submit:
              transition_to: awaiting_shipping
              action:
                - assign: { order_id: "event.payload.order_id" }
                - send:
                    event: shipment_requested
                    to: { external: true }
                    correlation_id: "event.payload.order_id"
                    payload:
                      order_id: "event.payload.order_id"
        awaiting_shipping:
          on_events:
            complete: { transition_to: done }
        done: { type: final }
```

Save it as `order-v2.yaml`.

## 4. Describe the migration

A migration descriptor is immutable data. It names exact source and target definition
fingerprints, maps every retained field, and has its own digest. The deployment must
trust these exact digests; Determa never searches for or invents a route.

First create an intentionally incomplete descriptor. Its empty `active_states` array
does not say what should replace the deleted active state.

<!-- determa-example: persistence-tutorial/migration-missing-state.json -->
```json
{
  "migration_descriptor_format": "determa.aggregate_migration",
  "migration_descriptor_schema_version": 1,
  "source_machine_format": 1,
  "target_machine_format": 1,
  "source_validated_bundle_fingerprint": "sha256:e8ebf83dc88ba698f6e550945958a8059d5a15cd70d7d5c5e4864e3ab8c538e0",
  "target_validated_bundle_fingerprint": "sha256:e046130705827409a6263442a7f0c81c4153fee00f7d217600b3f6587334bf8a",
  "source_aggregate_shape_fingerprint": "sha256:b6d2096a63d6feee54a708d3144f01ddbc568c20500f1547a1de771519144143",
  "target_aggregate_shape_fingerprint": "sha256:0e97046b585ae04ffc523b94785ce7180e6bb92ca03a901fd3f998294f4b64fd",
  "mode": "transform",
  "mappings": {
    "machines": [{"source_definition_pointer": "/machines/0/root", "target_definition_pointer": "/machines/0/root"}],
    "active_states": [],
    "variables": [{"operation": "copy", "source_declaration_pointer": "/machines/0/root/variables/order_id", "target_declaration_pointer": "/machines/0/root/variables/order_id"}],
    "history": [],
    "components": [],
    "owned_runtimes": [],
    "lifetime_holders": [],
    "counters": [
      {"operation": "map", "source_definition_pointer": "/machines/0/root", "target_definition_pointer": "/machines/0/root"},
      {"operation": "map", "source_definition_pointer": "/machines/0/root/states/pending", "target_definition_pointer": "/machines/0/root/states/pending"},
      {"operation": "map", "source_definition_pointer": "/machines/0/root/states/awaiting_fulfillment", "target_definition_pointer": "/machines/0/root/states/awaiting_shipping"}
    ]
  },
  "terminal_policy": {"completed": "preserve", "faulted": "preserve"},
  "resource_requirements": {
    "maximum_transformed_output_bytes": "64",
    "maximum_cel_expression_length": "0",
    "maximum_cel_ast_nodes": "0",
    "maximum_cel_evaluation_steps": "0"
  },
  "migration_descriptor_digest": "sha256:0ea15292bbed1768fe16600da9d2bb771568aff65ae20118d4f6b8485163671d"
}
```

Save it as `migration-missing-state.json`.

The deliberate repair maps the old leaf to the new leaf. All other mappings remain
the same; this is not a reset and it does not run entry or exit actions.

<!-- determa-example: persistence-tutorial/migration-good.json -->
```json
{
  "migration_descriptor_format": "determa.aggregate_migration",
  "migration_descriptor_schema_version": 1,
  "source_machine_format": 1,
  "target_machine_format": 1,
  "source_validated_bundle_fingerprint": "sha256:e8ebf83dc88ba698f6e550945958a8059d5a15cd70d7d5c5e4864e3ab8c538e0",
  "target_validated_bundle_fingerprint": "sha256:e046130705827409a6263442a7f0c81c4153fee00f7d217600b3f6587334bf8a",
  "source_aggregate_shape_fingerprint": "sha256:b6d2096a63d6feee54a708d3144f01ddbc568c20500f1547a1de771519144143",
  "target_aggregate_shape_fingerprint": "sha256:0e97046b585ae04ffc523b94785ce7180e6bb92ca03a901fd3f998294f4b64fd",
  "mode": "transform",
  "mappings": {
    "machines": [{"source_definition_pointer": "/machines/0/root", "target_definition_pointer": "/machines/0/root"}],
    "active_states": [{
      "source_leaf_state_definition_pointer": "/machines/0/root/states/awaiting_fulfillment",
      "target_leaf_state_definition_pointers": ["/machines/0/root/states/awaiting_shipping"]
    }],
    "variables": [{"operation": "copy", "source_declaration_pointer": "/machines/0/root/variables/order_id", "target_declaration_pointer": "/machines/0/root/variables/order_id"}],
    "history": [],
    "components": [],
    "owned_runtimes": [],
    "lifetime_holders": [],
    "counters": [
      {"operation": "map", "source_definition_pointer": "/machines/0/root", "target_definition_pointer": "/machines/0/root"},
      {"operation": "map", "source_definition_pointer": "/machines/0/root/states/pending", "target_definition_pointer": "/machines/0/root/states/pending"},
      {"operation": "map", "source_definition_pointer": "/machines/0/root/states/awaiting_fulfillment", "target_definition_pointer": "/machines/0/root/states/awaiting_shipping"}
    ]
  },
  "terminal_policy": {"completed": "preserve", "faulted": "preserve"},
  "resource_requirements": {
    "maximum_transformed_output_bytes": "64",
    "maximum_cel_expression_length": "0",
    "maximum_cel_ast_nodes": "0",
    "maximum_cel_evaluation_steps": "0"
  },
  "migration_descriptor_digest": "sha256:03f66443a799a4be413c50b00571f65a24d975f23add2a767922731c3fb4fc86"
}
```

Save it as `migration-good.json`.

## 5. Build the SQLite host

The host stores definitions and descriptors once under their content digests. An
aggregate row stores only canonical aggregate bytes. One SQLite transaction owns the
inbox decision, aggregate replacement, ordered outbox inserts, and migration audit.
This implements the
[lazy transactional host order in specification §16.11](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#1611-lazy-transactional-host-ordering).

<!-- determa-example: persistence-tutorial/app.py -->
```python
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

import determa.state as ds

HERE = Path(__file__).resolve().parent
TARGET = "sha256:e046130705827409a6263442a7f0c81c4153fee00f7d217600b3f6587334bf8a"
GOOD = "sha256:03f66443a799a4be413c50b00571f65a24d975f23add2a767922731c3fb4fc86"
BROKEN = "sha256:0ea15292bbed1768fe16600da9d2bb771568aff65ae20118d4f6b8485163671d"


class SQLiteResolver:
    def __init__(self, db):
        self.db = db

    def resolve_definition(self, fingerprint):
        row = self.db.execute(
            "SELECT document FROM definitions WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        return None if row is None else row[0]

    def definition_is_trusted(self, fingerprint):
        row = self.db.execute(
            "SELECT trusted FROM definitions WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        return row is not None and row[0] == 1

    def resolve_migration_descriptor(self, digest):
        row = self.db.execute(
            "SELECT document FROM descriptors WHERE digest=?", (digest,)
        ).fetchone()
        return None if row is None else row[0]

    def migration_descriptor_is_trusted(self, digest):
        row = self.db.execute(
            "SELECT trusted FROM descriptors WHERE digest=?", (digest,)
        ).fetchone()
        return row is not None and row[0] == 1


def open_database(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS definitions(
          fingerprint TEXT PRIMARY KEY, machine_version INTEGER NOT NULL,
          document TEXT NOT NULL, trusted INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS descriptors(
          digest TEXT PRIMARY KEY, document TEXT NOT NULL, trusted INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS aggregates(
          root_instance_id TEXT PRIMARY KEY, aggregate_bytes BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS inbox(
          event_id TEXT PRIMARY KEY, root_instance_id TEXT NOT NULL,
          status TEXT NOT NULL, disposition TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox(
          effect_id TEXT PRIMARY KEY, root_instance_id TEXT NOT NULL,
          sequence INTEGER NOT NULL, intent_json TEXT NOT NULL,
          UNIQUE(root_instance_id, sequence));
        CREATE TABLE IF NOT EXISTS migration_audit(
          root_instance_id TEXT NOT NULL, migration_sequence INTEGER NOT NULL,
          record_json TEXT NOT NULL,
          PRIMARY KEY(root_instance_id, migration_sequence));
        CREATE TABLE IF NOT EXISTS blocked_inbox(
          event_id TEXT PRIMARY KEY, root_instance_id TEXT NOT NULL,
          failure_code TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS quarantine(
          root_instance_id TEXT PRIMARY KEY, aggregate_state_digest TEXT NOT NULL,
          failure_code TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS migration_failure_audit(
          event_id TEXT PRIMARY KEY, root_instance_id TEXT NOT NULL,
          aggregate_state_digest TEXT NOT NULL, failure_code TEXT NOT NULL,
          route_json TEXT NOT NULL);
        """
    )
    return db


def register_artifacts(db):
    for name in ("order-v1.yaml", "order-v2.yaml"):
        source = (HERE / name).read_text()
        bundle = ds.load_bundle(source)
        version = bundle.raw["machines"][0]["version"]
        row = db.execute(
            "SELECT document FROM definitions WHERE fingerprint=?",
            (bundle.fingerprint,),
        ).fetchone()
        if row is None:
            db.execute(
                "INSERT INTO definitions VALUES(?,?,?,1)",
                (bundle.fingerprint, version, source),
            )
        elif ds.load_bundle(row[0]).fingerprint != bundle.fingerprint:
            raise RuntimeError("definition fingerprint collision")
    for name in ("migration-good.json", "migration-missing-state.json"):
        source = (HERE / name).read_text()
        document = json.loads(source)
        digest = document["migration_descriptor_digest"]
        verifier = ds.MemoryArtifactResolver()
        verifier.put_migration_descriptor(digest, document)
        row = db.execute(
            "SELECT document FROM descriptors WHERE digest=?", (digest,)
        ).fetchone()
        if row is None:
            db.execute("INSERT INTO descriptors VALUES(?,?,1)", (digest, source))
        elif json.loads(row[0]) != document:
            raise RuntimeError("migration descriptor digest collision")
    db.commit()


def artifact_cache(db):
    definitions = {
        fingerprint: document
        for fingerprint, document, trusted in db.execute(
            "SELECT fingerprint,document,trusted FROM definitions"
        )
        if trusted
    }
    descriptors = {
        digest: document
        for digest, document, trusted in db.execute(
            "SELECT digest,document,trusted FROM descriptors"
        )
        if trusted
    }
    return ds.MemoryArtifactResolver(
        definitions=definitions,
        migration_descriptors=descriptors,
        trusted_definitions=list(definitions),
        trusted_migration_descriptors=list(descriptors),
    )


def delivery(state, event, event_id, payload=None):
    return {"input": {
        "event": event,
        "event_id": event_id,
        "target": {"root": {
            "root_instance_id": state["root_instance_id"],
            "root_runtime_id": state["root_runtime_id"],
        }},
        "payload": payload or {},
    }}


def create_order(db):
    source = db.execute(
        "SELECT document FROM definitions WHERE machine_version=1"
    ).fetchone()[0]
    bundle = ds.load_bundle(source)
    result = ds.create(bundle, "order", "order-100", "create:order-100", {})
    encoded = ds.serialize_aggregate(bundle, result["state"])
    db.execute("INSERT INTO aggregates VALUES(?,?)", ("order-100", encoded))
    db.commit()
    assert ds.restore_aggregate(encoded, SQLiteResolver(db)).canonical_bytes == encoded


def dispatch_once(db, event, event_id, payload=None):
    cache = artifact_cache(db)
    db.execute("BEGIN IMMEDIATE")
    try:
        previous = db.execute(
            "SELECT status,disposition FROM inbox WHERE event_id=?", (event_id,)
        ).fetchone()
        if previous:
            db.rollback()
            return f"duplicate:{previous[0]}:{previous[1]}"
        encoded = db.execute(
            "SELECT aggregate_bytes FROM aggregates WHERE root_instance_id='order-100'"
        ).fetchone()[0]
        restored = ds.restore_aggregate(encoded, cache)
        result = ds.dispatch(
            restored.bundle, restored.state,
            delivery(restored.state, event, event_id, payload),
        )
        next_bytes = ds.serialize_aggregate(restored.bundle, result["state"])
        db.execute(
            "UPDATE aggregates SET aggregate_bytes=? WHERE root_instance_id='order-100'",
            (next_bytes,),
        )
        db.execute(
            "INSERT INTO inbox VALUES(?,?,?,?)",
            (event_id, "order-100", result["status"], result["disposition"]),
        )
        for intent in result["emissions"]:
            if intent["target"] == "external":
                db.execute(
                    "INSERT INTO outbox VALUES(?,?,?,?)",
                    (intent["effect_id"], "order-100", intent["sequence"],
                     json.dumps(intent, sort_keys=True)),
                )
        db.commit()
        return result["disposition"]
    except Exception:
        db.rollback()
        raise


def quarantine_broken_migration(db):
    event_id = "input-complete-1"
    cache = artifact_cache(db)
    db.execute("BEGIN IMMEDIATE")
    try:
        previous = db.execute(
            "SELECT status,disposition FROM inbox WHERE event_id=?", (event_id,)
        ).fetchone()
        if previous:
            db.rollback()
            return f"duplicate:{previous[0]}:{previous[1]}"
        blocked = db.execute(
            "SELECT failure_code FROM blocked_inbox WHERE event_id=?", (event_id,)
        ).fetchone()
        if blocked:
            db.rollback()
            return "blocked:" + blocked[0]
        encoded = db.execute(
            "SELECT aggregate_bytes FROM aggregates WHERE root_instance_id='order-100'"
        ).fetchone()[0]
        aggregate_digest = json.loads(encoded)["aggregate_state_digest"]
        result = ds.migrate_aggregate(
            encoded, TARGET, [BROKEN], cache, maintenance_mode=False
        )
        assert result.failure is not None
        assert db.execute(
            "SELECT aggregate_bytes FROM aggregates WHERE root_instance_id='order-100'"
        ).fetchone()[0] == encoded
        code = result.failure.code
        db.execute(
            "INSERT INTO blocked_inbox VALUES(?,?,?)",
            (event_id, "order-100", code),
        )
        db.execute(
            "INSERT INTO quarantine VALUES(?,?,?)",
            ("order-100", aggregate_digest, code),
        )
        db.execute(
            "INSERT INTO migration_failure_audit VALUES(?,?,?,?,?)",
            (event_id, "order-100", aggregate_digest, code, json.dumps([BROKEN])),
        )
        db.commit()
        return code
    except Exception:
        db.rollback()
        raise


def migrate_and_complete(db):
    cache = artifact_cache(db)
    db.execute("BEGIN IMMEDIATE")
    try:
        previous = db.execute(
            "SELECT status,disposition FROM inbox WHERE event_id=?",
            ("input-complete-1",),
        ).fetchone()
        if previous:
            db.rollback()
            return f"duplicate:{previous[0]}:{previous[1]}"
        blocked = db.execute(
            "SELECT failure_code FROM blocked_inbox WHERE event_id=?",
            ("input-complete-1",),
        ).fetchone()
        encoded = db.execute("SELECT aggregate_bytes FROM aggregates").fetchone()[0]
        restored = ds.restore_aggregate(encoded, cache)
        result = ds.migrate_and_dispatch(
            encoded, TARGET, [GOOD], cache,
            delivery(restored.state, "complete", "input-complete-1"),
            maintenance_mode=False,
        )
        assert result.failure is None
        db.execute("UPDATE aggregates SET aggregate_bytes=?", (result.aggregate_bytes,))
        db.execute(
            "INSERT INTO inbox VALUES(?,?,?,?)",
            ("input-complete-1", "order-100", result.status, result.disposition),
        )
        for audit in result.audit_records:
            db.execute(
                "INSERT INTO migration_audit VALUES(?,?,?)",
                ("order-100", int(audit["migration_sequence"]),
                 json.dumps(audit, sort_keys=True)),
            )
        if blocked:
            db.execute(
                "DELETE FROM blocked_inbox WHERE event_id=?", ("input-complete-1",)
            )
            db.execute(
                "DELETE FROM quarantine WHERE root_instance_id='order-100'"
            )
        db.commit()
        return f"{result.status}:{result.disposition}"
    except Exception:
        db.rollback()
        raise


def inspect(db):
    encoded = db.execute("SELECT aggregate_bytes FROM aggregates").fetchone()[0]
    document = json.loads(encoded)
    restored = ds.restore_aggregate(encoded, SQLiteResolver(db))
    root = restored.state["runtimes"][restored.state["root_runtime_id"]]
    return {
        "active": root["active"],
        "aggregate_state_digest": document["aggregate_state_digest"],
        "definition_fingerprint": document["validated_bundle_fingerprint"],
        "machine_version": document["root_machine_version"],
        "migration_sequence": document["migration_sequence"],
        "inbox": db.execute("SELECT COUNT(*) FROM inbox").fetchone()[0],
        "outbox": db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0],
        "audits": db.execute("SELECT COUNT(*) FROM migration_audit").fetchone()[0],
        "blocked": db.execute("SELECT COUNT(*) FROM blocked_inbox").fetchone()[0],
        "quarantined": db.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0],
        "failure_audits": db.execute(
            "SELECT COUNT(*) FROM migration_failure_audit"
        ).fetchone()[0],
    }


def scenario(db):
    create_order(db)
    assert dispatch_once(
        db, "submit", "input-submit-1", {"order_id": "order-100"}
    ) == "handled"
    before = inspect(db)
    assert dispatch_once(
        db, "submit", "input-submit-1", {"order_id": "order-100"}
    ) == "duplicate:running:handled"
    assert inspect(db) == before
    assert quarantine_broken_migration(db) == "migration_totality_failure"
    quarantined = inspect(db)
    assert quarantined["aggregate_state_digest"] == before["aggregate_state_digest"]
    assert quarantined["blocked"] == 1
    assert quarantined["quarantined"] == 1
    assert quarantined["failure_audits"] == 1
    assert quarantine_broken_migration(db) == "blocked:migration_totality_failure"
    assert inspect(db) == quarantined
    assert migrate_and_complete(db) == "completed:handled"
    final = inspect(db)
    assert final["machine_version"] == "2"
    assert final["migration_sequence"] == "1"
    assert final["inbox"] == 2 and final["outbox"] == 1 and final["audits"] == 1
    assert final["blocked"] == 0 and final["quarantined"] == 0
    assert final["failure_audits"] == 1
    assert quarantine_broken_migration(db) == "duplicate:completed:handled"
    assert inspect(db) == final
    assert migrate_and_complete(db) == "duplicate:completed:handled"
    assert inspect(db) == final
    print(
        "restored=v1; duplicate=ignored; outbox=1; "
        "quarantined=migration_totality_failure; released=trusted-route; "
        "migrated=v2; status=completed"
    )


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: python app.py DATABASE COMMAND")
    path, command = Path(sys.argv[1]), sys.argv[2]
    if command in {"reset", "scenario"} and path.exists():
        path.unlink()
    db = open_database(path)
    register_artifacts(db)
    actions = {
        "reset": lambda: "database=ready",
        "create": lambda: (create_order(db), "created=v1")[1],
        "submit": lambda: "submit=" + dispatch_once(
            db, "submit", "input-submit-1", {"order_id": "order-100"}
        ),
        "duplicate": lambda: "duplicate=" + dispatch_once(
            db, "submit", "input-submit-1", {"order_id": "order-100"}
        ),
        "check-broken": lambda: "migration=" + quarantine_broken_migration(db),
        "complete": lambda: "status=" + migrate_and_complete(db),
        "inspect": lambda: json.dumps(inspect(db), indent=2, sort_keys=True),
        "scenario": lambda: scenario(db),
    }
    if command not in actions:
        raise SystemExit("unknown command")
    output = actions[command]()
    if output is not None:
        print(output)
    db.close()


if __name__ == "__main__":
    main()
```

Save it as `app.py`.

The resolver returns only trusted artifacts under the requested digest. The engine
revalidates and rehashes them. Content addressing proves integrity; deciding which
digests are trusted remains deployment policy. `artifact_cache` performs that registry
work before `BEGIN IMMEDIATE`; the transaction then uses only the immutable cache and
the locked aggregate row.

## 6. Run one step per process

Each command opens the database again, so the aggregate is restored rather than kept
in Python memory:

```sh
python app.py tutorial.db reset
python app.py tutorial.db create
python app.py tutorial.db submit
python app.py tutorial.db duplicate
python app.py tutorial.db inspect
python app.py tutorial.db check-broken
python app.py tutorial.db complete
python app.py tutorial.db inspect
python app.py tutorial.db check-broken
python app.py tutorial.db inspect
python app.py tutorial.db complete
python app.py tutorial.db inspect
```

Before migration, inspection reports machine version `1`, migration sequence `0`,
active state `awaiting_fulfillment`, one inbox record, and one outbox intent. The
duplicate does not call the engine or add rows.

`check-broken` presents `input-complete-1` with the incomplete route. The pure engine
result is only `migration_totality_failure` and returns no candidate or audit. In the
same SQLite transaction, the host proves the aggregate bytes are unchanged, records
the inbox item as blocked, adds separate quarantine metadata, and appends a failure
audit. Repeating `check-broken` reads that blocked row and does not call the engine.

These records are deliberately separate:

- quarantine is host metadata, not an aggregate lifecycle status;
- blocked inbox means the input is neither acknowledged nor successfully committed;
- failure audit records the permanent route failure, not a successful engine migration
  audit or engine fault.

The first `complete` command represents installing the corrected trusted route. It
migrates and dispatches in one transaction, moves the blocked item into the committed
inbox, clears quarantine, and retains the failure audit for operators. Final inspection
reports version `2`, migration sequence `1`, two committed inbox records, one outbox
row, one successful migration audit, one retained failure audit, and no blocked or
quarantined row. The following `check-broken` command reads the committed inbox outcome
before considering quarantine and returns
`migration=duplicate:completed:handled`; the next inspection proves aggregate, inbox,
outbox, audits, and quarantine remain unchanged. The second `complete` command returns
`status=duplicate:completed:handled` from the locked committed inbox row. It never
reads or migrates the aggregate.

SQLite makes this local transaction atomic. It does **not** make delivery to a payment
provider, broker, or other process exactly once. Dispatch the outbox after commit,
retry it by `effect_id`, and acknowledge broker input only after the transaction
commits.

## 7. Check the portable path with Rust

The database host is narrated once in Python so the transaction boundary stays clear.
This complete Rust trace uses the released Rust API with the same two definitions and
descriptors. It independently restores the canonical artifact, observes the same pure
failure, applies the same remap, and reaches the same result. Host quarantine remains a
database concern rather than a Rust engine result.

<!-- determa-example: persistence-tutorial/rust/Cargo.toml -->
```toml
[package]
name = "determa-persistence-migration-tutorial"
version = "0.2.0"
edition = "2021"
publish = false

[dependencies]
determa-state = "=0.2.0"
serde_json = "1"
```

<!-- determa-example: persistence-tutorial/rust/src/main.rs -->
```rust
use determa_state::{
    create, dispatch, encode_aggregate, load_bundle, migrate_aggregate, migrate_and_dispatch,
    restore_aggregate, Bindings, Delivery, Envelope, InMemoryDefinitionResolver, MigrationRequest,
    ResourceLimits, RuntimeStatus, Target, Value,
};
use serde_json::Value as JsonValue;
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::PathBuf,
};

fn delivery(
    state: &determa_state::AggregateState,
    event: &str,
    event_id: &str,
    payload: BTreeMap<String, Value>,
) -> Delivery {
    Delivery::Input(Envelope {
        event: event.to_string(),
        event_id: event_id.to_string(),
        target: Target::Root {
            root_instance_id: state.root_instance_id.clone(),
            root_runtime_id: state.root.runtime_id.clone(),
        },
        payload,
        correlation_id: None,
    })
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let root = PathBuf::from(env::args().nth(1).expect("project path"));
    let source = load_bundle(&fs::read_to_string(root.join("order-v1.yaml"))?)?;
    let target = load_bundle(&fs::read_to_string(root.join("order-v2.yaml"))?)?;
    let good_bytes = fs::read(root.join("migration-good.json"))?;
    let bad_bytes = fs::read(root.join("migration-missing-state.json"))?;
    let good: JsonValue = serde_json::from_slice(&good_bytes)?;
    let bad: JsonValue = serde_json::from_slice(&bad_bytes)?;
    let good_digest = good["migration_descriptor_digest"]
        .as_str()
        .unwrap()
        .to_string();
    let bad_digest = bad["migration_descriptor_digest"]
        .as_str()
        .unwrap()
        .to_string();

    let mut resolver = InMemoryDefinitionResolver::default();
    resolver.insert(source.clone(), true);
    resolver.insert(target.clone(), true);
    resolver.insert_descriptor(good_digest.clone(), good_bytes, true);
    resolver.insert_descriptor(bad_digest.clone(), bad_bytes, true);

    let initial = create(
        &source,
        "order",
        "order-100",
        "create:order-100",
        &Bindings::default(),
    )
    .state
    .unwrap();
    let submitted = dispatch(
        &source,
        &initial,
        Some(delivery(
            &initial,
            "submit",
            "input-submit-1",
            BTreeMap::from([(
                "order_id".to_string(),
                Value::String("order-100".to_string()),
            )]),
        )),
    );
    assert_eq!(submitted.emissions.len(), 1);
    let submitted_state = submitted.state.unwrap();
    let (_, encoded) = encode_aggregate(&source, &submitted_state)?;
    let restored = restore_aggregate(&encoded, &resolver)?;
    assert_eq!(
        restored.root.active,
        BTreeSet::from(["root".to_string(), "awaiting_fulfillment".to_string(),])
    );

    let broken = migrate_aggregate(
        &encoded,
        &MigrationRequest {
            migration_route: vec![bad_digest.clone()],
            target_validated_bundle_fingerprint: target.fingerprint.clone(),
            maintenance_mode: false,
        },
        &resolver,
        &ResourceLimits::default(),
    )
    .expect_err("missing active-state mapping");
    assert_eq!(broken.code.as_str(), "migration_totality_failure");
    let broken_retry = migrate_aggregate(
        &encoded,
        &MigrationRequest {
            migration_route: vec![bad_digest],
            target_validated_bundle_fingerprint: target.fingerprint.clone(),
            maintenance_mode: false,
        },
        &resolver,
        &ResourceLimits::default(),
    )
    .expect_err("the same incomplete route fails again");
    assert_eq!(broken_retry, broken);

    let preview = migrate_aggregate(
        &encoded,
        &MigrationRequest {
            migration_route: vec![good_digest.clone()],
            target_validated_bundle_fingerprint: target.fingerprint.clone(),
            maintenance_mode: false,
        },
        &resolver,
        &ResourceLimits::default(),
    )?;
    assert_eq!(preview.aggregate.root.runtime_id, restored.root.runtime_id);
    assert_eq!(
        preview.aggregate.next_logical_step_sequence,
        restored.next_logical_step_sequence
    );
    assert_eq!(
        preview.aggregate.next_output_sequence,
        restored.next_output_sequence
    );

    let completed = migrate_and_dispatch(
        &encoded,
        &MigrationRequest {
            migration_route: vec![good_digest],
            target_validated_bundle_fingerprint: target.fingerprint.clone(),
            maintenance_mode: false,
        },
        &resolver,
        &ResourceLimits::default(),
        Some(delivery(
            &restored,
            "complete",
            "input-complete-1",
            BTreeMap::new(),
        )),
    )?;
    assert_eq!(
        completed.migration.aggregate_envelope.root_machine_version,
        "2"
    );
    assert_eq!(
        completed.migration.aggregate_envelope.migration_sequence,
        "1"
    );
    assert_eq!(completed.migration.audit_records.len(), 1);
    assert_eq!(
        completed.migration.aggregate.root.status,
        RuntimeStatus::Completed
    );

    println!(
        "restored=v1; duplicate=ignored; outbox=1; \
         pure_failure=migration_totality_failure; migrated=v2; status=completed"
    );
    Ok(())
}
```

Run it:

```sh
cargo run --quiet --manifest-path rust/Cargo.toml -- .
```

The Python host prints:

```text
restored=v1; duplicate=ignored; outbox=1; quarantined=migration_totality_failure; released=trusted-route; migrated=v2; status=completed
```

The Rust engine trace prints:

```text
restored=v1; duplicate=ignored; outbox=1; pure_failure=migration_totality_failure; migrated=v2; status=completed
```

## 8. Inspect and recover safely

When a dormant row fails to load or migrate:

1. Preserve the exact aggregate bytes and failed descriptor route.
2. Read `aggregate_state_digest`, `validated_bundle_fingerprint`,
   `root_machine_version`, and `migration_sequence` from the JSON envelope.
3. Resolve that exact definition fingerprint from the registry and verify its digest.
4. Inspect active leaf pointers and the deterministic failure code.
5. Publish and authorize an explicit descriptor that accounts for every retained
   occurrence, then retry from the unchanged bytes.

Do not silently bind the row to the newest YAML, reset it to the target initial state,
or rewrite every database row during deployment. Lazy migration keeps dormant rows
cheap while the central registry retains the old declarative definitions needed to
interpret them. Definition garbage collection must therefore be reference-aware.

This focused example covers round-trip encoding, definition resolution, unchanged
restoration, explicit active-state remapping, deleted-state totality, counter and
identity preservation, rollback, migration plus dispatch, and the host transaction
order demonstrated by conformance cases
[94](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/94-aggregate-wire-round-trip),
[96](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/96-definition-resolution),
[98](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/98-unchanged-definition-resume),
[100](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/100-explicit-active-state-remap),
[101](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/101-deleted-active-state-totality),
[106](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/106-counter-and-identity-preservation),
[108](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/108-migration-retry-and-rollback), and
[109](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/109-migration-then-dispatch).

Continue with the
[persistence and migration reference lab](persistence-migration-reference.md) for
package attachments, variable/history/component/owned-runtime transforms, chained
routes, terminal maintenance migration, resource limits, occurrence-local transform
binding, and large decimal identity projections.
