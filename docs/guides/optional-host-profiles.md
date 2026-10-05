# Optional host profiles and extension providers

A machine definition describes portable behavior. An extension provider supplies a
configured host boundary around that behavior. The pure engine never performs network
calls, starts a scheduler or grants ownership of a scope. An embedding application can
use `create`, `admit` and `step` with its own transaction and no authority service.

The 0.3.0 candidate keeps every public contract at version 1. The Python and Rust
registries validate closed descriptors, exact references, configuration and required
capabilities. Registration identifies a provider; operational verification must still
prove the configured instance, source closure, health and transaction boundary. A
provider name or a Boolean claim cannot establish those facts.

## Select only the capabilities you can prove

A host resolves an exact provider reference and configuration, then verifies its
runtime implementation before composing a profile. Replacing the implementation,
changing configuration or losing health invalidates that evidence. Unsupported or
unproved requirements fail closed as `host_capability_mismatch`. SDK objects,
callbacks, transaction handles and credentials remain inside the provider. Portable
artifacts contain only closed serializable values and nonsecret references.

The store registry supports explicit memory, file, SQLite and PostgreSQL selection.
Memory is ephemeral. File storage persists across restart. SQLite's tested local
transaction supports its declared single-writer boundary. PostgreSQL can compose a
checkpoint with application rows in a verified shared transaction. These properties
do not establish distributed coordination or exactly-once external delivery.

## Scope authority and worker fencing

The local authority implementation stores epochs, generations, guarded writes, worker
claims and inventory evidence in the same tested SQLite boundary as the checkpoint.
A guarded commit checks the current authority and worker fence again at commit.
Freezing stops new authorized work; retirement and destination activation require
separate retained evidence. Copying a database does not produce a second authority.

A host profile report separates `guarded_local_writes`, `worker_fencing`,
`complete_scope_inventory` and `safe_relocation`. Without a verified authority provider
all four are false. A healthy source does not prove destination support. The reference
implementation cannot claim safe relocation across independent authorities; this
release defines no leader election, distributed coordinator or managed control plane.

## Commit native intents before invoking a provider

Python's `determa.state.effects.SQLiteCommittedEffectHost` implements the local SQLite journal boundary. It
requires a `VerifiedNativeHandler` for dispatch; an ordinary callback is refused.
The producing transaction commits the aggregate, external intent, pinned route and
business operation token before the provider is invoked. Destination calls use
`(logical_scope_identity, effect_id)` as their idempotency identity.

The journal records claims, attempts, cancellation decisions and native outcomes.
The host rechecks trusted time and the original claim deadline before and after a
handler and before committing its result. A result uses the pinned definition,
runtime incarnation, token and route; worker authentication is separate from event
correlation. Authenticated result admission and later machine processing are separate
commits. An outcome retained before a crash can be admitted by host recovery without
calling the provider again or pretending an expired worker claim is live.

An ambiguous call cannot be retried merely because two caller-supplied byte strings
match. The installed provider must independently verify its native destination's
retained deduplication receipts for that exact scope, effect and destination. Missing,
forged or unavailable evidence refuses the retry. This boundary proves committed local
state and authenticated result delivery, never exactly-once execution at an arbitrary
remote endpoint. Rust's registry and host gates expose only their implemented
capabilities; do not infer Python's native-effect implementation from matching schemas.

## Project application rows without losing state

`ApplicationProjectionFacade` selects a finite set of application rows and supplies
the host-owned native transaction to the mapping plugin. The mapping reconstructs the
complete portable checkpoint exactly, validates the selected identity, normalizes
only declared input or external-refresh data, then projects the new state back to
those rows. The facade commits checkpoint and selected rows together. The plugin must
not independently commit, access unrelated rows or substitute a lossy business view
for the full aggregate.

Bindings initialize externally supplied variables; declared inputs carry business
commands; `env` refresh updates declared external variables. These are distinct
boundaries. A plain database column does not silently become a machine variable.
Rollback preserves both the previous checkpoint and the selected application rows.

