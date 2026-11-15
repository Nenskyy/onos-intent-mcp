#!/usr/bin/env python3
"""Automated tests for the ONOS intent translation and conflict layer.

Run offline:
    uv run python -m unittest -v tests.test_intent_tools

Add a live ONOS smoke test:
    ONOS_LIVE=1 uv run python -m unittest -v tests.test_intent_tools
"""

import json
import os
import tempfile
import time
import unittest
from unittest import mock

from onos_mcp.intent_core import (
    ConflictError,
    IntentManager,
    NodeResolver,
    OnosError,
    OnosClient,
    detect_conflicts,
    host_to_host_payload,
    intent_endpoints,
    load_env_file,
    parse_aliases,
    parse_command,
)

HOSTS = [
    {"id": "00:00:00:00:00:01/None", "mac": "00:00:00:00:00:01",
     "ipAddresses": ["10.0.4.1"], "locations": []},
    {"id": "00:00:00:00:00:02/None", "mac": "00:00:00:00:00:02",
     "ipAddresses": ["10.0.4.2"], "locations": []},
    {"id": "00:00:00:00:00:03/None", "mac": "00:00:00:00:00:03",
     "ipAddresses": ["10.0.4.3"], "locations": []},
    {"id": "00:00:00:00:00:04/None", "mac": "00:00:00:00:00:04",
     "ipAddresses": ["10.0.4.4"], "locations": []},
]


class FakeClient:
    def __init__(self, hosts=None, intents=None):
        self._hosts = hosts if hosts is not None else [dict(h) for h in HOSTS]
        self._intents = list(intents or [])
        self.created = []
        self.deleted = []
        self._next = 1

    def hosts(self):
        return self._hosts

    def intents(self):
        return self._intents

    def host_by_ip(self, ip):
        for host in self._hosts:
            if ip in (host.get("ipAddresses") or []):
                return host
        return None

    def host_by_id(self, host_id):
        for host in self._hosts:
            if host.get("id") == host_id:
                return host
        return None

    def resolve_host(self, name, host_ips=None):
        return OnosClient.resolve_host(self, name, host_ips)

    def create_intent(self, payload):
        self.created.append(payload)
        ident = "0x%04x" % self._next
        self._next += 1
        intent = dict(payload)
        intent.update({"id": ident, "state": "INSTALLED"})
        self._intents.append(intent)
        return 201, {"Location": "/onos/v1/intents/%s/%s" % (payload["appId"], ident)}, intent, json.dumps(intent)

    def delete_intent(self, app_id, intent_id):
        self.deleted.append((app_id, intent_id))
        self._intents = [
            intent for intent in self._intents
            if not (intent.get("id") == intent_id and intent.get("appId") == app_id)
        ]
        return 204, {}, "", "/onos/v1/intents/%s/%s" % (app_id, intent_id)


class ParserTests(unittest.TestCase):
    def test_connect_to(self):
        self.assertEqual(
            parse_command("connect h1 to h2"),
            {"action": "connect", "src": "h1", "dst": "h2"},
        )

    def test_connect_spaces_and_case(self):
        self.assertEqual(
            parse_command("  CONNECT   h3    h4  "),
            {"action": "connect", "src": "h3", "dst": "h4"},
        )

    def test_disconnect(self):
        self.assertEqual(
            parse_command("disconnect h1 from h2"),
            {"action": "disconnect", "src": "h1", "dst": "h2"},
        )

    def test_self_connect_rejected(self):
        with self.assertRaises(OnosError):
            parse_command("connect h1 to h1")

    def test_unknown_command_rejected(self):
        with self.assertRaises(OnosError):
            parse_command("please make h1 talk to h2")


