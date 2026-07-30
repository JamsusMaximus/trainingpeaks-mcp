"""MCP Apps wiring (hand-rolled on the low-level Server - see the adoption PRD).

An MCP App is a tool plus a ``ui://`` HTML resource the host renders in a
sandboxed iframe, linked by ``_meta.ui.resourceUri`` on the tool. The SDK's
``Apps`` extension automates this for ``MCPServer`` only, so tp-mcp carries the
small amount of wiring itself:

- ``register_app(tool_name, uri, html_file, title)`` binds a tool to an HTML
  resource shipped as package data in this directory.
- ``stamp_tools(tools)`` writes the ``_meta`` keys onto the bound Tool objects
  (both the nested spec shape and the deprecated flat key pre-GA hosts read).
- ``list_resources()`` / ``read_resource(uri)`` back the server's
  ``resources/list`` / ``resources/read`` handlers.

Security invariant (enforced by tests): app HTML is fully self-contained and
must render ALL API-derived strings via ``textContent`` - workout titles and
coach/athlete comments are user-authored free text and a stored-XSS surface.
"""

from dataclasses import dataclass
from importlib import resources as importlib_resources

from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID
from mcp.types import Tool

__all__ = [
    "APP_MIME_TYPE",
    "EXTENSION_ID",
    "APPS",
    "AppBinding",
    "list_resources",
    "read_resource",
    "register_app",
    "stamp_tools",
]


@dataclass(frozen=True)
class AppBinding:
    tool_name: str
    uri: str
    html_file: str  # filename inside src/tp_mcp/apps/
    title: str


# Populated at import time by the register_app calls at the bottom of this file.
APPS: dict[str, AppBinding] = {}


def register_app(tool_name: str, uri: str, html_file: str, title: str) -> None:
    if not uri.startswith("ui://"):
        raise ValueError(f"App resource URI must be ui://...: {uri!r}")
    APPS[uri] = AppBinding(tool_name=tool_name, uri=uri, html_file=html_file, title=title)


def load_html(html_file: str) -> str:
    """Load an app HTML document shipped as package data (wheel-safe)."""
    return (importlib_resources.files("tp_mcp.apps") / html_file).read_text(encoding="utf-8")


def stamp_tools(tools: list[Tool]) -> None:
    """Write ``_meta.ui.resourceUri`` onto every app-bound tool.

    Emits both the nested spec shape and the deprecated flat
    ``"ui/resourceUri"`` key some pre-GA hosts still read.
    """
    by_tool = {b.tool_name: b for b in APPS.values()}
    for tool in tools:
        binding = by_tool.get(tool.name)
        if binding is None:
            continue
        meta = dict(tool.meta or {})
        meta["ui"] = {**meta.get("ui", {}), "resourceUri": binding.uri}
        meta["ui/resourceUri"] = binding.uri  # deprecated flat key, pre-GA hosts
        tool.meta = meta


def list_resources() -> list[dict]:
    """Resource descriptors for resources/list (dicts keyed for mcp.types.Resource)."""
    return [
        {"uri": b.uri, "name": b.tool_name.removeprefix("tp_"), "title": b.title, "mime_type": APP_MIME_TYPE}
        for b in APPS.values()
    ]


def read_resource(uri: str) -> tuple[str, str] | None:
    """(mime_type, html) for a registered ui:// resource, or None."""
    binding = APPS.get(uri)
    if binding is None:
        return None
    return APP_MIME_TYPE, load_html(binding.html_file)


# ---------------------------------------------------------------------------
# App registrations. Each app PR adds one line plus its .html file.
# ---------------------------------------------------------------------------
register_app("tp_get_fitness", "ui://trainingpeaks/pmc-chart.html", "pmc_chart.html", "Fitness chart (PMC)")
register_app(
    "tp_get_weekly_summary", "ui://trainingpeaks/weekly-summary.html", "weekly_summary.html", "Weekly summary card"
)
