"""MCP Server implementation for TrainingPeaks."""

import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

from tp_mcp.auth import get_credential, validate_auth_sync
from tp_mcp.tools import (
    tp_auth_status,
    tp_get_fitness,
    tp_get_peaks,
    tp_get_profile,
    tp_get_workout,
    tp_get_workout_prs,
    tp_get_workouts,
)

# Configure logging to stderr (stdout is used for MCP protocol)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("tp-mcp")

# Create the MCP server
server = Server("trainingpeaks-mcp")


# Define tools with terse descriptions (under 50 tokens as per PRD)
TOOLS = [
    Tool(
        name="tp_auth_status",
        description="Check auth status. Use when other tools return auth errors.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="tp_get_profile",
        description="Get athlete profile and ID.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="tp_get_workouts",
        description="Get workouts for date range. Returns planned and completed.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD)",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD)",
                },
                "type": {
                    "type": "string",
                    "enum": ["all", "planned", "completed"],
                    "description": "Filter by type",
                    "default": "all",
                },
            },
            "required": ["start_date", "end_date"],
        },
    ),
    Tool(
        name="tp_get_workout",
        description="Get full workout details including metrics.",
        inputSchema={
            "type": "object",
            "properties": {
                "workout_id": {
                    "type": "string",
                    "description": "Workout ID",
                },
            },
            "required": ["workout_id"],
        },
    ),
    Tool(
        name="tp_get_workout_prs",
        description="Get personal records set during a specific workout.",
        inputSchema={
            "type": "object",
            "properties": {
                "workout_id": {
                    "type": "string",
                    "description": "Workout ID to get PRs for",
                },
            },
            "required": ["workout_id"],
        },
    ),
    Tool(
        name="tp_get_peaks",
        description="Get ranked personal records by sport and type.",
        inputSchema={
            "type": "object",
            "properties": {
                "sport": {
                    "type": "string",
                    "enum": ["Bike", "Run"],
                    "description": "Sport type",
                },
                "pr_type": {
                    "type": "string",
                    "description": "PR type: power5sec, power20min, speed5K, etc.",
                },
                "days": {
                    "type": "integer",
                    "description": "Days of history (default 365)",
                    "default": 365,
                },
            },
            "required": ["sport", "pr_type"],
        },
    ),
    Tool(
        name="tp_get_fitness",
        description="Get CTL/ATL/TSB fitness and fatigue data.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Days of history (default 90)",
                    "default": 90,
                },
            },
            "required": [],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool call: {name}")

    try:
        result: dict[str, Any]

        if name == "tp_auth_status":
            result = await tp_auth_status()

        elif name == "tp_get_profile":
            result = await tp_get_profile()

        elif name == "tp_get_workouts":
            result = await tp_get_workouts(
                start_date=arguments["start_date"],
                end_date=arguments["end_date"],
                workout_filter=arguments.get("type", "all"),
            )

        elif name == "tp_get_workout":
            result = await tp_get_workout(
                workout_id=arguments["workout_id"],
            )

        elif name == "tp_get_workout_prs":
            result = await tp_get_workout_prs(
                workout_id=arguments["workout_id"],
            )

        elif name == "tp_get_peaks":
            result = await tp_get_peaks(
                sport=arguments["sport"],
                pr_type=arguments["pr_type"],
                days=arguments.get("days", 365),
            )

        elif name == "tp_get_fitness":
            result = await tp_get_fitness(
                days=arguments.get("days", 90),
            )

        else:
            result = {
                "isError": True,
                "error_code": "UNKNOWN_TOOL",
                "message": f"Unknown tool: {name}",
            }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        logger.exception(f"Error in tool {name}")
        error_result = {
            "isError": True,
            "error_code": "API_ERROR",
            "message": str(e),
        }
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]


def _validate_auth_on_startup() -> bool:
    """Validate authentication on server startup.

    Returns:
        True if auth is valid, False otherwise.
    """
    cred = get_credential()
    if not cred.success or not cred.cookie:
        logger.warning("No credential stored. Run 'tp-mcp auth' to authenticate.")
        return False

    result = validate_auth_sync(cred.cookie)
    if result.is_valid:
        logger.info(f"Authenticated as {result.email} (athlete_id: {result.athlete_id})")
        return True
    else:
        logger.warning(f"Authentication invalid: {result.message}")
        return False


async def run_server_async() -> None:
    """Run the MCP server (async)."""
    logger.info("Starting TrainingPeaks MCP Server")

    # Validate auth on startup (warning only, don't block)
    _validate_auth_on_startup()

    # Run the server with stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run_server() -> int:
    """Run the MCP server (entry point).

    Returns:
        Exit code.
    """
    try:
        asyncio.run(run_server_async())
        return 0
    except KeyboardInterrupt:
        logger.info("Server stopped")
        return 0
    except Exception as e:
        logger.exception(f"Server error: {e}")
        return 1
