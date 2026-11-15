#!/usr/bin/env python3
"""Start a Mininet topology from JSON and connect it to ONOS.

Run from this directory with Mininet installed:

    sudo python3 start_topo.py \
      --topology example.json \
      --controller-ip 127.0.0.1 \
      --control-host 0.0.0.0 \
      --control-port 9090

From the project root, use:

    sudo python3 topology/start_topo.py \
      --topology topology/example.json \
      --controller-ip 127.0.0.1 \
      --control-host 0.0.0.0 \
      --control-port 9090

The control API is optional but is required by the MCP ping and link tools.
"""

import argparse
import subprocess
import sys
import time

try:
    from topology.config import TopologyError, load_topology
    from topology.control_api import NetworkControl, start_control_server
except ImportError:
    from config import TopologyError, load_topology
    from control_api import NetworkControl, start_control_server


def build_net(config, controller_ip, controller_port):
    from mininet.net import Mininet
    from mininet.node import OVSKernelSwitch, RemoteController

    net = Mininet(
        controller=RemoteController,
        switch=OVSKernelSwitch,
        autoSetMacs=True,
        autoStaticArp=False,
    )
    controller = net.addController(
        "c0",
        ip=controller_ip,
        port=controller_port,
    )

    switches = {}
    for entry in config["switches"]:
        kwargs = {"protocols": "OpenFlow13"}
        if entry.get("dpid"):
            kwargs["dpid"] = entry["dpid"]
        switches[entry["name"]] = net.addSwitch(entry["name"], **kwargs)

    hosts = {}
    for entry in config["hosts"]:
        kwargs = {"ip": entry["ip"], "defaultRoute": None}
        if entry.get("mac"):
            kwargs["mac"] = entry["mac"]
        hosts[entry["name"]] = net.addHost(entry["name"], **kwargs)

    nodes = dict(switches)
    nodes.update(hosts)
    for entry in config["links"]:
        net.addLink(nodes[entry["left"]], nodes[entry["right"]])

    return net, controller, switches, hosts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--topology",
        required=True,
        help="path to the JSON topology file",
    )
    parser.add_argument("--controller-ip", default="127.0.0.1")
    parser.add_argument("--controller-port", type=int, default=6653)
    parser.add_argument(
        "--control-host",
        default="127.0.0.1",
        help="bind address for the control API",
    )
    parser.add_argument(
        "--control-port",
        type=int,
        default=9090,
        help="control API port; 0 disables it",
    )
    parser.add_argument(
        "--hold",
        type=int,
        default=0,
        help="keep the topology alive for N seconds instead of opening the CLI",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="run 'mn -c' before starting to remove stale Mininet state",
    )
    args = parser.parse_args()

    try:
        from mininet.cli import CLI
        from mininet.log import info, setLogLevel
    except ImportError as error:
        print(
            "ERROR: Mininet is required to run this launcher: %s" % error,
            file=sys.stderr,
        )
        return 2

    if args.clean:
        info("*** cleaning stale Mininet state\n")
        subprocess.run(["mn", "-c"], check=False)

    try:
        config = load_topology(args.topology)
    except TopologyError as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 2

    setLogLevel("info")
    net, _controller, switches, hosts = build_net(
        config,
        args.controller_ip,
        args.controller_port,
    )
    net.start()

    control_server = None
    if args.control_port:
        control = NetworkControl(net, switches, hosts)
        control_server = start_control_server(
            control,
            args.control_host,
            args.control_port,
        )
        info(
            "*** control API: http://%s:%d\n"
            % (args.control_host, args.control_port)
        )

    info("*** topology ready: %d switches, %d hosts, %d links\n" % (
        len(switches),
        len(hosts),
        len(config["links"]),
    ))
    for name, host in hosts.items():
        info("*** %s ip=%s mac=%s\n" % (name, host.IP(), host.MAC()))
    for entry in config["links"]:
        info("*** link %s-%s\n" % (entry["left"], entry["right"]))

    try:
        if args.hold:
            info("*** holding topology for %s seconds\n" % args.hold)
            time.sleep(args.hold)
        else:
            CLI(net)
    finally:
        if control_server is not None:
            control_server.shutdown()
            control_server.server_close()
        net.stop()


if __name__ == "__main__":
    sys.exit(main())
