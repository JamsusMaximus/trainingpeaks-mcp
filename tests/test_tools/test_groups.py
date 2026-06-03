"""Tests for athlete group (tag) read tools — issue #69."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.groups import tp_list_athletes_in_group, tp_list_groups

USER = {
    "personId": 1135463,
    "athletes": [
        {"athleteId": 201, "firstName": "Charlotte", "lastName": "Horton"},
        {"athleteId": 202, "firstName": "Ivan", "lastName": "Petrov"},
        {"athleteId": 203, "firstName": "Anna", "lastName": "Sun"},
    ],
}

TAGS = [
    {"id": 11, "coachId": 1135463, "name": "Group A",
     "athleteIds": [202, 201], "isDefault": False},
    {"id": 12, "coachId": 1135463, "name": "My Athletes",
     "athleteIds": [201, 202, 203], "isDefault": True},
]


def _client(**methods):
    inst = AsyncMock()
    for name, value in methods.items():
        setattr(inst, name, AsyncMock(return_value=value))
    return inst


def _patch(monkeypatch_target, instance):
    p = patch(monkeypatch_target)
    mock = p.start()
    mock.return_value.__aenter__.return_value = instance
    return p


# ── tp_list_groups ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_groups_ok():
    inst = _client(
        _get_user_data=USER,
        get=APIResponse(success=True, data=TAGS),
    )
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_list_groups()
    assert out["count"] == 2
    a = next(g for g in out["groups"] if g["id"] == 11)
    assert a == {"id": 11, "name": "Group A", "athlete_count": 2, "is_default": False}
    default = next(g for g in out["groups"] if g["id"] == 12)
    assert default["is_default"] is True
    # coach-scoped endpoint built from personId
    inst.get.assert_awaited_once_with("/coaches/v2/coaches/1135463/tags")


@pytest.mark.asyncio
async def test_list_groups_auth_failure():
    inst = _client(_get_user_data=None)
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_list_groups()
    assert out["isError"] is True
    assert out["error_code"] == "AUTH_INVALID"


@pytest.mark.asyncio
async def test_list_groups_api_error():
    inst = _client(
        _get_user_data=USER,
        get=APIResponse(success=False, message="boom"),
    )
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_list_groups()
    assert out["isError"] is True


# ── tp_list_athletes_in_group ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_athletes_in_group_joins_names_sorted():
    inst = _client(
        _get_user_data=USER,
        get=APIResponse(success=True, data=TAGS),
    )
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_list_athletes_in_group("11")
    assert out["group_id"] == 11
    assert out["name"] == "Group A"
    # sorted by name: Charlotte Horton, Ivan Petrov
    assert out["athletes"] == [
        {"athlete_id": 201, "name": "Charlotte Horton"},
        {"athlete_id": 202, "name": "Ivan Petrov"},
    ]
    assert out["count"] == 2


@pytest.mark.asyncio
async def test_list_athletes_in_group_unknown_id():
    inst = _client(
        _get_user_data=USER,
        get=APIResponse(success=True, data=TAGS),
    )
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_list_athletes_in_group("999")
    assert out["isError"] is True
    assert out["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_list_athletes_in_group_non_numeric():
    out = await tp_list_athletes_in_group("abc")
    assert out["isError"] is True
    assert out["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_list_athletes_in_group_athlete_not_in_roster():
    user = {"personId": 1135463, "athletes": []}   # roster doesn't have the ids
    inst = _client(
        _get_user_data=user,
        get=APIResponse(success=True, data=TAGS),
    )
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_list_athletes_in_group("11")
    # ids preserved, names None (still useful to the caller)
    assert {a["athlete_id"] for a in out["athletes"]} == {201, 202}
    assert all(a["name"] is None for a in out["athletes"])


# ── write tools (create / rename / delete) — verified signatures ─────────────
from tp_mcp.tools.groups import (
    tp_create_group, tp_delete_group, tp_rename_group,
)

CREATED = {"id": 337680, "coachId": 1135463, "name": "New", "athleteIds": [], "isDefault": False}


@pytest.mark.asyncio
async def test_create_group_uses_v1_value_body():
    inst = _client(_get_user_data=USER, post=APIResponse(success=True, data=CREATED))
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_create_group("New")
    assert out["id"] == 337680
    assert out["name"] == "New"
    # v1 endpoint + body key "Value" (the verified quirk)
    inst.post.assert_awaited_once_with(
        "/coaches/v1/coaches/1135463/tags", json={"Value": "New"})


@pytest.mark.asyncio
async def test_create_group_rejects_empty_name():
    out = await tp_create_group("   ")
    assert out["isError"] and out["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_rename_group_puts_value_and_guards_default():
    inst = _client(
        _get_user_data=USER,
        get=APIResponse(success=True, data=TAGS),
        put=APIResponse(success=True, data={}),
    )
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_rename_group("11", "Renamed")
    assert out == {"id": 11, "name": "Renamed"}
    inst.put.assert_awaited_once_with(
        "/coaches/v1/coaches/1135463/tags/11", json={"Value": "Renamed"})


@pytest.mark.asyncio
async def test_rename_default_group_forbidden():
    inst = _client(_get_user_data=USER, get=APIResponse(success=True, data=TAGS),
                   put=APIResponse(success=True, data={}))
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_rename_group("12", "X")   # 12 is isDefault
    assert out["isError"] and out["error_code"] == "FORBIDDEN"
    inst.put.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_group_ok_and_guards_default():
    inst = _client(_get_user_data=USER, get=APIResponse(success=True, data=TAGS),
                   delete=APIResponse(success=True, data=None))
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_delete_group("11")
    assert out["deleted"] is True and out["id"] == 11
    inst.delete.assert_awaited_once_with("/coaches/v1/coaches/1135463/tags/11")


@pytest.mark.asyncio
async def test_delete_default_group_forbidden():
    inst = _client(_get_user_data=USER, get=APIResponse(success=True, data=TAGS),
                   delete=APIResponse(success=True, data=None))
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_delete_group("12")        # default
    assert out["isError"] and out["error_code"] == "FORBIDDEN"
    inst.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_unknown_group_not_found():
    inst = _client(_get_user_data=USER, get=APIResponse(success=True, data=TAGS),
                   delete=APIResponse(success=True, data=None))
    with patch("tp_mcp.tools.groups.TPClient") as mc:
        mc.return_value.__aenter__.return_value = inst
        out = await tp_delete_group("999")
    assert out["isError"] and out["error_code"] == "NOT_FOUND"
