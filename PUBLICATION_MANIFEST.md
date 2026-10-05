# Unreleased 0.3.0 publication manifest

Status: **incomplete; publication held**. This records evidence and remaining gates,
not approval to tag, publish, create a release, dispatch a release workflow or deploy.
The [reopened scope audit](https://github.com/fruwehq/determa-state-examples/issues/21)
supersedes the earlier completion statement. Contracts remain version 1 and machine
documents use numeric `format: 1`.

## Source identity and review

These are interim public checkpoints. Final engine, documentation and example
heads, reviewed trees, gate results and package inventories must be replaced together
after the remaining implementations land.

| Repository | Verified merged main | Evidence |
|---|---|---|
| Specification | `77c0a2e60cd0771a6d44ae170a079ddd51d7d9f0` | PR111, executable-slot/provider identity clarification |
| Conformance | `dc84ed81ea36a5f2140181a97660477a14347ccc` | PR106/109/110/112, independent reviews and validation; last-moment timer lease vectors |
| Python | `2f27a78bd9ab114da0e971e90ba548d55913330c` | PR109, exact reviewed/merged tree match, seven CI checks, independent review |
| Rust | `3edad6322011accf81ece6a30134fa183548aceb` | PR63, exact reviewed/merged tree match, four CI checks, independent review |
| Documentation | `7619c16f8de5c90b660d66badb826ba9be563c06` | Historical candidate; source pins and full manual audit need refresh |
| Examples | `1f339af40ce4f13a88331f89a8f69b7eaf26ead9` | Historical catalog; infrastructure acceptance and final audit remain open |

Python's merged runtime-provider implementation passed all 52 operational vectors,
505 unit tests (six PostgreSQL skips in that offline run), six actual PostgreSQL
tests, 1,083 conformance tests, 46 authority tests and 43 committed-effect tests.
Rust's merged native implementation passed all seven native inspections, 487 artifact
documents, 52 operational provider vectors, all-features Rust1.86 build/tests
(115 tests including vector loops), Clippy, packaging and 19 fresh native store gates.
These counts establish those checkpoints' scope, not completion of the remaining
optional host implementations.

Draft Python PR111 and Rust PR65 continue timer and authority/effect integration.
Python timer checkpoint `fd90681c534707ba24826d02b0f962f3b1b84445` passed scoped
independent review, 569 unit tests, 1,083 pinned conformance tests and six dedicated
tests against actual PostgreSQL. It includes spawned-process SIGKILL before and after
coordinated commit, immutable storage-bound original-request/result/artifact evidence
and strictly local native-fate reclaim. Replacement fencing requires the native
writer lock, complete history, permanent checkpoint receipts and unchanged trusted
implementation/configuration. Independently admitted matching events do not become
helper completion proof. Review caught replaceable-method and mutable-code bypasses;
pre-invocation dispatch checks and regression tests resolve them. Verified installation,
archive/recovery/authority composition and the full operational profile are unfinished.
Rust authority checkpoint `85c4c1d1b3c41de2f3f50b241ea4bb5576181659` passed scoped
independent review, 131 all-feature tests, all 19 required fresh native execution-store
gates with actual PostgreSQL, and all-target Rust1.86 Clippy. Guarded checkpoint loads
and conflict-return bytes share the same validated native snapshot; immutable allocation
binds original owner bytes/digest. Real staged-write failure and SIGKILL before/after
commit use the same production native SQL; fresh reopen verifies retained replay.
Child stdout isolation preserves strict gate reporting. Complete frozen inventories,
worker fences, fate profile, relocation and committed native effects remain unfinished.
Infrastructure draft PR24 at `10790a63013a657eef7d295892085e873982f505` has a separate
durable provider and bounded foreground process bridge. Eleven tests and scoped
independent review passed, including SIGKILL/SIGSTOP/timeout/restart and exact retained
native evidence. Canonical-byte verification preserves JSON boolean/integer distinctions.
Host/machine/verified-handler integration and the full lifecycle matrix remain unfinished.
Evolving checkpoint SHAs and CI results are recorded in PR bodies and the scope audit.
Scoped review does not approve a full profile.
Only ordinary pushes are permitted; verify each remote head. Earlier force pushes
remain an acknowledged process violation.

## Distribution contents and registry destinations

| Artifact | Registry target | Interim reviewed package |
|---|---|---|
| Python wheel | [PyPI determa-state](https://pypi.org/project/determa-state/) | `determa_state-0.3.0-py3-none-any.whl`, 76 files |
| Python source distribution | Same PyPI project | `determa_state-0.3.0.tar.gz`, 125 files |
| Rust crate | [crates.io determa-state](https://crates.io/crates/determa-state) | `determa-state-0.3.0.crate`, 102 files |

The complete interim file lists, byte sizes and SHA-256 digests are retained in
[Python inventory](audit/packages/python-native-interim.json) and
[Rust inventory](audit/packages/rust-native-interim.json). Python inventory binds
reviewed head `d1d626a15a909d176f915013d88c0fa7a6ba7597`; Rust binds reviewed head
`dadd601ab0587c4b0693a62749b145a7910fcf65` and its merged main. They are **not the final
release artifacts**: timer/authority changes are newer. Regenerate wheel, source
distribution and crate from final reviewed sources, verify metadata and exact contents,
record their digests, and verify exclusions before any publication decision.

Python's distribution is `determa-state`, import `determa.state`; its namespace package
and declared version-1 JSON schemas are included. Rust's crate/library is
`determa-state`/`determa_state`, with `determa-state` and `determa-state-rust`
validation binaries. Repository-only conformance observations, adapters and excluded
test fixtures must stay outside the published crate. Check new files against package
manifests; an old packaging pass does not prove new files are present or excluded.

Specification and conformance are public Git repositories, not engine registry
packages. Documentation and examples remain public source and validation artifacts.
No website deployment is authorized.

## Release workflow and manual approval evidence

| Repository | Workflow behavior read from source | Actual approval evidence |
|---|---|---|
| Python | `.github/workflows/release.yml`, push `v*`; verifies tag/version, builds wheel/sdist, checks metadata and contents, uploads `dist`; publish job uses `environment: pypi` and OIDC | **Blocked**: live `pypi` reviewers, self-review restriction, branch/tag rules and PyPI Trusted Publisher binding not verified |
| Rust | `.github/workflows/release.yml`, push `v*` or manual dispatch of an existing tag; verifies tag/version, OIDC, `cargo publish --locked` | **Gap**: current job declares no GitHub Environment. Live crates.io Trusted Publisher binding and a required manual publishing gate are not proved |
| Documentation | Only `.github/workflows/docs.yml`; validation on PR/main/schedule/dispatch. `PUBLICATION_HOLD.md` and input hashes prohibit Pages publication steps | Hold present; strict validation required again after final source/content updates |
| Conformance | `.github/workflows/validate.yml` validates public source | No engine package publication workflow |
| Specification | No `.github/workflows` directory at the checkpoint | No package publication workflow |
| Examples | Seven application validation workflows at the historical catalog main | Infrastructure workflow and complete final acceptance remain pending |

Workflow YAML is evidence of requested behavior, not evidence that GitHub's live
Environment protections or registry Trusted Publisher configuration exist. The
Rust [draft PR67](https://github.com/fruwehq/determa-state-rust/pull/67) proposes a
`crates-io` Environment declaration; it is unmerged and live protection remains unproved.
The connector rejects Environment endpoints and the prepared Cloud proxy blocks
`api.github.com`; do not bypass that boundary or substitute workflow comments for
live settings. Required evidence includes exact repository/environment, required
reviewers, prevention of self-review where applicable, permitted deployment
branches/tags, and the registry's exact repository/workflow/environment binding.
No credential material belongs in this manifest.

The intended coordinated version is `v0.3.0`, but no tag is authorized or created.
A later publication decision must choose exact final commits and an execution order
for spec, conformance, Python and Rust tags, account for tag-triggered publication,
and provide manual approval at each publishing boundary. This manifest does not
authorize a workflow dispatch or create a registry publisher.

## Acceptance still required

- Concrete synchronized Python/Rust timer, archive and recovery providers, registered
  against actual source/configuration, with full operational profile vectors.
- Rust committed native effects and complete guarded authority host composition,
  inventories, worker fences and proven native transaction fate.
- Same-authority local relocation with source retirement and one-use destination
  activation; immutable quarantine and explicit fresh-scope takeover/clone/reconciliation.
- Infrastructure lifecycle application with a separate durable fake provider and
  actual process-kill/restart matrix; timer/recovery/relocation examples.
- Final documentation/example source closure and exact immutable engine pins;
  regenerated final package inventories and all required gates.
- Live manual approval/registry publisher proof, exact-head independent final audit,
  and a separate publication decision.

Unsupported topologies must refuse explicitly. Schema validation, conditional vectors,
a clock timeout or a readable copy do not prove an operational provider, transaction
rollback, safe takeover or completion of this checklist.
