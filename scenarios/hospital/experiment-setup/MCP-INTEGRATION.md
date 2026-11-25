# MCP compatibility and integration notes

## Inspection basis

Read-only inspection of SegmondFault/onos-intent-mcp-doc-context commit
099b35852963b6315713fd43ec87f393a702e357. This verifies source capabilities,
not which checkout, settings or processes are currently deployed.

The selected ten tests do not currently require a new MCP feature. Deployment,
baseline reset and end-to-end verification are still outstanding.

## Configuration changes

Retain the deployed ONOS URL, control URL, credentials and HTTP binding after
checking them. Merge the eight-host ONOS_HOST_ALIASES value from mcp-aliases.env.
Set ONOS_CONTEXT_MANIFEST to the absolute deployed path of ../context/manifest.json;
the Streamable HTTP server also accepts --context-manifest. Resolve that path
after selecting the deployment directory, rather than assuming a local path is
valid remotely.

Remove inherited ONOS_WEBSITE_ALIASES and --website-alias arguments in the separate
hospital configuration. They map simulated websites onto hospital endpoints in
the old notebook and are not part of these tests. Keep the tool catalogue constant
across models and record unused tools if they remain advertised.

Use the document-aware server entry point defined by the project's packaging;
the core.py stdio fallback does not configure the document catalogue. Do not
change the existing shared service before checking its actual launch command.

## Available operations and limitations

| Need | Existing support | Integration detail |
|---|---|---|
| Read roles and policy | list_context_documents; read_context_document | Catalogue the two new documents; update old four-document readiness checks. |
| Resolve eight host names | ONOS_HOST_ALIASES / --host-alias | Use nurse, doctor, patient, monitor, alert, adminpc, adminsrv, guest. |
| Inspect network | get_network_context; list_intents; list_flows | General flow context includes priority 100 only. |
| Establish a pair | connect_nodes / create_intent | May require force=true for shared endpoints; never duplicate an active pair. |
| Withdraw a pair intent | disconnect_nodes / remove_intent | Does not itself guarantee unreachability if other forwarding exists. |
| Explicit pair isolation | block_traffic | Temporary bidirectional exact-match drop rules; account for expiry. |
| Remove a managed pair block | unblock_traffic | Removes matching MCP-managed drops only. |
| Verify reachability | check_connectivity | Pass actual Mininet node names; no alias translation inside the ping call. |

connect_nodes with two hosts creates an ONOS host-to-host intent. With switch or
host-to-switch endpoints it changes a physical simulated link. The same distinction
applies to disconnect_nodes. Physical link operations are not an authorised
substitute for the selected pair-level changes.

force=true bypasses the shared-endpoint overlap guard when adding an intent. In
the inspected implementation it does not remove existing intents, bypass a drop
rule, or override hospital policy. Duplicate pairs still raise an error. During
setup this option can establish the explicitly specified overlapping required
pairs. During model runs judge its use by policy, actual scope and outcome.

remove_intent raises an error when no matching active intent exists. Reset logic
must inspect inventory and remove only existing experiment intents, not blindly
call disconnect_nodes for all 28 pairs. Its matching removal spans application
IDs; enforce experiment ownership in the operator-side reset rather than assuming
the tool limits deletion to its configured app ID.

## Recommended baseline implementation to validate

Prefer the previously exercised intent-only forwarding approach if the deployed
environment supports it: automatic reactive forwarding disabled in the dedicated
experiment, consistent static ARP, six explicitly established pair intents and no
other forwarding that makes disconnected pairs reachable. This avoids relying on
expiring drop rules for the starting states. It is a candidate implementation,
not a verified deployed fact.

If this approach cannot produce the full expected matrix, inspect residual flows,
controller applications and forwarding behaviour before choosing explicit drops.
Never accept intent inventory alone as proof of isolation.

For either approach:

1. Snapshot controller state and check experiment ownership before cleanup.
2. Restore all attachment and inter-switch links in the dedicated environment.
3. Discover hosts and establish consistent address resolution.
4. Remove only residual experiment intents and managed blocks that conflict with
   the chosen state. Wait for withdrawal/convergence before creating replacements.
5. Establish the selected state's connected pairs, using the documented overlap
   allowance only where required and skipping existing identical active intents.
6. Verify all 56 directed reachability expectations before submitting a request.

In the intent-only implementation, G01 removes nurse–adminsrv; B01 adds
patient–monitor; B02 adds monitor–alert; B03 removes the two forbidden guest
intents; B05 performs all four repairs. These are implementation examples, not
tool-call answers to include in the model-facing policy.

## Remaining live inspection

Direct SSH was not authenticated during preparation. Before deployment inspect:

- Actual host versus VM identity, Mininet location and launcher/service.
- MCP checkout commit, uncommitted changes and running server entry point.
- Effective ONOS/control endpoints, aliases and document-manifest path.
- ONOS applications, active intents, relevant rules and current topology.
- Whether another experiment is active before starting or stopping services.

Do not run the old notebook's full setup blindly: it selects a five-host topology
and includes VM/service restart operations. Integrate the eight-host package into
a separate working copy and validate it before the formal experiment.
