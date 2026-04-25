"""Tests for events and calendar tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.events import (
    tp_create_availability,
    tp_create_event,
    tp_create_note,
    tp_delete_event,
    tp_get_availability,
    tp_get_events,
    tp_get_focus_event,
    tp_get_next_event,
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
                event_type="Triathlon", priority="A",
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
