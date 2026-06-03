"""Workout library tools: templates, scheduling."""

import logging
from typing import Any

from pydantic import ValidationError

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import WorkoutIdInput, format_validation_error

logger = logging.getLogger("tp-mcp")


async def tp_get_libraries() -> dict[str, Any]:
    """List all workout library folders.

    Returns:
        Dict with libraries list.
    """
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = "/exerciselibrary/v2/libraries"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        data = response.data if isinstance(response.data, list) else []
        libraries = [
            {
                "id": lib.get("exerciseLibraryId", lib.get("id")),
                "name": lib.get("name", ""),
                "is_default": lib.get("isDefault", False),
                "item_count": lib.get("itemCount", 0),
            }
            for lib in data
        ]

        return {"libraries": libraries, "count": len(libraries)}


async def tp_get_library_items(library_id: str) -> dict[str, Any]:
    """List templates in a workout library.

    Args:
        library_id: Library ID.

    Returns:
        Dict with library items list.
    """
    try:
        validated = WorkoutIdInput(workout_id=library_id)
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

        endpoint = f"/exerciselibrary/v2/libraries/{validated.workout_id}/items"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        data = response.data if isinstance(response.data, list) else []
        items = [
            {
                "id": item.get("exerciseLibraryItemId", item.get("id")),
                "name": item.get("itemName", item.get("name", "")),
                "sport": item.get("workoutTypeId"),
                "duration": item.get("totalTimePlanned"),
                "tss": item.get("tssPlanned"),
            }
            for item in data
        ]

        return {
            "items": items,
            "count": len(items),
            "library_id": validated.workout_id,
        }


async def tp_get_library_item(library_id: str, item_id: str) -> dict[str, Any]:
    """Get full template details including structure.

    Args:
        library_id: Library ID.
        item_id: Library item ID.

    Returns:
        Dict with item details.
    """
    try:
        lib_validated = WorkoutIdInput(workout_id=library_id)
        item_validated = WorkoutIdInput(workout_id=item_id)
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

        # Get all items and find the specific one
        endpoint = f"/exerciselibrary/v2/libraries/{lib_validated.workout_id}/items"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        data = response.data if isinstance(response.data, list) else []

        for item in data:
            iid = item.get("exerciseLibraryItemId", item.get("id"))
            if iid == item_validated.workout_id:
                return {"item": item}

        return {
            "isError": True,
            "error_code": "NOT_FOUND",
            "message": f"Item {item_validated.workout_id} not found in library {lib_validated.workout_id}.",
        }


async def tp_create_library(name: str) -> dict[str, Any]:
    """Create a workout library folder.

    Args:
        name: Library name.

    Returns:
        Dict with confirmation or error.
    """
    if not name or not name.strip():
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Library name must not be empty.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = "/exerciselibrary/v1/libraries"
        payload = {"name": name.strip()}
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        lib_id = None
        if isinstance(response.data, dict):
            lib_id = response.data.get("exerciseLibraryId", response.data.get("id"))

        return {
            "success": True,
            "library_id": lib_id,
            "name": name.strip(),
        }


async def tp_delete_library(library_id: str) -> dict[str, Any]:
    """Delete a workout library folder and all its templates.

    Args:
        library_id: Library ID.

    Returns:
        Dict with confirmation or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=library_id)
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

        endpoint = f"/exerciselibrary/v1/libraries/{validated.workout_id}"
        response = await client.delete(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": f"Library {validated.workout_id} deleted.",
        }


async def tp_create_library_item(
    library_id: str,
    name: str,
    sport_family_id: int,
    sport_type_id: int,
    duration_hours: float | None = None,
    tss: float | None = None,
    description: str | None = None,
    structure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save a workout template to a library.

    Args:
        library_id: Library ID.
        name: Template name.
        sport_family_id: Sport family ID.
        sport_type_id: Sport type ID.
        duration_hours: Optional duration in hours.
        tss: Optional planned TSS.
        description: Optional description.
        structure: Optional interval structure (nested object, NOT string).

    Returns:
        Dict with confirmation or error.
    """
    try:
        lib_validated = WorkoutIdInput(workout_id=library_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    if not name or not name.strip():
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Template name must not be empty.",
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
            "exerciseLibraryId": lib_validated.workout_id,
            "itemName": name.strip(),
            "workoutTypeFamilyId": sport_family_id,
            "workoutTypeValueId": sport_type_id,
        }
        if duration_hours is not None:
            payload["totalTimePlanned"] = duration_hours
        if tss is not None:
            payload["tssPlanned"] = tss
        if description:
            payload["description"] = description
        if structure is not None:
            # Library items use nested object, NOT double-serialised string
            payload["structure"] = structure

        endpoint = f"/exerciselibrary/v1/libraries/{lib_validated.workout_id}/items"
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        item_id = None
        if isinstance(response.data, dict):
            item_id = response.data.get("exerciseLibraryItemId", response.data.get("id"))

        return {
            "success": True,
            "item_id": item_id,
            "name": name.strip(),
            "library_id": lib_validated.workout_id,
        }


