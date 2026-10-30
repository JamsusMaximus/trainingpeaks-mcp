"""Tests for tp_delete_library_item / tp_copy_library_item (strength + endurance backends)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.library import tp_copy_library_item, tp_delete_library_item

STRENGTH_ITEMS = [{"id": 111, "title": "Upper", "workout": {}}]
ENDURANCE_ITEMS = [{"exerciseLibraryItemId": 222, "itemName": "Ride", "workoutTypeId": 2, "tssPlanned": 50}]


def _client(get_data=None):
    c = AsyncMock()
    c.ensure_athlete_id = AsyncMock(return_value=1)
    c.get = AsyncMock(return_value=APIResponse(success=True, data=get_data if get_data is not None else []))
    c.delete = AsyncMock(return_value=APIResponse(success=True, data=None))
    c.post = AsyncMock(return_value=APIResponse(success=True, data={"exerciseLibraryItemId": 999}))
    return c


def _http(status=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = ""
    http = AsyncMock()
    http.delete.return_value = resp
    http.post.return_value = resp
    return http


def _ctx(obj):
    return MagicMock(__aenter__=AsyncMock(return_value=obj), __aexit__=AsyncMock())


def _env(client, http, strength_items):
    return (
        patch("tp_mcp.tools.library.TPClient", return_value=_ctx(client)),
        patch("tp_mcp.tools.library._fetch_templates", AsyncMock(return_value=(strength_items, None))),
        patch("tp_mcp.tools.library._access", AsyncMock(return_value=(1, "tok", None))),
        patch("tp_mcp.tools.library.httpx.AsyncClient", return_value=_ctx(http)),
    )


async def _call(fn, client, http, strength_items, *a, **k):
    p1, p2, p3, p4 = _env(client, http, strength_items)
    with p1, p2, p3, p4:
        return await fn(*a, **k)


@pytest.mark.asyncio
async def test_delete_strength_uses_peaksware():
    c, h = _client(), _http()
    r = await _call(tp_delete_library_item, c, h, STRENGTH_ITEMS, "5", "111")
    assert r == {"deleted": True, "item_id": "111", "library_id": "5", "kind": "strength"}
    assert h.delete.call_args.args[0].endswith("/libraryContent/workoutLibrary/items/111")
    c.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_endurance_uses_tpapi_v1():
    c, h = _client(), _http()
    c.get.return_value = APIResponse(success=True, data=ENDURANCE_ITEMS)
    r = await _call(tp_delete_library_item, c, h, [], "5", "222")
    assert r["kind"] == "endurance"
    c.delete.assert_awaited_once_with("/exerciselibrary/v1/libraries/5/items/222")
    h.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_validation():
    assert (await tp_delete_library_item("x", "1"))["error_code"] == "VALIDATION_ERROR"
    assert (await tp_delete_library_item("5", ""))["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_delete_strength_api_error():
    c, h = _client(), _http(status=403)
    r = await _call(tp_delete_library_item, c, h, STRENGTH_ITEMS, "5", "111")
    assert r["error_code"] == "AUTH_INVALID"


@pytest.mark.asyncio
async def test_copy_strength_to_other_library():
    c, h = _client(), _http(json_data={"data": {"id": 333}})
    r = await _call(tp_copy_library_item, c, h, STRENGTH_ITEMS, "5", "111", target_library_id="9")
    assert r == {"item_id": "333", "library_id": "9", "title": "Upper Copy", "kind": "strength"}
    assert h.post.call_args.args[0].endswith("/libraryContent/workoutLibrary/items/copy")
    assert h.post.call_args.kwargs["json"] == {"libraryId": 9, "workoutLibraryItemId": 111, "title": "Upper Copy"}


@pytest.mark.asyncio
async def test_copy_endurance_creates_in_target():
    c, h = _client(get_data=ENDURANCE_ITEMS), _http()
    r = await _call(tp_copy_library_item, c, h, [], "5", "222", title="Ride 2", target_library_id="9")
    assert r == {"item_id": "999", "library_id": "9", "title": "Ride 2", "kind": "endurance"}
    endpoint = c.post.call_args.args[0]
    body = c.post.call_args.kwargs["json"]
    assert endpoint == "/exerciselibrary/v1/libraries/9/items"
    assert body["itemName"] == "Ride 2" and body["exerciseLibraryId"] == 9 and body["tssPlanned"] == 50
    assert "exerciseLibraryItemId" not in body


@pytest.mark.asyncio
async def test_copy_endurance_not_found():
    c, h = _client(get_data=ENDURANCE_ITEMS), _http()
    r = await _call(tp_copy_library_item, c, h, [], "5", "404")
    assert r["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_missing_item_is_not_found():
    c, h = _client(get_data=ENDURANCE_ITEMS), _http()
    r = await _call(tp_delete_library_item, c, h, [], "5", "404")
    assert r["error_code"] == "NOT_FOUND"
    c.delete.assert_not_called()
    h.delete.assert_not_called()
