# Persistence and migration reference lab

The [SQLite tutorial](persistence-and-migration.md) shows a complete application
transaction. This lab explains the immutable fixtures behind the unreleased 0.3.0
candidate. Machine `format: 1` and all aggregate, package and migration schema versions
remain 1. A machine's own version may change independently.

Use a checkout of this manual and its `sources.lock.yaml`. Run `make sources` to fetch
only the pinned public repositories, install the candidate with
`python scripts/install_candidate.py`, then run `make check`. That command executes
both engines against the v1 vectors and durable-host vectors; it does not publish a
package or deploy the manual.

## Read the fixture groups

The pinned core contains 154 version-1 operation vectors across these eight groups.
Eight additional checkpoint vectors bring the complete v1 inventory to 162.
The operation harness compares complete results with the expected fixtures, including
stable refusal codes. These groups replace the previous persistence-vector inventory.

| Case | What it protects |
| --- | --- |
| 117 mailboxes | Admission, FIFO processing, deferral, release and lifecycle cleanup. |
| 118 persistence | Compatible queued work, explicit disposal, ordered route audits and incompatible targets. |
| 119 aggregate integrity | Closed decoding, digests, identities, counters and canonical round trips. |
| 120 definition packages | Trusted attachments, resolver insertion and package restore. |
| 121 migration totality | Every live state, variable, history, component, owned runtime and counter mapping. |
| 122 migration execution | Migration followed by queue processing, fault rollback and terminal preservation. |
| 123 migration guards | Exact routes, trusted descriptors, resource limits and selected-decoder failures. |
| 124 occurrence identity | Repeated runtime and activation occurrences remain separate. |

A package transports portable definitions and descriptors. It is neither a machine
language import nor permission to trust an arbitrary attachment. A migration descriptor
names exact source and target fingerprints and includes `queued_event_default` and
explicit `queued_event_rules`. It cannot infer a mapping from a renamed state.

## Inspect the portable evidence

The following script reads the already fetched public conformance checkout. It checks
that the current inventory has all eight groups, both success and refusal results,
closed version-1 aggregate artifacts and explicit queue migration policies. Engine
execution remains the separate `make check` gate; inspecting fixtures alone does not
prove an adapter's operational guarantees.

<!-- determa-example: persistence-reference/inspect_vectors.py -->
```python
from pathlib import Path
import json
import sys

from ruamel.yaml import YAML

root = Path(sys.argv[1]) / "conformance" / "core"
yaml = YAML(typ="safe")
yaml.version = (1, 2)
yaml.allow_duplicate_keys = False
counts = {117: 38, 118: 11, 119: 27, 120: 12,
          121: 12, 122: 18, 123: 24, 124: 12}
operations = set()
results = set()
for number, count in counts.items():
    directories = list(root.glob(f"{number}-*"))
    assert len(directories) == 1
    directory = directories[0]
    manifest = yaml.load((directory / "test.yaml").read_text())
    vectors = manifest["version1_vectors"]
    assert len(vectors) == count
    for vector in vectors:
        operations.add(vector["operation"])
        results.add(vector["expect"]["result"])
    for item in manifest.get("artifacts", {}).get("documents", []):
        if not item["valid"]:
            continue
        document = json.loads((directory / item["file"]).read_text())
        if item["kind"] == "migration_descriptor_v1":
            assert document["migration_descriptor_schema_version"] == 1
            assert document["queued_event_default"] == "preserve_if_compatible"
            assert isinstance(document["queued_event_rules"], list)
        if item["kind"] == "aggregate_state_v1":
            assert document["aggregate_state_schema_version"] == 1
            for runtime in document["runtimes"]:
                assert isinstance(runtime["ready_mailbox"], list)
                assert isinstance(runtime["deferred_mailbox"], list)
assert sum(counts.values()) == 154
assert {"success", "failure"} <= results
assert {"create_v1", "admit_v1", "step_v1", "migrate_aggregate_v1",
        "restore_package_v1", "round_trip_aggregate_v1"} <= operations
print("154 core v1 vectors; queues=portable; migration=explicit; packages=trusted transport")
```

After extracting the named examples, run:

```sh
python persistence-reference/inspect_vectors.py .sources/determa-state-conformance
```

Expected output:

```text
154 core v1 vectors; queues=portable; migration=explicit; packages=trusted transport
```

Pure failures leave the caller's committed aggregate unchanged. A host must separately
own retry, quarantine, acknowledgement and outbox transactions. The manual also runs
all 142 durable-host vectors against both engines. Those conditional adapter policies
are distinct from production-provider verification: a mock or a passing artifact
schema cannot establish native transactional delivery or worker authority.

## Normative coverage

This lab explains [§16 portable persistence and definition migration](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#16-portable-persistence-and-definition-migration)
and the pinned [core fixture inventory](https://github.com/fruwehq/determa-state-conformance/tree/7f09321fb483a22eb677a4342f8d9537a7a18e82/conformance/core).
Use [the checkpoint guide](execution-checkpoint-hosting.md) for durable admission,
restart and replay, and [the migration tutorial](persistence-and-migration.md) for the
application-owned SQLite transaction and quarantine release.
