# Contributing

The tutorial must stay understandable to a first-time user and exactly synchronized
with released Determa State behavior.

## Before writing

1. Open one focused issue.
2. Confirm the behavior is already normative in the specification, represented by
   conformance, and implemented by both released engines.
3. Link the relevant specification sections and conformance cases.
4. Do not teach planned or host-specific behavior as portable core behavior.

## Author once

Write examples inside the chapter that explains them. A named fence looks like:

````markdown
<!-- determa-example: machines/example.yaml -->
```yaml
format: 1
...
```
````

The path must be relative, unique, and remain below the generated example root.
Validation extracts it to a temporary directory. Do not commit a second copy.

Python and Rust runner fences use the same mechanism. Both runners must consume the
same extracted machine and assert the same observable trace.

## Update coverage

Every pinned normative section and core conformance case has exactly one entry in
`coverage.yaml`.

- `covered`: an existing chapter demonstrably explains or executes the item.
- `planned`: the item is assigned to an existing chapter path and open child issue.
- `non_user_facing`: the item is repository/testing machinery rather than a tutorial
  behavior; include a specific reason.

Never mark an entry covered merely because a chapter mentions its name.

## Validate

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --requirement requirements.txt
make sources
make check
```

Do not update `STATE_VERSION` or `sources.lock.yaml` independently. A synchronized
State release update must refresh all four pinned repositories, regenerate the coverage
inventory, update affected chapters, and pass both engines.

## Pull requests

- One issue maps to one pull request.
- Keep generated output out of Git.
- Report the exact validation run.
- Resolve every review conversation before squash merge.
- Do not change version pins, publish Pages, or merge unrelated tutorial stages in the
  same pull request.
