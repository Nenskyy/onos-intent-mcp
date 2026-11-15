#!/usr/bin/env python3
"""Tests for the Streamable HTTP transport."""

import asyncio
import unittest

import httpx2

from tests.test_mcp_server import make_server

try:
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    from onos_mcp.server import build_http_app
except ImportError:
    Client = None
    streamable_http_client = None
    build_http_app = None


@unittest.skipUnless(Client, "mcp SDK is not installed")
class HttpTransportTests(unittest.TestCase):
    def test_health(self):
        async def exercise():
            app = build_http_app(make_server(), host="127.0.0.1")
            transport = httpx2.ASGITransport(app=app)
            async with httpx2.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                return await client.get("/health")

        response = asyncio.run(exercise())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["mcp_path"], "/mcp")

    def test_cors_preflight(self):
        async def exercise():
            app = build_http_app(make_server(), host="0.0.0.0")
            transport = httpx2.ASGITransport(app=app)
            async with httpx2.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                return await client.options(
                    "/mcp",
                    headers={
                        "Origin": "http://llama.example:8080",
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )

        response = asyncio.run(exercise())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "*")
        self.assertIn("POST", response.headers["access-control-allow-methods"])

    def test_mcp_over_streamable_http(self):
        async def exercise():
            app = build_http_app(make_server(), host="127.0.0.1")
            async with app.router.lifespan_context(app):
                transport = httpx2.ASGITransport(app=app)
                async with httpx2.AsyncClient(
                    transport=transport,
                    base_url="http://127.0.0.1:8000",
                    headers={"Origin": "http://llama.example:8080"},
                ) as http_client:
                    async with Client(
                        streamable_http_client(
                            "http://127.0.0.1:8000/mcp",
                            http_client=http_client,
                        )
                    ) as client:
                        tools = await client.list_tools()
                        context = await client.call_tool(
                            "get_network_context", {}
                        )
                        return tools, context

        tools, context = asyncio.run(exercise())
        names = [tool.name for tool in tools.tools]
        self.assertIn("get_network_context", names)
        self.assertFalse(context.is_error)
        self.assertTrue(context.content[0].text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
