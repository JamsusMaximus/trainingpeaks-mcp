"""TrainingPeaks MCP Server."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tp-mcp")
except PackageNotFoundError:  # source tree without an installed distribution
    __version__ = "unknown"
