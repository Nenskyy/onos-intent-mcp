#!/usr/bin/env python3
"""Load and validate a generic Mininet topology description."""

import json
import re

NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
DPID_RE = re.compile(r"^(?:0x)?([0-9a-fA-F]{1,16})$")


class TopologyError(Exception):
    """Raised when a topology file is missing or invalid."""


def _require_name(entry, kind, index):
    name = str(entry.get("name") or "").strip()
    if not name:
        raise TopologyError("%s %d has no name" % (kind, index))
    if not NAME_RE.match(name):
        raise TopologyError("invalid %s name %r" % (kind, name))
    return name


def _normalize_dpid(value):
    if value is None:
        return None
    if isinstance(value, int):
        if value < 0:
            raise TopologyError("dpid must not be negative")
        return "%016x" % value
    text = str(value).strip()
    match = DPID_RE.match(text)
    if not match:
        raise TopologyError("invalid dpid %r" % value)
    return match.group(1).zfill(16)


def _normalize_link(entry, index):
    if not isinstance(entry, dict):
        raise TopologyError("link %d must be an object" % index)
    left = str(entry.get("left") or entry.get("one") or "").strip()
    right = str(entry.get("right") or entry.get("two") or "").strip()
    if not left or not right:
        raise TopologyError("link %d needs left and right" % index)
    if left == right:
        raise TopologyError("link %d connects %s to itself" % (index, left))
    return left, right


def load_topology(path):
    """Read a JSON topology and return normalized switches, hosts, and links."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as error:
        raise TopologyError("cannot read topology %s: %s" % (path, error))
    except ValueError as error:
        raise TopologyError("invalid JSON in %s: %s" % (path, error))
    if not isinstance(data, dict):
        raise TopologyError("topology root must be an object")

    switches = []
    node_names = set()
    for index, entry in enumerate(data.get("switches") or [], 1):
        if not isinstance(entry, dict):
            raise TopologyError("switch %d must be an object" % index)
        name = _require_name(entry, "switch", index)
        if name in node_names:
            raise TopologyError("duplicate node name %r" % name)
        node_names.add(name)
        switches.append(
            {
                "name": name,
                "dpid": _normalize_dpid(entry.get("dpid")),
            }
        )
    if not switches:
        raise TopologyError("topology needs at least one switch")

    hosts = []
    host_links = []
    switch_names = {switch["name"] for switch in switches}
    for index, entry in enumerate(data.get("hosts") or [], 1):
        if not isinstance(entry, dict):
            raise TopologyError("host %d must be an object" % index)
        name = _require_name(entry, "host", index)
        if name in node_names:
            raise TopologyError("duplicate node name %r" % name)
        node_names.add(name)
        ip = str(entry.get("ip") or "").strip()
        if not ip:
            raise TopologyError("host %s has no ip" % name)
        switch = str(entry.get("switch") or "").strip()
        if switch not in switch_names:
            raise TopologyError(
                "host %s references unknown switch %r" % (name, switch)
            )
        mac = entry.get("mac")
        hosts.append(
            {
                "name": name,
                "ip": ip,
                "mac": str(mac).strip() if mac else None,
                "switch": switch,
            }
        )
        host_links.append((name, switch))
    if not hosts:
        raise TopologyError("topology needs at least one host")

    links = []
    seen = set()
    for pair in host_links:
        key = tuple(sorted(pair))
        seen.add(key)
        links.append({"left": pair[0], "right": pair[1]})

    for index, entry in enumerate(data.get("links") or [], 1):
        left, right = _normalize_link(entry, index)
        for name in (left, right):
            if name not in node_names:
                raise TopologyError("link %d references unknown node %r" % (index, name))
        key = tuple(sorted((left, right)))
        if key in seen:
            raise TopologyError("duplicate link %s-%s" % (left, right))
        seen.add(key)
        links.append({"left": left, "right": right})

    return {"switches": switches, "hosts": hosts, "links": links}
