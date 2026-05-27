"""Read-only TrainingPeaks strength exercise reference tools.

This module supports only exercise-library lookup for public/reference-style
content such as videos, instructions, and muscle groups. It does not create,
update, delete, or inspect athlete strength workout prescriptions.
"""

from __future__ import annotations

import asyncio
import json as json_module
import logging
import re
import time
from typing import Any, cast
from urllib.parse import quote_plus

import httpx

from tp_mcp.client.http import (
    DEFAULT_TIMEOUT,
    MIN_REQUEST_INTERVAL,
    APIResponse,
    ErrorCode,
    TPClient,
)

logger = logging.getLogger("tp-mcp.strength_references")

STRENGTH_API_BASE = "https://api.peakswaresb.com"
STRENGTH_PREFIX = "/rx/activity/v1"
_YOUTUBE_REFERENCE_SUFFIX = "exercise technique"
_library_memory_cache: dict[str, Any] | None = None


class StrengthReferenceClient:
    """Minimal read-only client for the TrainingPeaks strength reference API."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = STRENGTH_API_BASE
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0.0
        self._token_cache = TPClient._get_token_cache()
        self._tp_client = TPClient(timeout=timeout)

    async def __aenter__(self) -> StrengthReferenceClient:
        await self._ensure_client()
        await self._tp_client._ensure_client()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        await self._tp_client.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token_cache.access_token}",
            "Accept": "application/json",
        }

    async def get(self, endpoint: str) -> APIResponse:
        """Make a read-only GET request against the strength API."""
        await self._ensure_client()
        assert self._client is not None

        token_result = await self._tp_client._ensure_access_token()
        if not token_result.success:
            return token_result

        await self._throttle()
        path = endpoint if endpoint.startswith("/") else f"{STRENGTH_PREFIX}/{endpoint}"
        url = f"{self.base_url}{path}"

        try:
            response = await self._client.get(url, headers=self._headers())
        except httpx.TimeoutException:
            return APIResponse(
                success=False,
                error_code=ErrorCode.NETWORK_ERROR,
                message=f"Request timed out: GET {url}",
            )
        except httpx.RequestError as e:
            return APIResponse(
                success=False,
                error_code=ErrorCode.NETWORK_ERROR,
                message=f"Network error: {e}",
            )

        if response.status_code == 401:
            return APIResponse(
                success=False,
                error_code=ErrorCode.AUTH_EXPIRED,
                message="Session expired or invalid. Run 'tp-mcp auth' to re-authenticate.",
            )
        if response.status_code == 404:
            return APIResponse(
                success=False,
                error_code=ErrorCode.NOT_FOUND,
                message=f"Resource not found: {endpoint}",
            )
        if response.status_code == 429:
            return APIResponse(
                success=False,
                error_code=ErrorCode.RATE_LIMITED,
                message="Rate limit exceeded. Back off and retry.",
            )
        if not (200 <= response.status_code < 300):
            return APIResponse(
                success=False,
                error_code=ErrorCode.API_ERROR,
                message=f"API error {response.status_code} on GET {endpoint}: {response.text[:500]}",
            )

        try:
            data = response.json() if response.text else None
        except json_module.JSONDecodeError as e:
            return APIResponse(
                success=False,
                error_code=ErrorCode.API_ERROR,
                message=f"Invalid JSON in response: {e}",
            )
        return APIResponse(success=True, data=data)


def build_youtube_reference_url(query: str) -> str:
    """Build a manual YouTube fallback search URL without calling YouTube."""
    return "https://www.youtube.com/results?search_query=" + quote_plus(
        f"{query.strip()} {_YOUTUBE_REFERENCE_SUFFIX}"
    )


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _exercises_from_library(library_payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = library_payload.get("data") or {}
    exercises = data.get("exercises") or []
    return [ex for ex in exercises if isinstance(ex, dict)]


def _score_exercise(query: str, exercise: dict[str, Any]) -> int | None:
    needle = _norm(query)
    tokens = needle.split()
    title = _norm(str(exercise.get("title") or ""))
    search_text = _norm(str(exercise.get("searchText") or ""))
    haystack = f"{title} {search_text}"
    if not tokens or not all(token in haystack for token in tokens):
        return None
    if title == needle:
        score = 100
    elif title.startswith(needle):
        score = 80
    elif needle in title:
        score = 60
    else:
        score = 40
    return score - min(len(title), 30) // 5


def _public_reference(exercise: dict[str, Any], detail: dict[str, Any] | None = None) -> dict[str, Any]:
    attrs = exercise.get("searchAttributes") or {}
    detail_data = (detail or {}).get("data") if isinstance(detail, dict) else None
    detail_data = detail_data if isinstance(detail_data, dict) else {}

    instructions = detail_data.get("instructions") or exercise.get("instructions")
    primary = detail_data.get("primaryMuscleGroups") or attrs.get("primaryMuscleGroups", [])
    secondary = detail_data.get("secondaryMuscleGroups") or attrs.get("secondaryMuscleGroups", [])
    return {
        "exercise_id": str(exercise.get("exerciseId") or detail_data.get("id")),
        "title": detail_data.get("title") or exercise.get("title"),
        "video_url": detail_data.get("videoUrl") or exercise.get("videoUrl"),
        "instructions": instructions if isinstance(instructions, str) else None,
        "primary_muscle_groups": primary if isinstance(primary, list) else [],
        "secondary_muscle_groups": secondary if isinstance(secondary, list) else [],
        "reference_source": "trainingpeaks_library",
    }


async def _load_strength_library() -> dict[str, Any]:
    """Load the TP strength exercise library using memory cache only.

    Privacy note: this deliberately avoids persisting API payloads to disk. The
    cache lives only for the current process.
    """
    global _library_memory_cache
    if _library_memory_cache is not None:
        return _library_memory_cache

    async with StrengthReferenceClient() as client:
        response = await client.get("libraryContent")
    if not response.success or not isinstance(response.data, dict):
        message = response.message or "Could not load strength exercise library."
        raise RuntimeError(message)
    _library_memory_cache = cast("dict[str, Any]", response.data)
    return _library_memory_cache


async def _load_exercise_detail(exercise_id: str) -> dict[str, Any] | None:
    """Load public/reference detail for a TP library exercise.

    Returns only in-memory data and tolerates detail failures so lookup can still
    return library matches from the index.
    """
    async with StrengthReferenceClient() as client:
        response = await client.get(f"exercises/{exercise_id}")
    if not response.success or not isinstance(response.data, dict):
        return None
    return cast("dict[str, Any]", response.data)


async def tp_search_strength_exercises(query: str, limit: int = 10) -> dict[str, Any]:
    """Search TP's strength exercise library for reference videos/instructions.

    This is read-only and returns TrainingPeaks library matches when available.
    If no library match is found, it returns a deterministic YouTube search URL
    for manual/reference-video fallback without making a YouTube network call.
    """
    if not query or not query.strip():
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "query must be non-empty.",
        }
    try:
        requested_limit = int(limit)
    except (TypeError, ValueError):
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "limit must be an integer.",
        }
    safe_limit = max(1, min(requested_limit, 25))

    try:
        library = await _load_strength_library()
    except RuntimeError as e:
        return {
            "isError": True,
            "error_code": "API_ERROR",
            "message": str(e),
        }

    scored: list[tuple[int, dict[str, Any]]] = []
    for exercise in _exercises_from_library(library):
        score = _score_exercise(query, exercise)
        if score is not None:
            scored.append((score, exercise))
    scored.sort(key=lambda item: item[0], reverse=True)

    matches = []
    for _score, exercise in scored[:safe_limit]:
        exercise_id = str(exercise.get("exerciseId") or "")
        detail = await _load_exercise_detail(exercise_id) if exercise_id else None
        matches.append(_public_reference(exercise, detail))
    if matches:
        return {
            "success": True,
            "source": "trainingpeaks_library",
            "query": query,
            "count": len(matches),
            "matches": matches,
            "youtube_fallback_url": None,
        }

    return {
        "success": True,
        "source": "youtube_fallback",
        "query": query,
        "count": 0,
        "matches": [],
        "youtube_fallback_url": build_youtube_reference_url(query),
    }
