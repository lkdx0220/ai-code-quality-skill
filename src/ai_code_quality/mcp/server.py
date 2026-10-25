"""Optional SDK transport. All execution policy lives below this boundary."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .. import __version__
from ..redact import redact_text
from .contracts import DESCRIPTIONS, SCHEMAS, ServiceError, encode
from .service import Service
from .settings import Settings


async def serve(settings):
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations

    service = Service(settings)

    async def list_tools(ctx, params):
        return ListToolsResult(
            tools=[
                Tool(
                    name=name,
                    description=DESCRIPTIONS[name],
                    input_schema=spec,
                    annotations=ToolAnnotations(
                        read_only_hint=False,
                        destructive_hint=False,
                        idempotent_hint=False,
                        open_world_hint=False,
                    ),
                )
                for name, spec in SCHEMAS.items()
            ]
        )

    async def call_tool(ctx, params):
        result = await service.call(
            params.name, params.arguments if params.arguments is not None else {}
        )
        return CallToolResult(
            content=[TextContent(type="text", text=encode(result))],
            structured_content=result,
            is_error=not result["ok"],
        )

    server = Server("cq-mcp", version=__version__, on_list_tools=list_tools, on_call_tool=call_tool)
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        await service.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="cq-mcp", description="Local stdio quality tools for a trusted project"
    )
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--tool-python")
    parser.add_argument("--allow-test-execution", action="store_true")
    parser.add_argument("--max-scan-seconds", type=int, default=3600)
    parser.add_argument("--inputs-timeout-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        import mcp  # noqa: F401 - check optional dependency before opening a service

        if sys.platform == "win32":
            import win32job  # noqa: F401 - required direct platform dependency
        settings = Settings(
            args.project,
            args.state_dir,
            tool_python=args.tool_python,
            allow_test_execution=args.allow_test_execution,
            max_scan_seconds=args.max_scan_seconds,
            inputs_timeout_seconds=args.inputs_timeout_seconds,
        )
        asyncio.run(serve(settings))
    except ModuleNotFoundError:
        print(
            'cq-mcp requires the optional extra: install "ai-code-quality[mcp]" in the server environment.',
            file=sys.stderr,
        )
        return 2
    except (ServiceError, OSError) as exc:
        print(redact_text(str(exc)), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0
