# Apply the eight-host hospital package

## What is ready

The existing Mininet topology, eight aliases, common policy and role directory,
G/B JSON definitions, operator state helper and connectivity checklist are ready.
The live document-aware MCP has not been reconfigured for this package.
No new server features or additional running MCP instance are proposed.

The new mcp-hospital.env is a configuration fragment, not a replacement for the
current full configuration or a discovered service launch command. It uses a
proposed host deployment directory; change it if choosing another location.

## Host-side MCP configuration

1. Copy the full hospital directory from the VM checkout to a directory readable
   by the existing MCP account on gray-area. A proposed destination is:
   /home/grayadmin/final-scenario/hospital-eight-host
   Preserve the old hospital documents separately. Do not merge old and new
   policies into one catalogue.
2. At that destination confirm context/manifest.json and its two documents exist.
   A VM-only path is not readable automatically by the MCP process on gray-area.
3. Merge the three settings in experiment-setup/mcp-hospital.env into the current
   server configuration. Adjust ONOS_CONTEXT_MANIFEST to the actual host path.
   Preserve the current ONOS credentials, app ID, ONOS/control URLs, HTTP port,
   bind address and transport settings. In the inspected running setup, the
   existing Mininet control connection already reaches the eight-host VM.
4. Remove old --website-alias arguments and environment mappings. Remove or update
   conflicting --host-alias and --context-manifest command-line arguments, which
   can override the environment. Do not assign simulated websites to monitor or
   alert endpoints for this experiment.
5. Restart the existing MCP through its existing owner-managed launch mechanism.
   Do not execute the old notebook's full five-host topology/restart sequence.
6. Run inspect_mcp.py against its /mcp endpoint. Expected host aliases are the eight
   named hospital nodes. The document catalogue should contain only:
   hospital-01-scenario-brief and hospital-01-connectivity-rules.
7. Read both documents through MCP and compare contents/hashes with the new files.
   Check patient-to-monitor ping through check_connectivity using the actual node
   names. In verified G, make and undo a nurse-to-adminsrv disconnection through
   MCP; verify the target effect and preservation of the other 27 host pairs.
   Host-pair restoration may need force=true because endpoints are shared with
   other permitted intents. Restore and verify G afterward. These integration
   checks precede model experiments and are recorded separately.

The MCP inventory reported 28 devices whereas Mininet reported three switches.
Inspect device availability and ownership; do not delete stale entries blindly.
Record/filter stale devices in experiment observations and ensure current host
attachments refer to s1, s2 and s3.

## Notebook integration

This requires adapting the existing notebook, not merely loading the env fragment:

- Select the eight-host network.json and retain correct controller/control URLs.
- Replace all h1-h5 host lists, role maps, link lists and probes with the eight
  actual names and IPs in the directory. Nurse=nurse; administrative server=adminsrv;
  patient monitor=patient; monitoring server=monitor; alert service=alert;
  doctor=doctor; administrative workstation=adminpc; guest workstation=guest.
- Replace four-document readiness requirements with the two catalogue IDs above.
- Import the exact G01-G05 and B01-B05 prompts and criteria from the agreed Excel.
  Old 16-question results and website cases are not results for the new experiment.
- For each request and model, run hospital_state.py apply G/B in the VM, followed
  by verify G/B. The default verify uses three probes per direction. The helper
  assumes an already running topology, discovered hosts and consistent ARP.
  If invoked from the host, use the normal authorised SSH route to the VM; copied
  helper files on gray-area do not make its VM-default network addresses valid.
- Replace old per-question five-host resets and scoring with the Excel expectations.
  In particular, B01/B02 repair only one path, B03 removes the two guest violations,
  B04 makes no changes and B05 repairs all four faults. Preserve other starting
  faults in narrowly scoped tests.
- Use fresh conversations, consistent tool/model settings, separate assessment
  dimensions, binary overall results and model-specific observations/evidence.
- Do not score unchanged connectivity as sufficient if the final answer is false.
  Distinguish unsafe attempts, actual outages, invalid setup and infrastructure errors.

## Evidence already obtained

VM evidence root:
/home/skynet/lab2/nen-onos-intent-mcp/scenarios/hospital/experiment-setup/evidence/

- B-verify-20261121T122604334291Z: all 56 directions matched, three probes each.
- G-apply-20261121T123552171566Z: automatic B-to-G intent preparation succeeded.
- G-verify-20261121T123759022816Z: all 56 directions matched, three probes each.
- B-apply-20261121T124643370726Z: automatic G-to-B intent preparation succeeded.
- B-verify-20261121T124707918778Z: all 56 directions matched, one-probe smoke check.
- G-apply-20261121T125158789440Z: G intents restored afterward; this last operation
  alone is not a fresh full reachability verification.

The initial helper failed on a GET request header and was corrected before these
successful verifications. The current prepared helper includes that correction.
The host-side read-only MCP inspection confirmed a working control connection,
eight discovered hosts, empty descriptive aliases and the old document catalogue.
MCP end-to-end alignment remains pending until the steps above pass.
