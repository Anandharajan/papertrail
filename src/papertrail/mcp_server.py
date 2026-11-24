"""MCP tool layer (stdio only). A thin wrapper over papertrail.api.

Tool descriptions are the static docstrings of the functions in api.TOOLS
(versioned with the package) to guard against tool poisoning.
"""
from __future__ import annotations

import functools
from typing import Any
from collections.abc import Callable

from . import api
from .audit import log_call


def audited(fn: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            out = fn(*args, **kwargs)
        except Exception:
            log_call(fn.__name__, kwargs, ok=False)
            raise
        log_call(fn.__name__, kwargs, ok=True)
        return out
    return wrapper


def build_server() -> Any:
    try:  # MCP Python SDK 2.x
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:
        try:  # MCP Python SDK 1.x
            from mcp.server.fastmcp import FastMCP as Server
        except ImportError as e:  # pragma: no cover
            raise SystemExit("Install the MCP extra: pip install 'papertrail[mcp]'") from e
    server = Server("PaperTrail")
    for fn in api.TOOLS:
        server.tool()(audited(fn))
    return server


def main() -> None:  # pragma: no cover
    build_server().run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
