"""MCP Apps foundation wiring (PRD PR 4).

The machinery is exercised with a synthetic binding because the first real app
lands in the next PR; the pairing tests then guard every real registration.
"""

import json
from pathlib import Path

import pytest

from tp_mcp import apps
from tp_mcp.server import TOOLS, server

XSS_FIXTURE = Path(__file__).parent / "fixtures" / "xss_strings.json"


@pytest.fixture()
def synthetic_app(monkeypatch):
    binding = apps.AppBinding(
        tool_name="tp_get_fitness", uri="ui://test/app.html", html_file="test.html", title="Test app"
    )
    monkeypatch.setattr(apps, "APPS", {binding.uri: binding})
    monkeypatch.setattr(apps, "load_html", lambda f: "<!doctype html><title>t</title>")
    return binding


class TestRegistry:
    def test_register_rejects_non_ui_uri(self):
        with pytest.raises(ValueError, match="ui://"):
            apps.register_app("tp_get_fitness", "https://evil.example/app.html", "x.html", "X")

    def test_read_resource_serves_app_mime(self, synthetic_app):
        mime, html = apps.read_resource(synthetic_app.uri)
        assert mime == "text/html;profile=mcp-app"
        assert html.startswith("<!doctype html>")

    def test_read_unknown_resource_returns_none(self):
        assert apps.read_resource("ui://nope/app.html") is None


class TestStamping:
    def test_stamp_writes_nested_and_flat_keys(self, synthetic_app):
        tools = [t.model_copy(deep=True) for t in TOOLS]
        apps.stamp_tools(tools)
        fitness = next(t for t in tools if t.name == "tp_get_fitness")
        assert fitness.meta["ui"]["resourceUri"] == synthetic_app.uri
        assert fitness.meta["ui/resourceUri"] == synthetic_app.uri
        untouched = next(t for t in tools if t.name == "tp_get_profile")
        assert not (untouched.meta or {}).get("ui")


class TestServerWiring:
    def test_extension_advertised(self):
        assert apps.EXTENSION_ID in server.extensions

    async def test_resources_list_and_read_through_v2_client(self):
        from mcp import Client

        async with Client(server) as client:
            listed = await client.list_resources()
            listed_uris = {str(r.uri) for r in listed.resources}
            assert listed_uris == set(apps.APPS)  # exactly the registered apps
            for uri in listed_uris:
                read = await client.read_resource(uri)
                assert read.contents[0].mime_type == "text/html;profile=mcp-app"


class TestRealRegistrations:
    """Pairing guards - replicate the startup validation the SDK's Apps
    extension would have given us. Vacuously true until the first app PR."""

    def test_every_binding_targets_a_real_tool(self):
        names = {t.name for t in TOOLS}
        for b in apps.APPS.values():
            assert b.tool_name in names, f"app {b.uri} bound to unknown tool {b.tool_name}"

    def test_every_binding_html_loads_and_is_self_contained(self):
        xss = json.loads(XSS_FIXTURE.read_text())
        for b in apps.APPS.values():
            html = apps.load_html(b.html_file)
            lowered = html.lower()
            assert "<script src=" not in lowered, f"{b.html_file}: external script"
            assert 'href="http' not in lowered, f"{b.html_file}: external stylesheet/link"
            assert ".innerhtml" not in lowered.replace("outerhtml", ""), (
                f"{b.html_file}: innerHTML with API-derived strings is a stored-XSS "
                f"vector (workout titles/comments are user-authored, e.g. {xss['strings'][0]!r}); "
                "use textContent"
            )

    def test_every_stamped_tool_has_a_registered_resource(self):
        for t in TOOLS:
            uri = ((t.meta or {}).get("ui") or {}).get("resourceUri")
            if uri:
                assert uri in apps.APPS, f"{t.name} stamped with unregistered {uri}"