## Preserve every ingress and outbound decision

A lossless delivery adapter retains the original source identity and canonical bytes
or typed transport value. Source identity is distinct from machine `event_id`.
Canonical Base64 decoding must reproduce the exact original spelling, including
padding. Equal source identity with different content is a conflict.

Source acknowledgement follows the atomic commit of admission plus its source
binding, or a durable dead-letter transfer. Rejection before admission leaves the
source responsible unless a declared policy durably transfers it. Ready/deferred
placement, terminal machine disposition, lifecycle disposal and outbound intents are
all observable decisions; ignoring any of them prevents a lossless claim. An
unhandled machine input differs from a malformed ingress item. Outbox retention and
idempotent destinations govern external delivery independently of machine handling.

## Archives, timers and recovery remain conditional

An archive is a consistent snapshot of explicitly selected root checkpoints and their
complete declared participant closure. It retains queues, receipts, tombstones,
outbox work and referenced immutable definitions. An archive digest checks content;
it grants no scope rights and restores no active worker claim. Import creates inert
staging after independently trusted source, participant and capability checks.

The optional external timer helper owns its clock, timer identities, cancellation and
fire fences. It submits declared events through ordinary admission and retains its
own delivery evidence. The pure core has no clock or `poll_due`. Timer recovery must
account for ambiguous delivery rather than claiming that a due deadline proves a fire.
The timer ledger is an archive participant only when that contract is declared.

Recovery consumes a verified inert stage. Strict restore stays quarantined. Explicit
standalone takeover requires its recorded risk acknowledgement and fresh destination
scope. Cloning creates independent execution with isolated destination effects.
Same-authority relocation requires positive topology support and transfer-specific
retirement evidence. Unsupported topology refuses before mutation. None of these
operations follows automatically from copying portable archive bytes.

The schemas and conformance vectors describe these optional boundaries; they do not
install an archive exporter, scheduler or recovery provider. Configure and test every
claimed participant and operation before advertising it.

## Use one public protocol for local and future remote hosts

The public v1 protocol uses named endpoint and scope bindings plus exact root/runtime
identity. Authentication stays outside portable messages. Its host `operation_id`,
creation ID, event ID, effect ID and business operation token have separate lifetimes.
The request digest binds the complete closed request. A mutation retains the first
exact response atomically with its committed evidence; equal replay returns those
bytes without core execution or endpoint resolution. Unequal reuse is a conflict.

A `committed` response means the named transaction committed or a bound read returned.
A `pending` response requires retained acceptance evidence linked to that exact public
request. An in-memory promise cannot produce it. A timeout produces no protocol
response and means outcome unknown; absence of a receipt never proves rollback.
Capabilities list only implemented, tested operations and independently verified
profiles. Every invocation rechecks its dependencies. A future remote service or MCP
transport uses the same closed messages and fixture matrix, with no private machine
syntax or special activation path.

## Normative coverage

The specification owns the complete closed requests, records, digests and refusal
precedence. Follow the pinned sections for implementation details:

- [§11.5 extension identity and capabilities](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#115-public-extension-identity-registration-and-capabilities)
- [§18 scope authority](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#18-optional-host-scope-authority)
- [§19 committed native effects](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#19-committed-native-effects-and-authenticated-results)
- [§20 lossless application projection](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#20-lossless-application-projection-and-embedded-transaction-facade)
- [§21 lossless delivery](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#21-lossless-event-delivery-profile)
- [§22 archives](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#22-portable-archives-and-declared-participants)
- [§23 timer helper](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#23-optional-external-timer-helper)
- [§24 recovery](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#24-recovery-fresh-scope-takeover-cloning-and-optional-relocation)
- [§25 public client/host protocol](https://github.com/fruwehq/determa-state-spec/blob/86bb88dd21cb1f799eefe5020b6e49dabf6e7225/SPEC.md#25-public-client-and-execution-host-protocol)