class ConflictTests(unittest.TestCase):
    def test_duplicate_is_order_insensitive(self):
        intents = [
            {
                "type": "HostToHostIntent",
                "id": "0x1",
                "appId": "test",
                "state": "INSTALLED",
                "one": "A",
                "two": "B",
            }
        ]
        conflicts = detect_conflicts("B", "A", intents)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["kind"], "duplicate")

    def test_shared_endpoint_is_overlap(self):
        intents = [
            {
                "type": "HostToHostIntent",
                "id": "0x1",
                "appId": "test",
                "state": "INSTALLED",
                "one": "A",
                "two": "B",
            }
        ]
        conflicts = detect_conflicts("A", "C", intents)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["kind"], "overlap")

    def test_disjoint_is_not_conflict(self):
        intents = [
            {
                "type": "HostToHostIntent",
                "id": "0x1",
                "appId": "test",
                "state": "INSTALLED",
                "one": "A",
                "two": "B",
            }
        ]
        self.assertEqual(detect_conflicts("C", "D", intents), [])

    def test_withdrawn_intent_is_ignored(self):
        intents = [
            {
                "type": "HostToHostIntent",
                "id": "0x1",
                "appId": "test",
                "state": "WITHDRAWN",
                "one": "A",
                "two": "B",
            }
        ]
        self.assertEqual(detect_conflicts("A", "B", intents), [])


class ManagerTests(unittest.TestCase):
    def test_translate_builds_host_to_host_payload(self):
        manager = IntentManager(client=FakeClient(), app_id="org.test")
        result = manager.translate("connect h1 to h2")
        self.assertEqual(result["one"], "00:00:00:00:00:01/None")
        self.assertEqual(result["two"], "00:00:00:00:00:02/None")
        self.assertEqual(
            result["payload"],
            host_to_host_payload(
                "00:00:00:00:00:01/None", "00:00:00:00:00:02/None", "org.test"
            ),
        )

    def test_dry_run_does_not_submit(self):
        client = FakeClient()
        manager = IntentManager(client=client)
        result = manager.submit("connect h1 to h2", dry_run=True)
        self.assertTrue(result["dryRun"])
        self.assertEqual(client.created, [])

    def test_duplicate_submit_rejected(self):
        client = FakeClient()
        manager = IntentManager(client=client)
        manager.submit("connect h1 to h2")
        with self.assertRaises(ConflictError) as raised:
            manager.submit("connect h2 to h1")
        self.assertEqual(raised.exception.conflicts[0]["kind"], "duplicate")

    def test_overlap_requires_force(self):
        client = FakeClient()
        manager = IntentManager(client=client)
        manager.submit("connect h1 to h2")
        with self.assertRaises(ConflictError):
            manager.submit("connect h1 to h3")
        result = manager.submit("connect h1 to h3", force=True)
        self.assertTrue(result["forced"])
        self.assertEqual(len(client.created), 2)

    def test_disconnect_removes_matching_intent(self):
        client = FakeClient()
        manager = IntentManager(client=client)
        manager.submit("connect h1 to h2")
        result = manager.disconnect("disconnect h2 from h1")
        self.assertEqual(len(result["deleted"]), 1)
        self.assertEqual(client.intents(), [])


GENERIC_HOSTS = [
    {
        "id": "00:00:00:00:00:01/None",
        "mac": "00:00:00:00:00:01",
        "ipAddresses": ["10.10.0.1"],
        "locations": [],
    },
    {
        "id": "00:00:00:00:00:05/None",
        "mac": "00:00:00:00:00:05",
        "ipAddresses": ["10.10.0.5"],
        "locations": [],
    },
    {
        "id": "00:00:00:00:00:50/None",
        "mac": "aa:bb:cc:dd:ee:50",
        "ipAddresses": ["10.10.0.50"],
        "locations": [],
    },
]

GENERIC_DEVICES = [
    {"id": "of:0000000000000001", "available": True, "type": "SWITCH"},
    {"id": "of:0000000000000005", "available": True, "type": "SWITCH"},
]


