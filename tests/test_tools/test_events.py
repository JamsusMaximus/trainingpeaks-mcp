"""Tests for events and calendar tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse, ErrorCode
from tp_mcp.tools.events import (
    tp_add_note_comment,
    tp_create_availability,
    tp_create_event,
    tp_create_note,
    tp_delete_event,
    tp_get_availability,
    tp_get_events,
    tp_get_focus_event,
    tp_get_next_event,
    tp_get_note,
    tp_get_note_comments,
    tp_update_note,
)


class TestGetFocusEvent:
    @pytest.mark.asyncio
    async def test_returns_event(self):
        response = APIResponse(success=True, data={"name": "IM World Champs", "priority": "A"})
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_focus_event()

        assert result["event"]["name"] == "IM World Champs"

    @pytest.mark.asyncio
    async def test_no_focus_event(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_focus_event()

        assert result["event"] is None


class TestGetNextEvent:
    @pytest.mark.asyncio
    async def test_returns_event(self):
        response = APIResponse(success=True, data={"name": "Local 10K"})
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_next_event()

        assert result["event"]["name"] == "Local 10K"


class TestGetEvents:
    @pytest.mark.asyncio
    async def test_list_events(self):
        events = [{"name": "Race A"}, {"name": "Race B"}]
        response = APIResponse(success=True, data=events)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_events("2026-01-01", "2026-03-01")

        assert result["count"] == 2


class TestCreateEvent:
    @pytest.mark.asyncio
    async def test_create_with_priority_and_ctl(self):
        response = APIResponse(success=True, data={"eventId": 501})
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_event(
                name="IRONMAN", date="2026-09-15",
                event_type="MultisportTriathlon", priority="A",
                distance_km=226.0, ctl_target=120.0,
            )

        assert result["success"] is True
        assert result["event_id"] == 501
        assert mock_instance.post.call_args[0][0] == "/fitness/v6/athletes/123/event"
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["personId"] == 123
        assert payload["atpPriority"] == "A"
        assert payload["eventDate"] == "2026-09-15"
        assert payload["goals"] == {}
        assert payload["legs"] == []
        assert payload["workouts"] == []
        assert payload["results"] == [
            {"resultType": "Division"},
            {"resultType": "Gender"},
            {"resultType": "Overall"},
        ]
        assert payload["distance"] == 226.0
        assert payload["distanceUnits"] == "Kilometers"
        assert payload["ctlTarget"] == 120.0

    @pytest.mark.asyncio
    async def test_default_event_type_is_other_other(self):
        response = APIResponse(success=True, data={"eventId": 502})
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            await tp_create_event(name="No-type event", date="2026-10-01")

        payload = mock_instance.post.call_args[1]["json"]
        assert payload["eventType"] == "OtherOther"


class TestDeleteEvent:
    @pytest.mark.asyncio
    async def test_delete_success(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.delete = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_delete_event("501")

        assert result["success"] is True
        # v6 uses singular /event/{id}; the plural form returns NOT_FOUND.
        mock_instance.delete.assert_awaited_once_with(
            "/fitness/v6/athletes/123/event/501"
        )


class TestCreateNote:
    @pytest.mark.asyncio
    async def test_create_note(self):
        response = APIResponse(success=True, data={"calendarNoteId": 701})
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_note(
                date="2026-03-15", title="Rest week", description="Deload",
            )

        assert result["success"] is True
        assert result["note_id"] == 701


class TestAvailability:
    @pytest.mark.asyncio
    async def test_get_availability(self):
        data = [{"id": 1, "startDate": "2026-04-01", "limited": False}]
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_availability("2026-04-01", "2026-04-30")

        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_create_limited_with_sports(self):
        response = APIResponse(success=True, data={"availabilityId": 801})
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_availability(
                start_date="2026-04-01", end_date="2026-04-07",
                limited=True, sport_types=["Run", "Swim"],
            )

        assert result["success"] is True
        assert result["limited"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["limited"] is True
        assert payload["sportTypes"] == ["Run", "Swim"]


class TestGetNote:
    @pytest.mark.asyncio
    async def test_get_note_success(self):
        data = {
            "id": 87386062,
            "title": "Test Note",
            "description": "Test Test",
            "noteDate": "2026-05-05T00:00:00",
            "createdDate": "2026-05-03T10:31:20",
            "modifiedDate": "2026-05-03T10:31:20",
            "athleteId": 1463609,
            "isHidden": False,
            "ownerId": 1463609,
            "appliedPlanId": 0,
            "parentPlanNoteId": 0,
            "attachments": [],
        }
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_note(note_id="87386062")

        assert result["note"]["id"] == 87386062
        assert result["note"]["title"] == "Test Note"
        assert result["note"]["date"] == "2026-05-05"
        assert result["note"]["description"] == "Test Test"
        assert result["note"]["is_hidden"] is False

    @pytest.mark.asyncio
    async def test_get_note_invalid_id(self):
        result = await tp_get_note(note_id="abc")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_get_note_not_found(self):
        response = APIResponse(success=False, error_code=ErrorCode.NOT_FOUND, message="Not found")
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_note(note_id="999")

        assert result["isError"] is True
        assert result["error_code"] == "NOT_FOUND"


class TestUpdateNote:
    @pytest.mark.asyncio
    async def test_update_note_success(self):
        existing = {
            "id": 87386062,
            "title": "Old Title",
            "description": "Old desc",
            "noteDate": "2026-05-05T00:00:00",
            "createdDate": "2026-05-03T10:31:20",
            "modifiedDate": "2026-05-03T10:31:20",
            "athleteId": 1463609,
            "isHidden": False,
            "ownerId": 1463609,
            "appliedPlanId": 0,
            "parentPlanNoteId": 0,
            "attachments": [],
        }
        updated = {**existing, "title": "New Title", "description": "New desc"}
        get_response = APIResponse(success=True, data=existing)
        put_response = APIResponse(success=True, data=updated)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.put = AsyncMock(return_value=put_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_note(
                note_id="87386062", title="New Title", description="New desc"
            )

        assert result["success"] is True
        assert result["note"]["title"] == "New Title"
        assert result["note"]["description"] == "New desc"

    @pytest.mark.asyncio
    async def test_update_note_invalid_id(self):
        result = await tp_update_note(note_id="abc", title="X")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_update_note_no_fields(self):
        result = await tp_update_note(note_id="123")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_update_note_whitespace_title(self):
        result = await tp_update_note(note_id="123", title="   ")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_update_note_get_fails(self):
        get_response = APIResponse(success=False, error_code=ErrorCode.NOT_FOUND, message="Not found")
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_note(note_id="999", title="X")

        assert result["isError"] is True
        assert result["error_code"] == "NOT_FOUND"
        mock_instance.put.assert_not_called()


class TestGetNoteComments:
    @pytest.mark.asyncio
    async def test_get_comments_success(self):
        data = [
            {
                "calendarNoteId": 87386062,
                "calendarNoteCommentStreamId": 194161,
                "comment": "Looks great",
                "commenterPersonId": 1463609,
                "createdDateTimeUtc": "2026-05-03T10:31:25",
                "updatedDateTimeUtc": "2026-05-03T10:31:25",
                "firstName": "Torge",
                "lastName": "Valerius",
                "commenterPhotoUrl": "https://example.com/photo.jpg",
            }
        ]
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_note_comments(note_id="87386062")

        assert result["count"] == 1
        assert result["comments"][0]["comment"] == "Looks great"
        assert result["comments"][0]["commenter"] == "Torge Valerius"
        assert result["comments"][0]["id"] == 194161

    @pytest.mark.asyncio
    async def test_get_comments_empty(self):
        response = APIResponse(success=True, data=[])
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_note_comments(note_id="87386062")

        assert result["count"] == 0
        assert result["comments"] == []

    @pytest.mark.asyncio
    async def test_get_comments_invalid_id(self):
        result = await tp_get_note_comments(note_id="abc")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"


class TestAddNoteComment:
    @pytest.mark.asyncio
    async def test_add_comment_success(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.put = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_add_note_comment(note_id="87386062", comment="Nice ride!")

        assert result["success"] is True
        mock_instance.put.assert_called_once()
        call_kwargs = mock_instance.put.call_args
        assert call_kwargs.kwargs["json"] == {"Comment": "Nice ride!"}

    @pytest.mark.asyncio
    async def test_add_comment_empty_comment(self):
        result = await tp_add_note_comment(note_id="87386062", comment="  ")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_add_comment_invalid_id(self):
        result = await tp_add_note_comment(note_id="abc", comment="test")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
