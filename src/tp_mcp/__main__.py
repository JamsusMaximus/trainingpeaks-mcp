"""CLI entry point for TrainingPeaks MCP Server."""

import sys


def main() -> int:
    """Main entry point."""
    print("TrainingPeaks MCP Server")
    print("Commands: auth, serve")
    print("Use 'tp-mcp auth' to authenticate")
    print("Use 'tp-mcp serve' to start the MCP server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
