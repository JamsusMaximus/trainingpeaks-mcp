"""Events and calendar tools: races, notes, availability."""

import logging
from datetime import date as dt_date
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import DateRangeInput, WorkoutIdInput, format_validation_error

logger = logging.getLogger("tp-mcp")

EVENT_TYPES = [
    "RoadRunning", "TrailRunning", "TrackRunning", "CrossCountry", "Running",
    "RoadCycling", "MountainBiking", "Cyclocross", "TrackCycling", "Cycling",
    "OpenWaterSwimming", "PoolSwimming", "Triathlon", "Xterra", "Duathlon",
    "Aquabike", "Aquathon", "Multisport", "Regatta", "Rowing",
    "AlpineSkiing", "NordicSkiing", "SkiMountaineering", "Snowshoe", "Snow",
    "Adventure", "Obstacle", "SpeedSkate", "Other",
]


class CreateEventInput(BaseModel):
    """Validates input for event creation."""

    name: str = Field(min_length=1, max_length=200)
    date: str
    event_type: str | None = None
    priority: str | None = None
    distance_km: float | None = Field(default=None, ge=0)
    ctl_target: float | None = Field(default=None, ge=0)
    description: str | None = None

    @field_validator("date")
    @classmethod
    def check_date(cls, v: str) -> str:
        from datetime import date

        date.fromisoformat(v)
        return v

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v: str | None) -> str | None:
        if v is not None and v not in ("A", "B", "C"):
            raise ValueError("priority must be 'A', 'B', or 'C'")
        return v

    @field_validator("event_type")
    @classmethod
    def check_event_type(cls, v: str | None) -> str | None:
        if v is not None and v not in EVENT_TYPES:
            raise ValueError(f"Invalid event_type '{v}'. Valid: {', '.join(EVENT_TYPES)}")
        return v


async def tp_get_focus_event() -> dict[str, Any]:
    """Get the A-priority focus event with goals and results."""
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/events/focusevent"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {"event": None, "message": "No focus event set."}

        return {"event": response.data}


async def tp_get_next_event() -> dict[str, Any]:
    """Get the nearest future planned event."""
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/events/nextplannedevent"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {"event": None, "message": "No upcoming events."}

        return {"event": response.data}


async def tp_get_events(start_date: str, end_date: str) -> dict[str, Any]:
    """List events in a date range.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        Dict with events list.
    """
    try:
        params = DateRangeInput(start_date=start_date, end_date=end_date)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        start_str = params.start_date.isoformat()
        end_str = params.end_date.isoformat()
        endpoint = f"/fitness/v6/athletes/{athlete_id}/events/{start_str}/{end_str}"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        data = response.data if isinstance(response.data, list) else []
        return {
            "events": data,
            "count": len(data),
            "date_range": {"start": start_date, "end": end_date},
        }


