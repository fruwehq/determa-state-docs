# Persistence and migration reference lab

The [SQLite tutorial](persistence-and-migration.md) is the shortest path from an empty
directory to a durable application. This lab is the next step. It executes every
portable persistence and migration vector released with Determa State 0.2.0 and then
inspects the fixtures so you can see which property each group protects.

The normative contract is
[specification section 16](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#16-portable-persistence-and-definition-migration).
This chapter explains that contract; it does not add new behavior.

## 1. Check prerequisites

You need:

- Python 3.11 or newer;
- Git and network access to clone the four immutable release sources; and
- a Rust toolchain compatible with Determa State 0.2.0. The released repositories
  validate with Rust 1.95.

Check them before creating files:

```sh
python3 --version
git --version
rustc --version
cargo --version
```

## 2. Create the lab

Start in an empty directory:

```sh
mkdir determa-persistence-reference
cd determa-persistence-reference
python3 -m venv .venv
. .venv/bin/activate
python -m pip install \
  determa-state==0.2.0 pytest==8.4.2 ruamel.yaml==0.19.1
```

Create the following script. It downloads the immutable released sources, checks their
exact commits, runs the Python package's persistence vectors against the installed
0.2.0 package, runs the Rust 0.2.0 crate's matching vectors, and finally runs the
property inspector created in the next section.

<!-- determa-example: persistence-reference/run.sh -->
```sh
#!/bin/sh
set -eu

clone_at() {
  repository=$1
  directory=$2
  commit=$3
  if [ ! -d "$directory/.git" ]; then
    git clone "https://github.com/fruwehq/$repository.git" "$directory"
  fi
  git -C "$directory" fetch --depth 1 origin "$commit"
  git -C "$directory" checkout --detach "$commit"
  test "$(git -C "$directory" rev-parse HEAD)" = "$commit"
}

clone_at determa-state-spec spec \
  c1635d74e6a216301a8986d37be8ce7e7111dfd7
clone_at determa-state-conformance conformance \
  600523ca08c3b8a6ee790439a32dc4ce47f71b95
clone_at determa-state-python python \
  7b17d788b48049648e7e463aa3d35ba13dc1aa6e
clone_at determa-state-rust rust \
  d17480c8b281dcd17953f59afcf6b5d23ff44efd

DETERMA_SPEC_DIR="$PWD/spec" \
DETERMA_CONFORMANCE_DIR="$PWD/conformance" \
  .venv/bin/python -m pytest \
  python/conformance/test_conformance.py::test_persistence_vectors -q

git -C rust submodule update --init
cargo test --quiet --manifest-path rust/Cargo.toml \
  --test persistence_conformance

.venv/bin/python inspect_vectors.py conformance
```

Save it as `run.sh`, make it executable, and run it after creating
`inspect_vectors.py`:

```sh
chmod +x run.sh
./run.sh
```

The two engine harnesses compare exact success bytes, aggregate values, audit arrays,
resolver contents, emissions, dispositions, stable failure codes, and caller ownership
for 108 vectors in cases 94 through 115. This is deliberately stronger than a smoke
test.

## 3. Inspect what the vectors prove

The conformance harness is the arbiter, but a passing test count does not teach you what
changed. Save this inspector as `inspect_vectors.py`. It checks the pedagogically
important facts in the same immutable fixtures.

<!-- determa-example: persistence-reference/inspect_vectors.py -->
```python
from __future__ import annotations

import json
from pathlib import Path
import sys

from ruamel.yaml import YAML


ROOT = Path(sys.argv[1]) / "conformance" / "core"
YAML_1_2 = YAML(typ="safe")
YAML_1_2.version = (1, 2)
YAML_1_2.allow_duplicate_keys = False


def case(number: int) -> Path:
    matches = list(ROOT.glob(f"{number}-*"))
    assert len(matches) == 1
    return matches[0]


def document(path: Path):
    return json.loads(path.read_text())


def test(number: int):
    return YAML_1_2.load((case(number) / "test.yaml").read_text())


def vectors(number: int):
    return test(number)["persistence_vectors"]


def vector(number: int, name: str):
    return next(item for item in vectors(number) if item["name"] == name)


def variable_values(path: Path, suffix: str):
    aggregate = document(path)
    return sorted(
        (
            runtime["runtime_id"],
            value["declaring_state_activation_sequence"],
            value["value"],
        )
        for runtime in aggregate["runtimes"]
        for value in runtime["variables"]
        if value["variable_declaration_pointer"].endswith(suffix)
    )


directories = [case(number) for number in range(94, 116)]
assert len(directories) == 22
assert sum(len(vectors(number)) for number in range(94, 116)) == 108

# Aggregate operations leave the source artifact caller-owned on every pure failure.
# Descriptor-only decoding has no aggregate argument to return.
for number in range(94, 116):
    for item in vectors(number):
        expected = item["expect"]
        if expected["result"] == "failure":
            if item["operation"] == "decode_selected_migration_descriptor":
                assert set(expected) == {"result", "code"}
                continue
            assert set(expected) == {
                "result",
                "code",
                "caller_still_owns_aggregate",
            }
            assert expected["caller_still_owns_aggregate"] is True

wire_codes = {
    item["expect"]["code"]
    for item in vectors(95)
}
assert wire_codes == {
    "invalid_aggregate_state",
    "unsupported_aggregate_state_format",
    "unsupported_aggregate_state_schema_version",
}
wire_documents = {
    item["file"]: item["error"]
    for item in test(95)["artifacts"]["documents"]
    if item["valid"] is False
}
assert wire_documents == {
    "duplicate-key.json": "duplicate_key",
    "invalid-unicode.json": "invalid_unicode",
    "malformed-decimal.json": "invalid_aggregate_state",
    "malformed-float.json": "invalid_aggregate_state",
    "unknown-field.json": "invalid_aggregate_state",
    "unsupported-format.json": "unsupported_aggregate_state_format",
    "legacy-0.0.6-snapshot.json": "unsupported_aggregate_state_format",
    "unsupported-schema-version.json": (
        "unsupported_aggregate_state_schema_version"
    ),
}

# A package is transport: it seeds an empty resolver, is idempotent, and never
# overwrites a conflicting digest key. It is not a machine-language import.
package_names = {item["name"] for item in vectors(97)}
assert {
    "valid_self_contained_package",
    "attachments_seed_empty_resolver_and_drive_route",
    "put_if_absent_is_idempotent",
    "attachment_never_overrides_existing_key",
} <= package_names
package = document(case(97) / "valid-package.json")
attached_definitions = {
    item["validated_bundle_fingerprint"]
    for item in package["normalized_definitions"]
}
assert package["aggregate_state"]["validated_bundle_fingerprint"] in attached_definitions
assert set(package["migration_route"]) == {
    item["migration_descriptor_digest"]
    for item in package["migration_descriptors"]
}
for descriptor in package["migration_descriptors"]:
    assert descriptor["source_validated_bundle_fingerprint"] in attached_definitions
    assert descriptor["target_validated_bundle_fingerprint"] in attached_definitions

# Compatible migration changes only the current definition binding and digest.
compatible_source = document(case(99) / "source-aggregate-state.json")
compatible_target = document(case(99) / "expected-aggregate-state.json")
assert compatible_source["root_runtime_id"] == compatible_target["root_runtime_id"]
assert compatible_source["creation_id"] == compatible_target["creation_id"]
assert compatible_target["migration_sequence"] == "1"

# Transform descriptors account for every state-bearing domain explicitly.
variable_rules = document(case(102) / "migration-descriptor.json")["mappings"]
assert {rule["operation"] for rule in variable_rules["variables"]} == {
    "copy",
    "drop",
    "initialize",
    "transform",
}
assert document(case(103) / "migration-descriptor.json")["mappings"]["history"]
assert document(case(104) / "migration-descriptor.json")["mappings"]["components"]
owned_rules = document(case(105) / "migration-descriptor.json")["mappings"]
assert owned_rules["owned_runtimes"] and owned_rules["lifetime_holders"]

transformed = document(case(102) / "expected-aggregate-state.json")
transformed_values = {
    item["variable_declaration_pointer"]: item["value"]
    for item in transformed["runtimes"][0]["variables"]
}
assert transformed_values[
    "/machines/0/root/variables/new_count"
] == ["integer", "2"]
assert transformed_values[
    "/machines/0/root/variables/added"
] == ["boolean", True]
assert transformed_values[
    "/machines/0/root/states/new_state/variables/renamed_shadow"
] == ["integer", "8"]

# The route is exact. A two-hop route produces two ordered audits; an empty route is
# an exact-byte no-op only when its source and target fingerprint are equal.
two_hop = vector(107, "exact_two_hop_route")
assert len(two_hop["migration_route"]) == 2
assert len(document(case(107) / two_hop["expect"]["migration_audit_file"])) == 2
assert vector(107, "empty_route_same_definition_is_exact_noop")[
    "migration_route"
] == []
assert vector(107, "wrong_descriptor_order")["expect"]["code"] == (
    "migration_route_mismatch"
)

# Terminal migrations require maintenance mode and preserve terminal state, identity,
# counters, and diagnostics.
assert vector(110, "maintenance_required")["expect"]["code"] == (
    "terminal_migration_requires_maintenance"
)
for number, expected_status in ((110, "completed"), (111, "faulted")):
    source = document(case(number) / "source-aggregate-state.json")
    target = document(case(number) / "expected-aggregate-state.json")
    source_root = next(
        runtime
        for runtime in source["runtimes"]
        if runtime["runtime_id"] == source["root_runtime_id"]
    )
    target_root = next(
        runtime
        for runtime in target["runtimes"]
        if runtime["runtime_id"] == target["root_runtime_id"]
    )
    assert source_root["status"] == target_root["status"] == expected_status
    assert source["root_runtime_id"] == target["root_runtime_id"]
    assert source["next_logical_step_sequence"] == target[
        "next_logical_step_sequence"
    ]
    assert source["next_output_sequence"] == target["next_output_sequence"]
    assert source_root["fault"] == target_root["fault"]

# Limits fail deterministically and do not truncate. The minimum supported floors
# accept the complete occurrence fixture.
limit_failures = [
    item for item in vectors(112) if item["expect"]["result"] == "failure"
]
assert len(limit_failures) == 17
assert {
    item["expect"]["code"] for item in limit_failures
} == {
    "migration_descriptor_untrusted",
    "migration_resource_limit_exceeded",
}
assert vector(
    112, "minimum_supported_floors_accept_all_listed_dimensions"
)["expect"]["result"] == "success"

failure_codes = {
    item["expect"]["code"]
    for item in vectors(113)
}
legacy_descriptor = vector(
    113, "legacy_snapshot_rejected_by_selected_descriptor_decoder"
)
assert legacy_descriptor["expect"] == {
    "result": "failure",
    "code": "unsupported_migration_descriptor_format",
}
assert failure_codes == {
    "invalid_migration_request",
    "migration_transform_fault",
    "target_definition_unavailable",
    "unsupported_migration_descriptor_format",
    "unsupported_migration_descriptor_schema_version",
}

# One transform rule is applied independently to each runtime and activation. Values
# never leak from one occurrence into another.
runtime_values = variable_values(
    case(114) / "repeated-runtime-expected.json",
    "/migrated_value",
)
activation_values = variable_values(
    case(114) / "repeated-activation-expected.json",
    "/migrated_value",
)
assert [item[2] for item in runtime_values] == [
    ["integer", "71"],
    ["integer", "31"],
]
assert [item[2] for item in activation_values] == [
    ["integer", "71"],
    ["integer", "31"],
]
assert [item[0] for item in runtime_values] == [
    item[0] for item in activation_values
]
assert sorted(item[1] for item in activation_values) == ["0", "1"]

# Identity projections are canonical decimal strings. Values above 2^53 survive
# Python and Rust without binary64 rounding.
decimal_case = case(115)
spawned_values = []
for filename in (
    "spawned-javascript-safe-maximum.json",
    "spawned-first-javascript-unsafe.json",
    "spawned-javascript-rounding-gap.json",
    "spawned-signed64-maximum.json",
):
    aggregate = document(decimal_case / filename)
    spawned_values.append(
        next(
            runtime["target_identity"]["spawned_instance"]["machine_version"]
            for runtime in aggregate["runtimes"]
            if runtime["identity_origin"]["kind"] == "owned_spawned_instance"
        )
    )
assert spawned_values == [
    "9007199254740991",
    "9007199254740992",
    "9007199254740993",
    "9223372036854775807",
]
unbounded = document(decimal_case / "component-unbounded.json")
activation = next(
    runtime["target_identity"]["component"]["activation_sequence"]
    for runtime in unbounded["runtimes"]
    if runtime["identity_origin"]["kind"] == "component"
    and runtime["target_identity"]["component"]["activation_sequence"] != "0"
)
assert activation == (
    "123456789012345678901234567890123456789012345678901234567890"
)

print(
    "108 vectors; package=trusted transport; transforms=total and local; "
    "terminal=preserved; limits=deterministic; decimals=lossless"
)
```

Run it directly whenever you want the shorter, explanatory report:

```sh
.venv/bin/python inspect_vectors.py conformance
```

Expected output:

```text
108 vectors; package=trusted transport; transforms=total and local; terminal=preserved; limits=deterministic; decimals=lossless
```

## 4. Know the three independent identities

[Section 16.1](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#161-independent-artifact-identities)
separates the machine definition, aggregate, and migration descriptor. A definition
fingerprint identifies normalized machine content. An aggregate digest identifies one
complete ownership tree at one point in time. A descriptor digest identifies one
immutable, declarative migration step.

[Canonical encoding in §16.2](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#162-canonical-values-and-aggregate-encoding)
uses RFC 8785 JSON and tagged values. Integers and identity counters are canonical
decimal strings, which is why the lab checks values above JavaScript's safe integer
limit rather than accepting rounded numbers. Malformed relations, unknown fields,
unsupported discriminators, and unsupported schema versions fail with exact codes;
the input bytes remain caller-owned. See
[case 95](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/95-aggregate-wire-rejection)
and
[case 115](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/115-target-identity-decimal-projections).

[The complete aggregate in §16.3](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#163-complete-root-ownership-aggregate)
contains the root, components, owned spawned descendants, variables, history, counters,
faults, and nominal references. It is one transaction boundary. Do not store or advance
an owned child independently.

## 5. Bind immutable identity to an approved definition

[Section 16.4](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#164-immutable-identity-and-mutable-definition-binding)
keeps creation and runtime identity immutable while allowing `current_definition` to
advance.
[Section 16.5](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#165-content-addressed-definition-registry)
requires the resolver to return the exact hash-valid, trusted artifact requested.
[Section 16.6](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#166-aggregate-shape-fingerprint)
distinguishes a compatible definition-only update from a state-bearing transform.

[Case 99](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/99-compatible-definition-upgrade)
shows the compatible path: runtime identity and logical state stay fixed while the
definition binding, aggregate digest, migration sequence, and audit advance.

## 6. Treat migration as closed data

[Descriptors in §16.7](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#167-immutable-declarative-migration-descriptors)
are immutable data, not code. Their restricted CEL transforms cannot call Python,
Rust, JavaScript, shell commands, plugins, files, clocks, networks, credentials, or
author actions.

[The route algorithm in §16.8](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#168-exact-route-and-migration-algorithm)
uses exactly the ordered digest list supplied by deployment. It does not search for a
newer or shorter route. Every intermediate candidate is validated in memory and only
the final result may commit.
[Case 107](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/107-migration-chain)
checks exact no-op bytes, a two-hop audit, wrong ordering, missing routes, and cycles.

[The total transform matrix in §16.9](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#169-total-transform-matrix)
requires every retained source occurrence and required target occurrence to be
accounted for. The vectors demonstrate:

- variable copy, transform, initialize, and destructive drop in
  [case 102](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/102-variable-migration);
- null, deep, and shallow history in
  [case 103](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/103-history-migration);
- component placement and activation identity in
  [case 104](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/104-component-migration);
- owned-runtime binding, lifetime holder, and nominal reference preservation in
  [case 105](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/105-owned-runtime-migration); and
- independent rule application for repeated runtimes and activations in
  [case 114](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/114-occurrence-local-transform-binding).

Rules read one immutable pre-descriptor snapshot. They cannot combine values from
different runtimes or observe another rule's output.

## 7. Keep terminal aggregates terminal

[Section 16.10](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#1610-terminal-aggregates)
requires `maintenance_mode: true` for a non-empty terminal migration. The descriptor
must preserve the matching terminal policy. A completed aggregate remains completed;
a faulted aggregate preserves its diagnostic tree and fault anchors. Neither migration
reactivates a runtime or emits an event.

[Case 110](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/110-completed-terminal-migration)
checks the completed path.
[Case 111](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/111-faulted-terminal-migration)
checks fault preservation and policy rejection.

## 8. Separate pure failures from host quarantine

The SQLite tutorial implements
[the transactional ordering in §16.11](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#1611-lazy-transactional-host-ordering):
resolve immutable artifacts before the transaction, lock aggregate and inbox, migrate
and dispatch once, then commit aggregate, inbox, outbox, and audit together.

[Section 16.12](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#1612-failure-rollback-quarantine-and-audit)
separates two layers:

- the pure engine failure is only `{code}` and leaves the exact aggregate bytes with
  the caller;
- the host transaction retains those bytes, blocks the inbox item, records quarantine
  metadata, and appends a failure audit.

Installing a corrected trusted route may release the blocked item. It does not erase
the failure audit. This is not an engine fault, dead letter, or aggregate status.
[Case 113](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/113-migration-failure-completeness)
checks the closed failure surface; the SQLite guide checks the database transaction.

## 9. Move aggregates without inventing imports

[Package transport in §16.13](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#1613-package-transport)
is an archive or transfer envelope containing one aggregate plus optional definition
and descriptor attachments. Attachments must reproduce their digests, satisfy all
cross-references, and seed a resolver with put-if-absent semantics. They never override
an existing digest and are not part of the aggregate digest.

[Case 97](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/97-aggregate-package-attachments)
checks integrity, duplicate attachments, unsupported package versions, resolver
seeding, idempotency, and collision refusal. This transport does **not** enable package
imports in machine YAML. Portable package imports remain unsupported format-1
semantics.

## 10. Set limits before loading untrusted artifacts

[Section 16.14](https://github.com/fruwehq/determa-state-spec/blob/v0.2.0/SPEC.md#1614-security-and-resource-limits)
requires digest checks, pinned trust, retained referenced definitions, and configurable
limits for aggregate and artifact size, JSON shape, runtime/state/value counts, route
and rule counts, and migration CEL work.

[Case 112](https://github.com/fruwehq/determa-state-conformance/tree/v0.2.0/conformance/core/112-migration-security-limits)
proves the minimum supported floors succeed and every lower configured dimension fails
with `migration_resource_limit_exceeded`. Understated descriptor requirements fail;
the engine never truncates a transform. Every failed vector returns no candidate or
audit and leaves the exact input artifact with the caller.
