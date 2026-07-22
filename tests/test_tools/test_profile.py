"""Tests for tp_get_profile, including coach athlete targeting (#68)."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.context import athlete_override
from tp_mcp.client.http import APIResponse
from tp_mcp.tools.profile import (
    _account_fields,
    _derive_tier,
    tp_get_profile,
    tp_list_athletes,
)

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
        # Premium-ish fields (passthrough). Active premium = future expireOn.
        "expireOn": "2099-01-01T00:00:00",
        "athleteType": 1,
        "userType": 1,
        "premiumTrial": None,
        "premiumTrialDaysRemaining": 0,
        "downgradeAllowed": True,
        "downgradeAllowedOn": "2099-01-01T00:00:00",
        "lastUpgradeOn": "2025-01-01T00:00:00",
    },
    {
        "athleteId": 201,
        "firstName": "Charlotte",
        "lastName": "Horton",
        "email": "charlotte@example.com",
        "coachedBy": 100,
        "expireOn": "2017-01-28T03:17:00",   # expired
        "athleteType": 4,
        "userType": 6,
        "premiumTrial": None,
        "premiumTrialDaysRemaining": 0,
        "downgradeAllowed": False,
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
        # Raw account fields ARE surfaced under `account` for caller analysis.
        assert result["account"]["expire_on"] == "2017-01-28T03:17:00"
        assert result["account"]["expired"] is True
        assert result["account"]["athlete_type"] == 4
        assert result["account"]["user_type"] == 6
        # …plus the derived tier («Account Type» label in TP UI).
        assert result["account"]["tier"] == "basic"
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


class TestDeriveTier:
    """Verified live against the TP UI «Account Type» label on 10 athletes
    spanning all four states (2026-06-28 sync). Order matters: trial > active
    subscription > lapsed-tier-1 (coach-paid) > default basic."""

    def test_premium_self_paid_active_subscription(self):
        # Active personal subscription: future expireOn.
        assert _derive_tier(expired=False, user_type=4, trial_days=0) == "premium_self"

    def test_premium_coach_paid_lapsed_personal_tier_1(self):
        # Coach-paid: personal premium lapsed, tier-1 user type persists.
        assert _derive_tier(expired=True, user_type=1, trial_days=0) == "premium_coach"

    def test_basic_lapsed_non_premium_tier(self):
        # Basic: lapsed with non-premium user_type (6).
        assert _derive_tier(expired=True, user_type=6, trial_days=0) == "basic"

    def test_basic_with_other_non_premium_user_type(self):
        # Anything not 1 is basic when expired (saw 6/4/2 etc. in the wild).
        assert _derive_tier(expired=True, user_type=4, trial_days=0) == "basic"

    def test_premium_trial_wins_over_other_signals(self):
        # Trial stays active even though expireOn just lapsed.
        assert _derive_tier(expired=True, user_type=4, trial_days=4) == "premium_trial"
        assert _derive_tier(expired=False, user_type=4, trial_days=7) == "premium_trial"

    def test_none_when_expired_unknown(self):
        assert _derive_tier(expired=None, user_type=6, trial_days=0) is None


class TestAccountFields:
    """`_account_fields` is a passthrough surface for premium/account flags
    whose semantics aren't documented by TP — these only pin the SHAPE so the
    keys don't drift, plus the ONE derived bit (`expired`)."""

    def test_passes_through_known_fields(self):
        out = _account_fields({
            "expireOn": "2099-01-01T00:00:00",
            "athleteType": 1, "userType": 1,
            "premiumTrial": "trial", "premiumTrialDaysRemaining": 5,
            "downgradeAllowed": True, "downgradeAllowedOn": "2099-01-01",
            "lastUpgradeOn": "2025-01-01",
        })
        assert out["expire_on"] == "2099-01-01T00:00:00"
        assert out["athlete_type"] == 1 and out["user_type"] == 1
        assert out["premium_trial"] == "trial"
        assert out["premium_trial_days_remaining"] == 5
        assert out["downgrade_allowed"] is True
        assert out["downgrade_allowed_on"] == "2099-01-01"
        assert out["last_upgrade_on"] == "2025-01-01"

    def test_expired_derived_from_expireon(self):
        assert _account_fields({"expireOn": "2017-01-28T03:17:00"})["expired"] is True
        assert _account_fields({"expireOn": "2099-12-31T23:59:00"})["expired"] is False

    def test_missing_or_bad_expireon_keeps_expired_none(self):
        assert _account_fields({})["expired"] is None
        assert _account_fields({"expireOn": ""})["expired"] is None
        assert _account_fields({"expireOn": "not-a-date"})["expired"] is None


class TestListAthletesShape:
    @pytest.mark.asyncio
    async def test_list_athletes_surfaces_account_block(self):
        """tp_list_athletes now carries an `account` sub-dict per entry — raw
        passthrough so a caller can correlate fields against known coach-paid
        vs self-paid vs free athletes."""
        instance = _mock_client(
            _get_user_data={"personId": 100, "email": "stevan@example.com",
                            "athletes": ROSTER},
        )
        with patch("tp_mcp.tools.profile.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = instance
            result = await tp_list_athletes()

        assert len(result["athletes"]) == 2
        coach, charlotte = result["athletes"]
        assert coach["is_self"] is True and coach["athlete_id"] == 100
        # account block carries the raw fields + the derived tier
        assert coach["account"]["athlete_type"] == 1
        assert coach["account"]["expired"] is False     # future expireOn
        assert coach["account"]["tier"] == "premium_self"
        assert charlotte["account"]["athlete_type"] == 4
        assert charlotte["account"]["expired"] is True   # 2017
        assert charlotte["account"]["tier"] == "basic"
