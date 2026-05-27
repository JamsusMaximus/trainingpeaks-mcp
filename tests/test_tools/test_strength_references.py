"""Tests for read-only TrainingPeaks strength exercise references."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools import strength_references
from tp_mcp.tools.strength_references import (
    build_youtube_reference_url,
    tp_search_strength_exercises,
)


@pytest.fixture(autouse=True)
def clear_strength_library_cache():
    strength_references._library_memory_cache = None
    yield
    strength_references._library_memory_cache = None


class TestSearchStrengthExercises:
    @pytest.mark.asyncio
    async def test_returns_trainingpeaks_video_reference_when_library_matches(self):
        """Matching TP library exercises should expose reference videos safely."""
        library_payload = {
            "data": {
                "exercises": [
                    {
                        "exerciseId": "131",
                        "title": "Back Squat",
                        "searchText": "barbell squat legs",
                        "videoUrl": "https://example.test/squat-demo",
                        "instructions": "Keep a neutral spine and brace.",
                        "searchAttributes": {
                            "primaryMuscleGroups": ["Quads", "Glutes"],
                            "secondaryMuscleGroups": ["Hamstrings"],
                        },
                    },
                    {
                        "exerciseId": "999",
                        "title": "Bench Press",
                        "searchText": "press chest",
                        "videoUrl": "https://example.test/bench-demo",
                    },
                ]
            }
        }

        detail_payload = {
            "data": {
                "id": "131",
                "title": "Back Squat",
                "videoUrl": "https://example.test/squat-demo",
                "instructions": "Keep a neutral spine and brace.",
                "primaryMuscleGroups": ["Quads", "Glutes"],
                "secondaryMuscleGroups": ["Hamstrings"],
            },
            "errors": {},
        }

        with patch("tp_mcp.tools.strength_references.StrengthReferenceClient") as mock_client:
            library_instance = AsyncMock()
            library_instance.get = AsyncMock(return_value=APIResponse(success=True, data=library_payload))
            detail_instance = AsyncMock()
            detail_instance.get = AsyncMock(return_value=APIResponse(success=True, data=detail_payload))
            mock_client.return_value.__aenter__.side_effect = [library_instance, detail_instance]

            result = await tp_search_strength_exercises("back squat")

        assert result["success"] is True
        assert result["source"] == "trainingpeaks_library"
        assert result["count"] == 1
        match = result["matches"][0]
        assert match == {
            "exercise_id": "131",
            "title": "Back Squat",
            "video_url": "https://example.test/squat-demo",
            "instructions": "Keep a neutral spine and brace.",
            "primary_muscle_groups": ["Quads", "Glutes"],
            "secondary_muscle_groups": ["Hamstrings"],
            "reference_source": "trainingpeaks_library",
        }
        assert result["youtube_fallback_url"] is None
        library_instance.get.assert_awaited_once_with("libraryContent")
        detail_instance.get.assert_awaited_once_with("exercises/131")

    @pytest.mark.asyncio
    async def test_returns_youtube_fallback_url_when_no_tp_match_exists(self):
        """Unknown movements should return a deterministic YouTube fallback search URL."""
        library_payload = {"data": {"exercises": [{"exerciseId": "1", "title": "Air Squat"}]}}

        with patch("tp_mcp.tools.strength_references.StrengthReferenceClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=APIResponse(success=True, data=library_payload))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_search_strength_exercises("tibialis raise")

        assert result["success"] is True
        assert result["source"] == "youtube_fallback"
        assert result["count"] == 0
        assert result["matches"] == []
        assert result["youtube_fallback_url"] == build_youtube_reference_url("tibialis raise")

    @pytest.mark.asyncio
    async def test_rejects_empty_query_without_calling_trainingpeaks(self):
        """Empty queries should fail locally and never make a TP request."""
        with patch("tp_mcp.tools.strength_references.StrengthReferenceClient") as mock_client:
            result = await tp_search_strength_exercises("  ")

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_non_integer_limit_without_calling_trainingpeaks(self):
        with patch("tp_mcp.tools.strength_references.StrengthReferenceClient") as mock_client:
            result = await tp_search_strength_exercises("squat", limit="many")

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "limit" in result["message"]
        mock_client.assert_not_called()


def test_build_youtube_reference_url_encodes_query_for_safe_manual_lookup():
    assert build_youtube_reference_url("single-leg RDL") == (
        "https://www.youtube.com/results?search_query=single-leg+RDL+exercise+technique"
    )
