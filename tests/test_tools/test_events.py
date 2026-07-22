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
    tp_list_notes,
    tp_update_event,
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


class TestEventDistanceNormalisation:
    """Event tools inject a canonical distance_km alongside TP's raw
    distance/distanceUnits, which vary per athlete for the same race (#71)."""

    @staticmethod
    async def _next_event_result(data):
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance
            return await tp_get_next_event()

    @pytest.mark.asyncio
    async def test_meters_units(self):
        result = await self._next_event_result(
            {"name": "50K", "distance": 50000, "distanceUnits": "Meters"}
        )
        assert result["event"]["distance_km"] == 50.0
        # Raw fields untouched
        assert result["event"]["distance"] == 50000
        assert result["event"]["distanceUnits"] == "Meters"

    @pytest.mark.asyncio
    async def test_kilometers_units(self):
        result = await self._next_event_result(
            {"name": "50K", "distance": 50, "distanceUnits": "Kilometers"}
        )
        assert result["event"]["distance_km"] == 50.0

    @pytest.mark.asyncio
    async def test_blank_units_large_value_assumed_meters(self):
        result = await self._next_event_result(
            {"name": "50K", "distance": 50000, "distanceUnits": ""}
        )
        assert result["event"]["distance_km"] == 50.0

    @pytest.mark.asyncio
    async def test_null_units_small_value_assumed_km(self):
        result = await self._next_event_result(
            {"name": "50K", "distance": 50, "distanceUnits": None}
        )
        assert result["event"]["distance_km"] == 50.0

    @pytest.mark.asyncio
    async def test_missing_distance(self):
        result = await self._next_event_result({"name": "No distance"})
        assert result["event"]["distance_km"] is None

    @pytest.mark.asyncio
    async def test_non_numeric_distance(self):
        result = await self._next_event_result(
            {"name": "Bad data", "distance": "n/a", "distanceUnits": "Kilometers"}
        )
        assert result["event"]["distance_km"] is None

    @pytest.mark.asyncio
    async def test_miles_units(self):
        result = await self._next_event_result(
            {"name": "Marathon", "distance": 26.2, "distanceUnits": "Miles"}
        )
        assert result["event"]["distance_km"] == pytest.approx(42.164813, rel=1e-6)

    @pytest.mark.asyncio
    async def test_focus_event_gets_distance_km(self):
        response = APIResponse(
            success=True,
            data={"name": "IM World Champs", "distance": 226000, "distanceUnits": "Meters"},
        )
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_focus_event()

        assert result["event"]["distance_km"] == 226.0

    @pytest.mark.asyncio
    async def test_get_events_list_gets_distance_km(self):
        events = [
            {"name": "Race A", "distance": 10000, "distanceUnits": "Meters"},
            {"name": "Race B", "distance": 21.1, "distanceUnits": "Kilometers"},
        ]
        response = APIResponse(success=True, data=events)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_events("2026-01-01", "2026-03-01")

        assert [e["distance_km"] for e in result["events"]] == [10.0, 21.1]


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
                description="Holiday",
            )

        assert result["success"] is True
        assert result["limited"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["personId"] == 123
        assert payload["type"] == 2
        assert payload["availableSportTypes"] == [3, 1]
        assert payload["description"] == "Holiday"
        assert "athleteId" not in payload
        assert "limited" not in payload


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


class TestListNotes:
    NOTE_DATA = [
        {
            "id": 83073469,
            "title": "Zwei Tests",
            "description": "Du brauchst nur einen der beiden Tests absolvieren.",
            "noteDate": "2026-05-07T00:00:00",
            "createdDate": "2026-03-03T07:21:22",
            "modifiedDate": "2026-03-03T07:21:22",
            "athleteId": 1463609,
            "isHidden": False,
            "commentCount": 0,
            "ownerId": 1463609,
            "appliedPlanId": 1024010,
            "parentPlanNoteId": 231128,
            "attachments": [],
        },
        {
            "id": 87921017,
            "title": "Spitzenwoche",
            "description": None,
            "noteDate": "2026-05-14T00:00:00",
            "createdDate": "2026-05-01T08:00:00",
            "modifiedDate": "2026-05-01T08:00:00",
            "athleteId": 1463609,
            "isHidden": True,
            "commentCount": 2,
            "ownerId": 1463609,
            "appliedPlanId": 0,
            "parentPlanNoteId": 0,
            "attachments": [],
        },
    ]

    @pytest.mark.asyncio
    async def test_list_notes_success(self):
        response = APIResponse(success=True, data=self.NOTE_DATA)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=1463609)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_list_notes(start_date="2026-05-01", end_date="2026-05-31")

        assert result["count"] == 2
        assert len(result["notes"]) == 2
        assert result["date_range"] == {"start": "2026-05-01", "end": "2026-05-31"}
        first = result["notes"][0]
        assert first["id"] == 83073469
        assert first["title"] == "Zwei Tests"
        assert first["date"] == "2026-05-07"
        assert first["is_hidden"] is False
        assert first["comment_count"] == 0
        assert first["owner_id"] == 1463609
        assert first["attachments"] == []
        second = result["notes"][1]
        assert second["id"] == 87921017
        assert second["is_hidden"] is True
        assert second["comment_count"] == 2

    @pytest.mark.asyncio
    async def test_list_notes_empty(self):
        response = APIResponse(success=True, data=[])
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=1463609)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_list_notes(start_date="2026-01-01", end_date="2026-01-07")

        assert result["count"] == 0
        assert result["notes"] == []
        assert result["date_range"] == {"start": "2026-01-01", "end": "2026-01-07"}

    @pytest.mark.asyncio
    async def test_list_notes_invalid_date(self):
        result = await tp_list_notes(start_date="not-a-date", end_date="2026-05-31")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_list_notes_end_before_start(self):
        result = await tp_list_notes(start_date="2026-05-31", end_date="2026-05-01")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_list_notes_api_error(self):
        response = APIResponse(success=False, error_code=ErrorCode.NOT_FOUND, message="Not found")
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=1463609)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_list_notes(start_date="2026-05-01", end_date="2026-05-31")

        assert result["isError"] is True
        assert result["error_code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_list_notes_uses_v2_endpoint(self):
        response = APIResponse(success=True, data=[])
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=1463609)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            await tp_list_notes(start_date="2026-05-01", end_date="2026-05-31")

        called_endpoint = mock_instance.get.call_args[0][0]
        assert "/fitness/v2/" in called_endpoint
        assert "2026-05-01" in called_endpoint
        assert "2026-05-31" in called_endpoint

    @pytest.mark.asyncio
    async def test_list_notes_calendar_note_id_fallback(self):
        data = [{"calendarNoteId": 999, "title": "Fallback", "noteDate": "2026-05-10T00:00:00"}]
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=1463609)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_list_notes(start_date="2026-05-01", end_date="2026-05-31")

        assert result["notes"][0]["id"] == 999

    @pytest.mark.asyncio
    async def test_list_notes_missing_note_date(self):
        data = [{"id": 1, "title": "No date"}]
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=1463609)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_list_notes(start_date="2026-05-01", end_date="2026-05-31")

        assert result["notes"][0]["date"] is None


