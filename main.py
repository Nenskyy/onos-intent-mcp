#!/usr/bin/env python3
"""Launch the ONOS MCP server over stdio or Streamable HTTP.

Run with uv:
    uv run main.py --selftest
    uv run main.py --control-url http://127.0.0.1:9090
    uv run main.py --http --http-host 127.0.0.1 \
        --control-url http://127.0.0.1:9090
"""

from onos_mcp.server import main

if __name__ == "__main__":
    raise SystemExit(main())
