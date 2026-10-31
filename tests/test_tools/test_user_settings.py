"""Tests for account/notification settings tools (mocked transport only)."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.user_settings import (
    tp_get_notification_settings,
    tp_get_user_settings,
    tp_update_notification_settings,
    tp_update_user_settings,
)

DOC = {
    "calendar": {
        "showComplianceColoring": True,
        "orderComplianceBy": ["TSS", "Duration", "Distance"],
        "compactView": True,
    },
    "workout": {"layout": {"1": [1, 2]}},
    "general": {"defaultLandingPage": "Calendar"},
    "metrics": [{"type": 6}, {"type": 10}],
    "atp": {"displayGraph": True},
}
COACH = [
    {"athleteId": 7, "inAppEnabled": True, "mobileEnabled": False, "emailEnabled": False, "details": [
        {"athleteId": 7, "type": "WorkoutUpload", "inAppEnabled": False, "mobileEnabled": False, "emailEnabled": True},
        {"athleteId": 7, "type": "WorkoutComment", "inAppEnabled": True, "mobileEnabled": False, "emailEnabled": False},
    ]},
    {"athleteId": 8, "inAppEnabled": True, "mobileEnabled": True, "emailEnabled": True, "details": []},
]


def _client(get=None, put=None):
    inst = AsyncMock()
    inst.ensure_athlete_id = AsyncMock(return_value=7)
    inst._get_user_data = AsyncMock(return_value={"userId": 99})
    inst.get = AsyncMock(side_effect=get or (lambda e: APIResponse(success=True, data=DOC)))
    inst.put = AsyncMock(return_value=put or APIResponse(success=True, data=None))
    return inst


def _patch(inst):
    p = patch("tp_mcp.tools.user_settings.TPClient")
    mock = p.start()
    mock.return_value.__aenter__.return_value = inst
    return p


@pytest.mark.asyncio
class TestUserSettings:
    async def test_get_all_and_section_use_the_right_owner(self):
        inst = _client()
        p = _patch(inst)
        try:
            r = await tp_get_user_settings()
            assert r["owner_id"] == 7 and r["settings"] == DOC and "calendar" in r["writable_sections"]
            inst.get.assert_called_with("/users/v1/user/7/settings")
            r = await tp_get_user_settings(section="calendar", scope="account")
            assert r["owner_id"] == 99 and r["settings"]["compactView"] is True
            inst.get.assert_called_with("/users/v1/user/99/settings")
            assert (await tp_get_user_settings(section="nope"))["isError"]
            assert (await tp_get_user_settings(scope="team"))["error_code"] == "VALIDATION_ERROR"
        finally:
            p.stop()

    async def test_update_merges_object_and_returns_previous(self):
        inst = _client()
        p = _patch(inst)
        try:
            r = await tp_update_user_settings("calendar", {"orderComplianceBy": ["Duration", "TSS", "Distance"]})
        finally:
            p.stop()
        assert r["previous"]["orderComplianceBy"] == ["TSS", "Duration", "Distance"]
        assert r["updated"]["orderComplianceBy"][0] == "Duration"
        assert r["updated"]["compactView"] is True  # untouched keys kept
        inst.put.assert_called_once_with("/users/v1/user/7/settings/calendar", json=r["updated"])

    async def test_dry_run_and_list_section_and_validation(self):
        inst = _client()
        p = _patch(inst)
        try:
            r = await tp_update_user_settings("calendar", {"compactView": False}, dry_run=True)
            assert r["dry_run"] and r["updated"]["compactView"] is False
            inst.put.assert_not_called()
            r = await tp_update_user_settings("metrics", [{"type": 6}])
            assert r["updated"] == [{"type": 6}]  # lists replace
            assert (await tp_update_user_settings("metrics", {"a": 1}))["error_code"] == "VALIDATION_ERROR"
            assert (await tp_update_user_settings("atp", {"a": 1}))["error_code"] == "VALIDATION_ERROR"
            assert (await tp_update_user_settings("calendar", {}))["error_code"] == "VALIDATION_ERROR"
        finally:
            p.stop()

    async def test_put_failure_is_surfaced(self):
        from tp_mcp.client.http import ErrorCode

        inst = _client(put=APIResponse(success=False, error_code=ErrorCode.API_ERROR, message="no"))
        p = _patch(inst)
        try:
            r = await tp_update_user_settings("general", {"defaultLandingPage": "Home"})
        finally:
            p.stop()
        assert r["isError"] and r["message"] == "no"


@pytest.mark.asyncio
class TestNotificationSettings:
    @staticmethod
    def _get(endpoint):
        return APIResponse(success=True, data=COACH if "coachSettings" in endpoint else {"athleteId": 7})

    async def test_get(self):
        inst = _client(get=self._get)
        p = _patch(inst)
        try:
            r = await tp_get_notification_settings()
        finally:
            p.stop()
        assert r["coach"] == COACH and r["athlete"] == {"athleteId": 7} and "WorkoutUpload" in r["types"]

    async def test_update_one_type_sends_whole_list(self):
        inst = _client(get=self._get)
        p = _patch(inst)
        try:
            r = await tp_update_notification_settings(7, type="WorkoutUpload", email=False)
        finally:
            p.stop()
        assert r["previous"]["details"][0]["emailEnabled"] is True
        sent = inst.put.call_args.kwargs["json"]
        assert len(sent) == 2 and sent[0]["details"][0]["emailEnabled"] is False
        assert sent[0]["details"][1]["inAppEnabled"] is True  # other types untouched

    async def test_update_athlete_wide_dry_run_and_errors(self):
        inst = _client(get=self._get)
        p = _patch(inst)
        try:
            r = await tp_update_notification_settings(8, mobile=False, dry_run=True)
            assert r["updated"]["mobileEnabled"] is False and r["previous"]["mobileEnabled"] is True
            inst.put.assert_not_called()
            assert (await tp_update_notification_settings(7))["error_code"] == "VALIDATION_ERROR"
            bad_type = await tp_update_notification_settings(7, type="Bogus", email=True)
            assert bad_type["error_code"] == "VALIDATION_ERROR"
            assert (await tp_update_notification_settings(123, email=True))["error_code"] == "NOT_FOUND"
            no_entry = await tp_update_notification_settings(8, type="WorkoutUpload", email=True)
            assert no_entry["error_code"] == "NOT_FOUND"
        finally:
            p.stop()
