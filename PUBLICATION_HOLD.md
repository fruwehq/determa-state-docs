# Documentation publication hold

The documentation workflow validates every pull request, main push, scheduled run,
and manual dispatch. It does not configure GitHub Pages, upload a Pages artifact, or
deploy a site. This hold remains in force when source commits are changed, a release
tag appears, or a workflow is manually dispatched.

Reintroducing any Pages publication action requires a separate reviewed change and
explicit publication authorization after the final release audit. A strict local
site build remains part of `make check`; its output is only a validation artifact.

`sources.lock.yaml` declares `lifecycle: released` with exact matching tags or
`lifecycle: candidate` with exact public commits and no tags. Candidate validation
checks those public commits and synchronized source versions. Released validation
additionally checks that each tag resolves to its pinned commit and remains the
latest published semantic version. Neither lifecycle state authorizes publication.
Candidate CI installs the Python engine from its exact public Git commit and checks
the installed package files against the pinned checkout. Every extracted candidate
Cargo manifest must use the exact public Rust Git repository and full locked commit.
The matching future candidate update must remove the registry `determa-state`
requirement and update the tutorial dependencies and traces together with the engine
API changes. `make check` mechanically enforces the workflow and local action hold.
