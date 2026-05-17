"""Tests for tp_get_profile, including coach athlete targeting (#68)."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.context import athlete_override
from tp_mcp.client.http import APIResponse
from tp_mcp.tools.profile import tp_get_profile

OWN_USER_RESPONSE = {
    "user": {
        "personId": 100,
        "firstName": "Stevan",
        "lastName": "Coach",
        "email": "stevan@example.com",
        "settings": {"account": {"isPremium": True}},
    }
}

ROSTER = [
    {
        "athleteId": 100,
        "firstName": "Stevan",
        "lastName": "Coach",
        "email": "stevan@example.com",
        "coachedBy": 100,
    },
    {
        "athleteId": 201,
        "firstName": "Charlotte",
        "lastName": "Horton",
        "email": "charlotte@example.com",
        "coachedBy": 100,
    },
]


def _mock_client(**methods):
    """Patch profile.TPClient and return the mocked client instance."""
    mock_instance = AsyncMock()
    for name, value in methods.items():
        setattr(mock_instance, name, AsyncMock(return_value=value))
    return mock_instance


class TestGetProfileSelf:
    @pytest.mark.asyncio
    async def test_no_override_returns_own_profile(self):
        """With no athlete override, the logged-in user's profile is returned."""
        instance = _mock_client(get=APIResponse(success=True, data=OWN_USER_RESPONSE))

        with patch("tp_mcp.tools.profile.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = instance
            result = await tp_get_profile()

        assert result["athlete_id"] == 100
        assert result["name"] == "Stevan Coach"
        assert result["email"] == "stevan@example.com"
        assert result["account_type"] == "premium"
        instance.get.assert_awaited_once_with("/users/v3/user")


class TestGetProfileTargetedAthlete:
    @pytest.mark.asyncio
    async def test_override_returns_targeted_athlete(self):
        """With an athlete override, the targeted roster athlete is returned (#68)."""
        instance = _mock_client(
            ensure_athlete_id=201,
            _get_user_data={"athletes": ROSTER},
        )

        with patch("tp_mcp.tools.profile.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = instance
            token = athlete_override.set("Charlotte Horton")
            try:
                result = await tp_get_profile()
            finally:
                athlete_override.reset(token)

        assert result["athlete_id"] == 201
        assert result["name"] == "Charlotte Horton"
        assert result["email"] == "charlotte@example.com"
        # Premium status is not knowable for a coached athlete.
        assert result["account_type"] is None
        # The logged-in user's profile endpoint must not be the source here.
        instance.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unresolved_athlete_returns_not_found(self):
        """An override that resolves to nothing returns NOT_FOUND, not the coach."""
        instance = _mock_client(ensure_athlete_id=None)

        with patch("tp_mcp.tools.profile.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = instance
            token = athlete_override.set("Nobody")
            try:
                result = await tp_get_profile()
            finally:
                athlete_override.reset(token)

        assert result["isError"] is True
        assert result["error_code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_athlete_not_in_roster_returns_not_found(self):
        """A resolved ID absent from the roster returns NOT_FOUND."""
        instance = _mock_client(
            ensure_athlete_id=999,
            _get_user_data={"athletes": ROSTER},
        )

        with patch("tp_mcp.tools.profile.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = instance
            token = athlete_override.set("999")
            try:
                result = await tp_get_profile()
            finally:
                athlete_override.reset(token)

        assert result["isError"] is True
        assert result["error_code"] == "NOT_FOUND"
