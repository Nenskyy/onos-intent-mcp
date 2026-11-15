#!/usr/bin/env python3
"""Python 3.8 fallback entrypoint for the dependency-free MCP server.

Run from the project root:
    PYTHONPATH=src python3 -m onos_mcp.stdlib_server --selftest
"""

from .core import main

if __name__ == "__main__":
    raise SystemExit(main())
