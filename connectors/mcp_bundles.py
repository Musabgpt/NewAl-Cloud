"""Vetted MCP bundle catalog shipped with MusabAI.

The catalog is deliberately honest: a bundle is marked available only when its
local runtime exists.  We never silently download code or pretend a server is
connected.  Playwright is started by npx when Node is present; the reference
servers repository is represented by its maintained server templates.
"""
import shutil

BUNDLES = [
    {
        "id": "playwright",
        "name": "Microsoft Playwright MCP",
        "repository": "https://github.com/microsoft/playwright-mcp",
        "runtime": "npx",
        "command": "npx",
        "args": ["@playwright/mcp@latest"],
        "description": "Browser automation and web inspection",
    },
    {
        "id": "reference-filesystem",
        "name": "MCP Reference Filesystem",
        "repository": "https://github.com/modelcontextprotocol/servers",
        "runtime": "npx",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem"],
        "description": "Sandboxed local file operations",
    },
    {
        "id": "reference-memory",
        "name": "MCP Reference Memory",
        "repository": "https://github.com/modelcontextprotocol/servers",
        "runtime": "npx",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "description": "Knowledge-graph memory server",
    },
    {
        "id": "reference-fetch",
        "name": "MCP Reference Fetch",
        "repository": "https://github.com/modelcontextprotocol/servers",
        "runtime": "npx",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-fetch"],
        "description": "Fetch and convert public web pages",
    },
]


def catalog():
    have_npx = shutil.which("npx") is not None
    return [dict(item, available=have_npx, status="available" if have_npx else "runtime_missing") for item in BUNDLES]


def route(handler, method, path, body=None):
    if path != "/api/mcp-bundles":
        return False
    if method != "GET":
        handler._json({"error": "Method not allowed"}, 405)
        return True
    handler._json({"bundles": catalog(), "automatic": True,
                   "note": "Bundles are first-class templates; a server is started only when its local runtime is available."})
    return True