async def tp_create_event(
    name: str,
    date: str,
    event_type: str | None = None,
    priority: str | None = None,
    distance_km: float | None = None,
    ctl_target: float | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a race/event.

    Args:
        name: Event name.
        date: Event date (YYYY-MM-DD).
        event_type: Event type (e.g. 'RoadRunning', 'Triathlon').
        priority: Priority level ('A', 'B', or 'C').
        distance_km: Event distance in km.
        ctl_target: Target CTL for the event.
        description: Optional description.

    Returns:
        Dict with created event details or error.
    """
    try:
        params = CreateEventInput(
            name=name,
            date=date,
            event_type=event_type,
            priority=priority,
            distance_km=distance_km,
            ctl_target=ctl_target,
            description=description,
        )
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        payload: dict[str, Any] = {
            "athleteId": athlete_id,
            "name": params.name,
            "eventDate": f"{params.date}T00:00:00",
        }
        if params.event_type:
            payload["eventType"] = params.event_type
        if params.priority:
            payload["priority"] = params.priority
        if params.distance_km is not None:
            payload["distance"] = params.distance_km * 1000
        if params.ctl_target is not None:
            payload["ctlTarget"] = params.ctl_target
        if params.description:
            payload["description"] = params.description

        endpoint = f"/fitness/v6/athletes/{athlete_id}/events"
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        event_id = None
        if isinstance(response.data, dict):
            event_id = response.data.get("eventId", response.data.get("id"))

        return {
            "success": True,
            "event_id": event_id,
            "name": params.name,
            "date": params.date,
        }


async def tp_update_event(
    event_id: str,
    name: str | None = None,
    date: str | None = None,
    event_type: str | None = None,
    priority: str | None = None,
    distance_km: float | None = None,
    ctl_target: float | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Update an event (GET then PUT merge).

    Args:
        event_id: Event ID.
        name: Optional new name.
        date: Optional new date (YYYY-MM-DD).
        event_type: Optional event type.
        priority: Optional priority ('A', 'B', 'C').
        distance_km: Optional distance in km.
        ctl_target: Optional CTL target.
        description: Optional description.

    Returns:
        Dict with confirmation or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=event_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    # Validate optional fields before making API calls
    if event_type is not None and event_type not in EVENT_TYPES:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Invalid event_type '{event_type}'.",
        }
    if priority is not None and priority not in ("A", "B", "C"):
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "priority must be 'A', 'B', or 'C'.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        # GET existing event by searching a broad date range
        today = dt_date.today()
        search_start = (today - timedelta(days=730)).isoformat()
        search_end = (today + timedelta(days=730)).isoformat()
        search_endpoint = f"/fitness/v6/athletes/{athlete_id}/events/{search_start}/{search_end}"
        search_response = await client.get(search_endpoint)

        existing = None
        if search_response.success and isinstance(search_response.data, list):
            for evt in search_response.data:
                if evt.get("id") == validated.workout_id:
                    existing = evt
                    break

        if existing is None:
            return {
                "isError": True,
                "error_code": "NOT_FOUND",
                "message": f"Event {validated.workout_id} not found.",
            }

        # Merge updates into existing event
        existing["personId"] = athlete_id
        if name is not None:
            existing["name"] = name
        if date is not None:
            dt_date.fromisoformat(date)
            existing["eventDate"] = f"{date}T00:00:00"
        if event_type is not None:
            existing["eventType"] = event_type
        if priority is not None:
            existing["atpPriority"] = priority
        if distance_km is not None:
            existing["distance"] = distance_km * 1000
        if ctl_target is not None:
            existing["ctlTarget"] = ctl_target
        if description is not None:
            existing["description"] = description

        endpoint = f"/fitness/v6/athletes/{athlete_id}/event"
        response = await client.put(endpoint, json=existing)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": f"Event {validated.workout_id} updated.",
        }


async def tp_delete_event(event_id: str) -> dict[str, Any]:
    """Delete an event.

    Args:
        event_id: Event ID.

    Returns:
        Dict with confirmation or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=event_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/events/{validated.workout_id}"
        response = await client.delete(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": f"Event {validated.workout_id} deleted.",
        }


async def tp_create_note(
    date: str,
    title: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a calendar note.

    Args:
        date: Note date (YYYY-MM-DD).
        title: Note title.
        description: Optional note description.

    Returns:
        Dict with confirmation or error.
    """
    try:
        from datetime import date as date_type

        date_type.fromisoformat(date)
    except ValueError:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Invalid date: {date}",
        }

    if not title or not title.strip():
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Title must not be empty.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        payload: dict[str, Any] = {
            "athleteId": athlete_id,
            "noteDate": f"{date}T00:00:00",
            "title": title.strip(),
        }
        if description:
            payload["description"] = description

        endpoint = f"/fitness/v1/athletes/{athlete_id}/calendarNote"
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        note_id = None
        if isinstance(response.data, dict):
            note_id = response.data.get("calendarNoteId", response.data.get("id"))

        return {
            "success": True,
            "note_id": note_id,
            "title": title,
            "date": date,
        }


async def tp_delete_note(note_id: str) -> dict[str, Any]:
    """Delete a calendar note.

    Args:
        note_id: Note ID.

    Returns:
        Dict with confirmation or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=note_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/calendarNote/{validated.workout_id}"
        response = await client.delete(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": f"Note {validated.workout_id} deleted.",
        }


async def tp_get_availability(start_date: str, end_date: str) -> dict[str, Any]:
    """Get availability entries for a date range.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        Dict with availability entries.
    """
    try:
        params = DateRangeInput(start_date=start_date, end_date=end_date)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        start_str = params.start_date.isoformat()
        end_str = params.end_date.isoformat()
        endpoint = f"/fitness/v1/athletes/{athlete_id}/availability/{start_str}/{end_str}"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        data = response.data if isinstance(response.data, list) else []
        return {
            "availability": data,
            "count": len(data),
        }


async def tp_create_availability(
    start_date: str,
    end_date: str,
    limited: bool = False,
    sport_types: list[str] | None = None,
) -> dict[str, Any]:
    """Mark dates as unavailable or limited.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        limited: If True, mark as limited (not fully unavailable).
        sport_types: If limited, list of available sport types.

    Returns:
        Dict with confirmation or error.
    """
    try:
        params = DateRangeInput(start_date=start_date, end_date=end_date)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        payload: dict[str, Any] = {
            "athleteId": athlete_id,
            "startDate": f"{params.start_date.isoformat()}T00:00:00",
            "endDate": f"{params.end_date.isoformat()}T00:00:00",
            "limited": limited,
        }
        if limited and sport_types:
            payload["sportTypes"] = sport_types

        endpoint = f"/fitness/v1/athletes/{athlete_id}/availability"
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        avail_id = None
        if isinstance(response.data, dict):
            avail_id = response.data.get("availabilityId", response.data.get("id"))

        return {
            "success": True,
            "availability_id": avail_id,
            "start_date": start_date,
            "end_date": end_date,
            "limited": limited,
        }


async def tp_delete_availability(availability_id: str) -> dict[str, Any]:
    """Remove an availability entry.

    Args:
        availability_id: Availability entry ID.

    Returns:
        Dict with confirmation or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=availability_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/availability/{validated.workout_id}"
        response = await client.delete(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": f"Availability {validated.workout_id} deleted.",
        }
