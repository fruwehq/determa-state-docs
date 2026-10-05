# Public clients and local hosts

The unreleased 0.3.0 candidate exposes the version-1 `determa.execution_host`
protocol. Python's qualified `determa.state.public_client` and
`determa.state.public_host` modules provide a durable client journal and a local
SQLite implementation. Rust offers the corresponding `public_host` module with
its SQLite feature. A transport adapter may carry the same messages over HTTP or
MCP; credentials, endpoints and authenticated principals stay outside machine YAML
and portable artifacts.

This tutorial uses an in-process transport so you can examine commit and retry
semantics without configuring a server. It uses the Python candidate installed by
the manual's reviewed source lock. The local host advertises capabilities, create,
admit, process, read, structural inspection and receipt retrieval. Optional helpers
must be discovered before use; this host does not advertise effects, authority,
timers, archives or recovery providers.

Create a fresh directory and save this numeric format-1 machine as `counter.yaml`:

<!-- determa-example: public-host-tutorial/counter.yaml -->
```yaml
format: 1
namespace: tutorial.public_host
events:
  increment:
    direction: input
    payload:
      amount: {type: int, required: true}
machines:
  - machine_id: counter
    version: 1
    root:
      variables:
        count: {type: int, init: 0}
      on_events:
        increment:
          action:
            - assign: {count: "count + event.payload.amount"}
```

Save `app.py` beside it:

<!-- determa-example: public-host-tutorial/app.py -->
```python
from pathlib import Path
import sys

import determa.state as ds
from determa.state.public_client import EndpointBinding, PublicHostClient
from determa.state.public_host import SQLitePublicExecutionHost

root = Path(sys.argv[1])
bundle = ds.load_bundle((root / "counter.yaml").read_text())
resolver = ds.MemoryArtifactResolver(definitions={bundle.fingerprint: bundle})
host = SQLitePublicExecutionHost(
    root / "host.db", scope_alias="tutorial", scope_binding_identity="tutorial-binding-1",
    authorized_principals=frozenset({"alice"}), resolver=resolver,
)
host.setup_schema()
lose_response = True


def transport(endpoint, request):
    global lose_response
    assert endpoint == "local-tutorial"
    # An HTTP adapter authenticates credentials before calling handle().
    response = host.handle(request, principal="alice")
    if request["operation"] == "create" and lose_response:
        lose_response = False
        raise TimeoutError("response lost after the authoritative commit")
    return response


client = PublicHostClient(root / "client.db", {
    "selected": EndpointBinding("local-tutorial", "tutorial")
}, transport)
client.setup_schema()
request = {
    "protocol": "determa.execution_host", "protocol_version": 1,
    "scope_binding_identity": None, "operation": "create", "operation_id": "tutorial-create",
    "target": {"root_instance_id": "tutorial-counter", "runtime_id": None,
               "runtime_incarnation": None},
    "precondition": None,
    "arguments": {"validated_bundle_fingerprint": bundle.fingerprint,
                  "namespace": "tutorial.public_host", "machine_id": "counter",
                  "machine_version": "1", "root_instance_id": "tutorial-counter",
                  "creation_id": "tutorial-counter:create", "bindings": ["map", []]},
}
try:
    client.submit("selected", request)
except TimeoutError:
    pass  # Unknown fate: do not invent a new creation or assume rollback.

# Restart and change the alias. Previously saved work retains its original route.
client = PublicHostClient(root / "client.db", {
    "selected": EndpointBinding("a-different-endpoint", "a-different-scope")
}, transport)
receipt = client.receipt("tutorial-create")
assert receipt["value"]["result"]["retention"] == "retained"
recovered = client.retry("tutorial-create")
assert recovered == receipt["value"]["result"]["saved_response"]
assert recovered["status"] == "committed"
checkpoint = recovered["value"]["result"]["checkpoint"]
assert checkpoint["execution_checkpoint_schema_version"] == 1
print("public create=committed; restart=retained; retry=original-binding")
```

Run it in the fresh directory, using the reviewed candidate environment:

```sh
python app.py .
```

The output is:

```text
public create=committed; restart=retained; retry=original-binding
```

The client saves the complete request and resolved endpoint/scope binding before
transport. A timeout has no protocol response and means unknown outcome. Receipt
lookup and exact retry use that saved binding, even after a deployment alias changes.
The SQLite host commits its checkpoint and complete first public response together;
replaying that response requires no new definition resolution or core execution.
An unknown or expired receipt does not prove rollback.

Each new mutation must discover the required capability and supply the operation's
closed arguments and target. Processing an admitted event additionally uses the
runtime identity/incarnation and checkpoint revision/digest precondition. `admit`
commits mailbox acceptance; `process` commits the selected core step. These are
separate decisions. An empty mailbox may return `not_runnable` with no public
mutation receipt while still retaining its first response for exact replay.

The local host owns its transaction. A remote request cannot join your application's
local database transaction; use an explicit application inbox/outbox when coordinating
business rows with remote execution. The host authenticates before revealing whether
work exists. Do not place transport tokens in `arguments`, payloads or machine definitions.
SQLite scope and client databases belong to this disposable tutorial. Stop all users
before resetting them; never delete individual live receipt or checkpoint rows.