async def tp_update_library_item(
    library_id: str,
    item_id: str,
    name: str | None = None,
    duration_hours: float | None = None,
    tss: float | None = None,
    description: str | None = None,
    structure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Edit a workout template.

    Args:
        library_id: Library ID.
        item_id: Item ID.
        name: Optional new name.
        duration_hours: Optional duration in hours.
        tss: Optional planned TSS.
        description: Optional description.
        structure: Optional structure (nested object).

    Returns:
        Dict with confirmation or error.
    """
    try:
        lib_validated = WorkoutIdInput(workout_id=library_id)
        item_validated = WorkoutIdInput(workout_id=item_id)
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

        # GET existing items to find and merge
        get_endpoint = f"/exerciselibrary/v2/libraries/{lib_validated.workout_id}/items"
        get_response = await client.get(get_endpoint)

        if get_response.is_error:
            return {
                "isError": True,
                "error_code": get_response.error_code.value if get_response.error_code else "API_ERROR",
                "message": get_response.message,
            }

        data = get_response.data if isinstance(get_response.data, list) else []

        existing = None
        for item in data:
            iid = item.get("exerciseLibraryItemId", item.get("id"))
            if iid == item_validated.workout_id:
                existing = item
                break

        if existing is None:
            return {
                "isError": True,
                "error_code": "NOT_FOUND",
                "message": f"Item {item_validated.workout_id} not found.",
            }

        # Merge updates
        if name is not None:
            existing["itemName"] = name
        if duration_hours is not None:
            existing["totalTimePlanned"] = duration_hours
        if tss is not None:
            existing["tssPlanned"] = tss
        if description is not None:
            existing["description"] = description
        if structure is not None:
            existing["structure"] = structure

        put_endpoint = (
            f"/exerciselibrary/v1/libraries/{lib_validated.workout_id}"
            f"/items/{item_validated.workout_id}"
        )
        put_response = await client.put(put_endpoint, json=existing)

        if put_response.is_error:
            return {
                "isError": True,
                "error_code": put_response.error_code.value if put_response.error_code else "API_ERROR",
                "message": put_response.message,
            }

        return {
            "success": True,
            "message": f"Library item {item_validated.workout_id} updated.",
        }


async def tp_schedule_library_workout(
    library_id: str,
    item_id: str,
    date: str,
) -> dict[str, Any]:
    """Schedule a library template to a calendar date.

    Args:
        library_id: Library ID.
        item_id: Library item ID.
        date: Target date (YYYY-MM-DD).

    Returns:
        Dict with confirmation or error.
    """
    try:
        lib_validated = WorkoutIdInput(workout_id=library_id)
        item_validated = WorkoutIdInput(workout_id=item_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    try:
        from datetime import date as date_type

        date_type.fromisoformat(date)
    except ValueError:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Invalid date: {date}",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/commands/addworkoutfromlibraryitem"
        payload = {
            "exerciseLibraryId": lib_validated.workout_id,
            "exerciseLibraryItemId": item_validated.workout_id,
            "date": f"{date}T00:00:00",
        }
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": f"Library workout scheduled for {date}.",
            "date": date,
        }
