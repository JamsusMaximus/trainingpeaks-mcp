"""Tests for the notification feed tool (mocked transport only)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.notifications import tp_get_notifications

FEED = {
    "newNotificationCount": 3,
    "unreadNotificationCount": 1,
    "notifications": [
        {
            "id": 2, "isRead": True, "timestamp": "2026-11-01T22:33:42Z", "notificationType": "WorkoutComment",
            "itemDataType": "Workout", "itemId": 20, "modifiedByPersonId": 5, "aboutPersonId": 5,
            "modifiedByFirstName": "Pat", "modifiedByLastName": "Example",
            "itemData": json.dumps({"workoutId": 20, "title": "Easy run", "sportType": "Run",
                                    "tssCompleted": 50.5, "feedItems": [{"big": "blob"}]}),
        },
        {
            "id": 1, "isRead": False, "timestamp": "2026-11-02T15:40:15Z", "notificationType": "AvailabilityCreated",
            "itemDataType": "Availability", "itemId": 10, "modifiedByPersonId": 5, "aboutPersonId": 5,
            "modifiedByFirstName": "Pat", "modifiedByLastName": "Example",
            "itemData": json.dumps({"id": 10, "startDate": "2026-11-15T00:00:00", "type": "Limited",
                                    "reason": "Work", "personId": 5}),
        },
        {
            "id": 3, "isRead": True, "timestamp": "2026-10-30T10:00:00Z", "notificationType": "ThresholdChange",
            "itemDataType": "Threshold", "itemId": 30, "modifiedByFirstName": None, "modifiedByLastName": None,
            "itemData": "not json",
        },
    ],
}


def _patch(response):
    p = patch("tp_mcp.tools.notifications.TPClient")
    mock = p.start()
    inst = AsyncMock()
    inst.get = AsyncMock(return_value=response)
    mock.return_value.__aenter__.return_value = inst
    return p, inst


@pytest.mark.asyncio
class TestGetNotifications:
    async def test_lists_newest_first_and_trims_item_data(self):
        p, inst = _patch(APIResponse(success=True, data=FEED))
        try:
            result = await tp_get_notifications(days=7)
        finally:
            p.stop()
        inst.get.assert_awaited_once_with("/notification/v2/notifications/7")
        assert result["unread_count"] == 1
        assert result["types"] == ["AvailabilityCreated", "ThresholdChange", "WorkoutComment"]
        assert [n["id"] for n in result["notifications"]] == [1, 2, 3]
        availability, comment, bad = result["notifications"]
        assert availability["from"] == "Pat Example" and availability["is_read"] is False
        assert availability["item"] == {"id": 10, "startDate": "2026-11-15T00:00:00", "type": "Limited",
                                        "reason": "Work"}
        assert comment["item"] == {"workoutId": 20, "title": "Easy run", "sportType": "Run", "tssCompleted": 50.5}
        assert bad["item"] == {} and bad["from"] is None

    async def test_unread_only_and_type_filters(self):
        p, _ = _patch(APIResponse(success=True, data=FEED))
        try:
            unread = await tp_get_notifications(unread_only=True)
            typed = await tp_get_notifications(type="WorkoutComment")
        finally:
            p.stop()
        assert [n["id"] for n in unread["notifications"]] == [1]
        assert [n["id"] for n in typed["notifications"]] == [2]
        assert typed["types"] == ["AvailabilityCreated", "ThresholdChange", "WorkoutComment"]

    async def test_default_window_is_fourteen_days(self):
        p, inst = _patch(APIResponse(success=True, data={"notifications": []}))
        try:
            result = await tp_get_notifications()
        finally:
            p.stop()
        inst.get.assert_awaited_once_with("/notification/v2/notifications/14")
        assert result["count"] == 0 and result["notifications"] == []

    @pytest.mark.parametrize("days", [0, -1, 366, True])
    async def test_rejects_bad_days(self, days):
        result = await tp_get_notifications(days=days)
        assert result["isError"] and result["error_code"] == "VALIDATION_ERROR"

    async def test_api_error_is_returned(self):
        p, _ = _patch(APIResponse(success=False, message="boom"))
        try:
            result = await tp_get_notifications()
        finally:
            p.stop()
        assert result["isError"] and result["message"] == "boom"
