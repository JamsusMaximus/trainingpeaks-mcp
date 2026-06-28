"""Athlete group tools — read-only (issue #69).

TrainingPeaks exposes a coach's "Athlete Groups" as TAGS in the API:

    GET /coaches/v2/coaches/{coachId}/tags

where ``coachId`` is the personId of the token owner. These are *coach-scoped*
endpoints — they describe how the coach has grouped their roster, so they do
NOT take an ``athlete`` target. Each tag looks like::

    {"id": 123, "coachId": 1135463, "name": "Group A",
     "athleteIds": [201, 202], "isDefault": false}

This module exposes listing only. Creating / updating / deleting groups is a
separate (write) effort: the POST/PUT/DELETE signatures must first be verified
against the live API, because TP write bodies are easy to get wrong (the
library endpoints, for instance, needed ``libraryName`` rather than ``name``
and an explicit ``ownerId``).
"""

import logging
from typing import Any

from tp_mcp.client import TPClient

logger = logging.getLogger("tp-mcp")

_TAGS_ENDPOINT = "/coaches/v2/coaches/{coach_id}/tags"


async def _coach_id(client: TPClient) -> int | None:
    """personId of the token owner — the ``coachId`` for group endpoints.

    Groups are coach-scoped, so this deliberately ignores any athlete override
    (unlike ``ensure_athlete_id``): the grouping belongs to the coach, not to a
    targeted athlete.
    """
    user_data = await client._get_user_data()
    if not user_data:
        return None
    return user_data.get("personId")


def _slim_group(tag: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": tag.get("id"),
        "name": tag.get("name", ""),
        "athlete_count": len(tag.get("athleteIds") or []),
        "is_default": tag.get("isDefault", False),
    }


async def tp_list_groups() -> dict[str, Any]:
    """List the coach's athlete groups (TP tags).

    Returns:
        Dict with a ``groups`` list of ``{id, name, athlete_count, is_default}``.
    """
    async with TPClient() as client:
        coach_id = await _coach_id(client)
        if not coach_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not resolve the coach account. Re-authenticate.",
            }

        response = await client.get(_TAGS_ENDPOINT.format(coach_id=coach_id))
        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        data = response.data if isinstance(response.data, list) else []
        groups = [_slim_group(t) for t in data if isinstance(t, dict)]
        return {"groups": groups, "count": len(groups)}


async def tp_list_athletes_in_group(group_id: str) -> dict[str, Any]:
    """List the athletes in one group, resolving athleteIds to names.

    Args:
        group_id: The group (tag) ID from tp_list_groups.

    Returns:
        Dict with the group name and an ``athletes`` list of
        ``{athlete_id, name}`` (names joined from the coach's roster).
    """
    try:
        gid = int(group_id)
    except (TypeError, ValueError):
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"group_id must be a numeric ID, got {group_id!r}.",
        }

    async with TPClient() as client:
        user_data = await client._get_user_data()
        if not user_data or not user_data.get("personId"):
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not resolve the coach account. Re-authenticate.",
            }
        coach_id = user_data.get("personId")

        response = await client.get(_TAGS_ENDPOINT.format(coach_id=coach_id))
        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        data = response.data if isinstance(response.data, list) else []
        tag = next((t for t in data
                    if isinstance(t, dict) and t.get("id") == gid), None)
        if tag is None:
            return {
                "isError": True,
                "error_code": "NOT_FOUND",
                "message": f"No athlete group with id {gid}. Use tp_list_groups.",
            }

        # Join athleteIds against the coach's roster (from /users/v3/user, the
        # same source tp_list_athletes uses) to attach names.
        roster = {a.get("athleteId"): a for a in user_data.get("athletes", [])}
        athletes = []
        for aid in (tag.get("athleteIds") or []):
            a = roster.get(aid)
            # name is None when the athlete is in the group but not in this
            # account's roster
            name = f"{a.get('firstName', '')} {a.get('lastName', '')}".strip() if a is not None else None
            athletes.append({"athlete_id": aid, "name": name})
        athletes.sort(key=lambda x: (x["name"] or "").lower())

        return {
            "group_id": gid,
            "name": tag.get("name", ""),
            "athletes": athletes,
            "count": len(athletes),
        }
