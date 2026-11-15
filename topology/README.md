# Mininet Topology Launcher

Starts a Mininet topology from JSON, connects its switches to ONOS, and optionally exposes the control API used by the MCP ping and link tools.

This directory is separate from the MCP server. It requires Mininet on the machine running the topology, plus a reachable ONOS controller. The launcher itself uses only Mininet and the Python standard library.

## Topology file

See [`example.json`](example.json). The schema is:

```json
{
  "switches": [
    {"name": "s1", "dpid": "0000000000000001"}
  ],
  "hosts": [
    {
      "name": "h1",
      "ip": "10.20.0.1/24",
      "mac": "00:00:00:00:20:01",
      "switch": "s1"
    }
  ],
  "links": [
    {"left": "s1", "right": "s2"}
  ]
}
```

- `name` is the Mininet node name.
- `dpid` is optional; Mininet assigns one when omitted.
- `ip` and `switch` are required for hosts; `mac` is optional.
- Host-switch links are created from each host's `switch`.
- `links` are additional direct links, usually switch-to-switch.
- Duplicate links are rejected.

## Run

From this directory:

```bash
sudo python3 start_topo.py \
  --topology example.json \
  --controller-ip 127.0.0.1 \
  --controller-port 6653 \
  --control-host 0.0.0.0 \
  --control-port 9090
```

From the project root:

```bash
sudo python3 topology/start_topo.py \
  --topology topology/example.json \
  --controller-ip 127.0.0.1 \
  --controller-port 6653 \
  --control-host 0.0.0.0 \
  --control-port 9090
```

Options:

- `--clean` runs `mn -c` before starting.
- `--hold N` holds the topology for N seconds instead of the interactive CLI.
- `--control-port 0` disables the control API.
- Stop with Ctrl-C so Mininet can clean its interfaces. If it was killed, use
  `--clean` or `sudo mn -c` before the next run.

If the topology runs in a VM and the MCP server runs outside it, bind the control API to `0.0.0.0` and forward port 9090. The MCP server does not SSH into the VM.

Verify the control API from the MCP host:

```bash
curl http://127.0.0.1:9090/health
```

## Control API

| Method | Path | Meaning |
|---|---|---|
| `GET` | `/health` | Health and host inventory |
| `GET` | `/status` | Hosts, links, and switch names |
| `POST` | `/command` | Run `status`, `ping`, or `link` |

```json
{"command": "ping", "source": "h1", "destination": "h5", "count": 3}
```

```json
{"command": "link", "left": "s1", "right": "s2", "state": "down"}
```

The API has no authentication. Keep it on a trusted network or protect it with a firewall.

## MCP configuration

```bash
export ONOS_URL=http://<onos-host>:8181
export ONOS_CONTROL_URL=http://<topology-host>:9090
```

Automatic names are `h<last IPv4 octet>` for hosts and `s<datapath number>` for
switches. Use MCP aliases if your names differ:

```bash
uv run main.py \
  --host-alias web=10.20.0.5 \
  --switch-alias edge=of:0000000000000003
```

## ONOS discovery

ONOS may not discover hosts until traffic is generated. From the Mininet CLI:

```text
mininet> h1 ping -c 2 10.20.0.5
```

Then call `get_network_context` again. If the ping fails but hosts appear, create an intent with `connect_nodes` or `create_intent` and test again.