class EnvFileTests(unittest.TestCase):
    def test_load_env_file_preserves_existing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, ".env")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "ONOS_URL=http://onos:8181\n"
                    "export ONOS_USER='alice'\n"
                    'ONOS_PASSWORD="secret"\n'
                    "# ignored\n"
                )
            with mock.patch.dict(
                os.environ, {"ONOS_USER": "real"}, clear=True
            ):
                load_env_file(path)
                self.assertEqual(os.environ["ONOS_URL"], "http://onos:8181")
                self.assertEqual(os.environ["ONOS_USER"], "real")
                self.assertEqual(os.environ["ONOS_PASSWORD"], "secret")


class GenericResolverTests(unittest.TestCase):
    def test_auto_host_and_switch_names(self):
        resolver = NodeResolver(GENERIC_HOSTS, GENERIC_DEVICES)
        host, name = resolver.resolve_host("h5")
        self.assertEqual(name, "h5")
        self.assertEqual(host["ipAddresses"], ["10.10.0.5"])
        device, name = resolver.resolve_switch("s5")
        self.assertEqual(name, "s5")
        self.assertEqual(device["id"], "of:0000000000000005")

    def test_resolve_by_ip_mac_and_id(self):
        resolver = NodeResolver(GENERIC_HOSTS, GENERIC_DEVICES)
        self.assertEqual(resolver.resolve_host("10.10.0.5")[1], "h5")
        self.assertEqual(
            resolver.resolve_host("aa:bb:cc:dd:ee:50")[1], "h50"
        )
        self.assertEqual(
            resolver.resolve_host("00:00:00:00:00:05/None")[1], "h5"
        )

    def test_explicit_aliases(self):
        resolver = NodeResolver(
            GENERIC_HOSTS,
            GENERIC_DEVICES,
            host_aliases={"web": "10.10.0.50"},
            switch_aliases={"edge": "of:0000000000000005"},
        )
        self.assertEqual(resolver.resolve_host("web")[1], "web")
        self.assertEqual(resolver.resolve_switch("edge")[1], "edge")

    def test_unknown_names_are_reported(self):
        resolver = NodeResolver(GENERIC_HOSTS, GENERIC_DEVICES)
        with self.assertRaises(OnosError):
            resolver.resolve_node("h99")

    def test_parse_aliases(self):
        self.assertEqual(
            parse_aliases("h5=10.0.0.5; edge=of:1"),
            {"h5": "10.0.0.5", "edge": "of:1"},
        )

    def test_translate_connect_h1_to_h5(self):
        manager = IntentManager(client=FakeClient(hosts=GENERIC_HOSTS))
        result = manager.translate("connect h1 to h5")
        self.assertEqual(result["oneName"], "h1")
        self.assertEqual(result["twoName"], "h5")
        self.assertEqual(
            result["one"], "00:00:00:00:00:01/None"
        )
        self.assertEqual(
            result["two"], "00:00:00:00:00:05/None"
        )


class LiveSmokeTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("ONOS_LIVE") == "1", "set ONOS_LIVE=1 to test a live ONOS"
    )
    def test_live_hosts_and_intent_roundtrip(self):
        manager = IntentManager(client=OnosClient())
        hosts = manager.client.hosts()
        self.assertGreaterEqual(len(hosts), 4)
        text = "connect h3 to h4"
        try:
            manager.submit(text)
        except ConflictError:
            manager.disconnect("disconnect h3 from h4")
            manager.submit(text)
        wanted = {"00:00:00:00:00:03/None", "00:00:00:00:00:04/None"}
        found = False
        deadline = time.time() + 20
        rows = []
        while time.time() < deadline:
            rows = manager.list_intents()
            if any(set(intent_endpoints(row)) == wanted for row in rows):
                found = True
                break
            time.sleep(1)
        self.assertTrue(found, "intent not visible; rows=%r" % (rows,))
        manager.disconnect("disconnect h3 from h4")


if __name__ == "__main__":
    unittest.main(verbosity=2)
