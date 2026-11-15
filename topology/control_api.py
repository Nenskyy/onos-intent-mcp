#!/usr/bin/env python3
"""Small topology control API for the generic Mininet launcher."""

import json
import logging
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
CONTROL_LOCK = threading.Lock()
LOG = logging.getLogger("topology-control")


class ControlError(Exception):
    """Raised for invalid control requests."""


def _link_status(net, left, right):
    wanted = {left, right}
    for link in net.links:
        names = {link.intf1.node.name, link.intf2.node.name}
        if names == wanted:
            return "up" if link.intf1.isUp() and link.intf2.isUp() else "down"
    return "unknown"


class NetworkControl:
    """Execute ping and link commands against a running Mininet network."""

    def __init__(self, net, switches, hosts):
        self.net = net
        self.switches = switches
        self.hosts = hosts
        self.links = []
        self.host_switches = {}
        seen = set()
        for link in net.links:
            left = link.intf1.node.name
            right = link.intf2.node.name
            key = tuple(sorted((left, right)))
            if key not in seen:
                seen.add(key)
                self.links.append(key)
            if left in hosts and right in switches:
                self.host_switches[left] = right
            elif right in hosts and left in switches:
                self.host_switches[right] = left

    def status(self):
        host_rows = {}
        for name, host in self.hosts.items():
            host_rows[name] = {
                "ip": host.IP(),
                "mac": host.MAC(),
                "switch": self.host_switches.get(name),
            }
        link_rows = [
            {
                "link": "%s-%s" % (left, right),
                "status": _link_status(self.net, left, right),
            }
            for left, right in sorted(self.links)
        ]
        return {
            "ok": True,
            "hosts": host_rows,
            "links": link_rows,
            "switches": sorted(self.switches),
        }

    def ping(self, source, destination, count=3):
        if source not in self.hosts:
            raise ControlError("unknown source host %r" % source)
        try:
            count = int(count)
        except (TypeError, ValueError):
            raise ControlError("ping count must be an integer")
        if not 1 <= count <= 10:
            raise ControlError("ping count must be between 1 and 10")

        if destination in self.hosts:
            target = self.hosts[destination].IP()
        elif IP_RE.match(str(destination)):
            target = str(destination)
        else:
            raise ControlError("unknown destination %r" % destination)

        command = "ping -c %d -W 2 %s" % (count, target)
        output = self.hosts[source].cmd(command)
        match = re.search(r"(\d+)% packet loss", output)
        loss = int(match.group(1)) if match else None
        return {
            "ok": loss == 0,
            "source": source,
            "destination": destination,
            "target": target,
            "count": count,
            "loss_percent": loss,
            "output": output,
        }

    def set_link(self, left, right, state):
        state = str(state).lower()
        if state not in ("up", "down"):
            raise ControlError("link state must be 'up' or 'down'")
        if tuple(sorted((left, right))) not in {tuple(sorted(p)) for p in self.links}:
            raise ControlError("unknown link %s-%s" % (left, right))
        with CONTROL_LOCK:
            self.net.configLinkStatus(left, right, state)
            time.sleep(0.5)
            status = _link_status(self.net, left, right)
        return {
            "ok": True,
            "link": "%s-%s" % (left, right),
            "state": state,
            "status": status,
        }

    def handle(self, request):
        command = request.get("command")
        if command == "status":
            return self.status()
        if command == "ping":
            return self.ping(
                request.get("source"),
                request.get("destination"),
                request.get("count", 3),
            )
        if command == "link":
            return self.set_link(
                request.get("left"),
                request.get("right"),
                request.get("state"),
            )
        raise ControlError("unknown control command %r" % command)


class ControlHandler(BaseHTTPRequestHandler):
    server_version = "TopologyControl/1.0"

    def _send_json(self, status, payload):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/", "/health", "/status"):
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            self._send_json(200, self.server.control.status())
        except Exception as error:
            self._send_json(500, {"ok": False, "error": str(error)})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/command":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, dict):
                raise ControlError("request must be a JSON object")
            self._send_json(200, self.server.control.handle(request))
        except (ControlError, ValueError) as error:
            self._send_json(400, {"ok": False, "error": str(error)})
        except Exception as error:
            self._send_json(500, {"ok": False, "error": str(error)})

    def log_message(self, fmt, *args):
        LOG.info(fmt, *args)


def start_control_server(control, host, port):
    server = ThreadingHTTPServer((host, port), ControlHandler)
    server.daemon_threads = True
    server.control = control
    thread = threading.Thread(
        target=server.serve_forever,
        name="topology-control",
        daemon=True,
    )
    thread.start()
    return server