class TestUpdateEventAttachLegs:
    """tp_update_event(workout_ids=...) attaches workouts to an event as its legs.
    TP links them via the event's `workouts` id array (HAR-verified: PUT /event
    with workouts=[…]; `legs` stays [] and is derived server-side)."""

    @pytest.mark.asyncio
    async def test_workout_ids_sets_workouts_array(self):
        existing = {
            "id": 37493307,
            "name": "Ironstar Гром олимпийка",
            "eventDate": "2026-05-30T00:00:00",
            "eventType": "MultisportTriathlon",
            "personId": 1680841,
            "legs": [],
            "workouts": [3753121100],  # one leg already attached
        }
        get_response = APIResponse(success=True, data=[existing])
        put_response = APIResponse(success=True, data={})
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=1680841)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.put = AsyncMock(return_value=put_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_event(
                event_id="37493307",
                workout_ids=[3753121100, 3763855286, 3753121299, 3753122444],
            )

        assert result["success"] is True
        payload = mock_instance.put.call_args.kwargs["json"]
        assert payload["workouts"] == [3753121100, 3763855286, 3753121299, 3753122444]
        assert payload["legs"] == []          # legs untouched — TP derives them

    @pytest.mark.asyncio
    async def test_string_workout_ids_are_coerced_to_int(self):
        existing = {"id": 1, "personId": 9, "legs": [], "workouts": []}
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=9)
            mock_instance.get = AsyncMock(return_value=APIResponse(success=True, data=[existing]))
            mock_instance.put = AsyncMock(return_value=APIResponse(success=True, data={}))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_event(event_id="1", workout_ids=["10", "20"])

        assert result["success"] is True
        assert mock_instance.put.call_args.kwargs["json"]["workouts"] == [10, 20]

    @pytest.mark.asyncio
    async def test_workout_ids_omitted_leaves_workouts_untouched(self):
        existing = {"id": 1, "personId": 9, "legs": [], "workouts": [55]}
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=9)
            mock_instance.get = AsyncMock(return_value=APIResponse(success=True, data=[existing]))
            mock_instance.put = AsyncMock(return_value=APIResponse(success=True, data={}))
            mock_client.return_value.__aenter__.return_value = mock_instance

            await tp_update_event(event_id="1", description="just a note")

        assert mock_instance.put.call_args.kwargs["json"]["workouts"] == [55]
