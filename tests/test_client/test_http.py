"""Tests for HTTP client, including throttling and athlete ID caching."""

import time
from unittest.mock import AsyncMock

import pytest

from tp_mcp.client.http import MIN_REQUEST_INTERVAL, APIResponse, TPClient


class TestThrottling:
    """Tests for request throttling."""

    @pytest.mark.asyncio
    async def test_throttle_enforces_minimum_interval(self):
        """Throttle should enforce minimum interval between requests."""
        client = TPClient()

        # First call should not block
        start = time.monotonic()
        await client._throttle()
        first_duration = time.monotonic() - start
        assert first_duration < 0.05  # Should be nearly instant

        # Immediate second call should be delayed
        start = time.monotonic()
        await client._throttle()
        second_duration = time.monotonic() - start
        assert second_duration >= MIN_REQUEST_INTERVAL * 0.9  # Allow 10% tolerance

    @pytest.mark.asyncio
    async def test_throttle_no_delay_when_spaced(self):
        """Throttle should not delay when requests are naturally spaced."""
        client = TPClient()

        await client._throttle()

        # Wait longer than the interval
        import asyncio

        await asyncio.sleep(MIN_REQUEST_INTERVAL + 0.05)

        # Next call should not block
        start = time.monotonic()
        await client._throttle()
        duration = time.monotonic() - start
        assert duration < 0.05  # Should be nearly instant

    @pytest.mark.asyncio
    async def test_throttle_multiple_rapid_calls(self):
        """Multiple rapid calls should each be throttled."""
        client = TPClient()

        start = time.monotonic()

        # Make 4 rapid throttle calls
        for _ in range(4):
            await client._throttle()

        total_duration = time.monotonic() - start

        # Should take at least 3 * MIN_REQUEST_INTERVAL (first is instant, next 3 are throttled)
        expected_min = MIN_REQUEST_INTERVAL * 3 * 0.9  # 10% tolerance
        assert total_duration >= expected_min

    @pytest.mark.asyncio
    async def test_client_init_sets_last_request_time(self):
        """Client should initialize last request time to 0."""
        client = TPClient()
        assert client._last_request_time == 0.0


class TestEnsureAthleteId:
    """Tests for athlete ID caching via ensure_athlete_id."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        """Reset class-level caches between tests."""
        TPClient._cached_athlete_id = None
        TPClient._shared_token_cache = None
        yield
        TPClient._cached_athlete_id = None
        TPClient._shared_token_cache = None

    @pytest.mark.asyncio
    async def test_returns_cached_class_level_value(self):
        """Should return class-level cached athlete ID without API call."""
        TPClient._cached_athlete_id = 999
        client = TPClient()
        client.get = AsyncMock()  # should not be called

        result = await client.ensure_athlete_id()

        assert result == 999
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_from_api_and_caches(self):
        """Should fetch athlete ID from API and cache at class level."""
        client = TPClient()
        client.get = AsyncMock(return_value=APIResponse(success=True, data={"user": {"personId": 42}}))

        result = await client.ensure_athlete_id()

        assert result == 42
        assert TPClient._cached_athlete_id == 42
        assert client.athlete_id == 42

    @pytest.mark.asyncio
    async def test_falls_back_to_athletes_array(self):
        """Should use athletes[0].athleteId when personId is missing."""
        client = TPClient()
        client.get = AsyncMock(
            return_value=APIResponse(
                success=True,
                data={"user": {"athletes": [{"athleteId": 77}]}},
            )
        )

        result = await client.ensure_athlete_id()

        assert result == 77
        assert TPClient._cached_athlete_id == 77

    @pytest.mark.asyncio
    async def test_returns_none_on_api_failure(self):
        """Should return None when API call fails (no caching)."""
        client = TPClient()
        client.get = AsyncMock(return_value=APIResponse(success=False, message="Auth failed"))

        result = await client.ensure_athlete_id()

        assert result is None
        assert TPClient._cached_athlete_id is None

    @pytest.mark.asyncio
    async def test_class_cache_persists_across_instances(self):
        """Class-level cache should persist across TPClient instances."""
        client1 = TPClient()
        client1.get = AsyncMock(return_value=APIResponse(success=True, data={"user": {"personId": 123}}))
        await client1.ensure_athlete_id()

        # Second instance should use cached value without API call
        client2 = TPClient()
        client2.get = AsyncMock()

        result = await client2.ensure_athlete_id()

        assert result == 123
        client2.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_instance_athlete_id_if_set(self):
        """Should return instance-level athlete_id if already set."""
        client = TPClient()
        client.athlete_id = 555
        client.get = AsyncMock()

        result = await client.ensure_athlete_id()

        assert result == 555
        client.get.assert_not_called()


class TestSharedTokenCache:
    """Tests for shared TokenCache across TPClient instances."""

    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        """Reset shared token cache between tests."""
        TPClient._shared_token_cache = None
        yield
        TPClient._shared_token_cache = None

    def test_token_cache_shared_across_instances(self):
        """Multiple TPClient instances should share the same TokenCache."""
        client1 = TPClient()
        client2 = TPClient()
        assert client1._token_cache is client2._token_cache

    def test_token_cache_lazily_created(self):
        """Shared cache should be None until first TPClient is created."""
        assert TPClient._shared_token_cache is None
        TPClient()
        assert TPClient._shared_token_cache is not None
