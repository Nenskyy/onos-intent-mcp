#!/usr/bin/env python3
"""Tests for the generic topology config loader."""

import json
import tempfile
import unittest
from pathlib import Path

from topology.config import TopologyError, load_topology


class TopologyConfigTests(unittest.TestCase):
    def test_example_and_validation(self):
        root = Path(__file__).resolve().parents[1]
        config = load_topology(root / "topology" / "example.json")
        self.assertEqual(len(config["switches"]), 3)
        self.assertEqual(len(config["hosts"]), 5)
        self.assertEqual(len(config["links"]), 8)
        self.assertTrue(all(host["mac"] for host in config["hosts"]))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "switches": [{"name": "s1"}],
                        "hosts": [
                            {
                                "name": "h1",
                                "ip": "10.0.0.1/24",
                                "switch": "missing",
                            }
                        ],
                        "links": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(TopologyError):
                load_topology(path)

            path.write_text(
                json.dumps(
                    {
                        "switches": [{"name": "s1"}],
                        "hosts": [
                            {
                                "name": "h1",
                                "ip": "10.0.0.1/24",
                                "switch": "s1",
                            }
                        ],
                        "links": [{"left": "s1", "right": "h1"}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(TopologyError):
                load_topology(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
