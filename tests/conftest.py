"""Pytest configuration and fixtures for TrainingPeaks MCP Server tests."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Test cookie (fake, for testing only)
TEST_COOKIE = "test_cookie_value_12345"
TEST_ATHLETE_ID = 123456
TEST_EMAIL = "test@example.com"


@pytest.fixture
def mock_keyring():
    """Mock keyring for testing credential storage."""
    storage = {}

    def mock_set_password(service, username, password):
        storage[(service, username)] = password

    def mock_get_password(service, username):
        return storage.get((service, username))

    def mock_delete_password(service, username):
        if (service, username) in storage:
            del storage[(service, username)]
        else:
            from keyring.errors import PasswordDeleteError

            raise PasswordDeleteError()

    with patch("tp_mcp.auth.keyring.keyring") as mock:
        mock.set_password = mock_set_password
        mock.get_password = mock_get_password
        mock.delete_password = mock_delete_password
        mock.get_keyring.return_value = MagicMock()
        mock.errors = MagicMock()
        mock.errors.PasswordDeleteError = Exception
        yield mock


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for testing API calls."""
    with patch("tp_mcp.client.http.httpx.AsyncClient") as mock:
        client_instance = AsyncMock()
        mock.return_value.__aenter__.return_value = client_instance
        mock.return_value.__aexit__.return_value = None
        yield client_instance


@pytest.fixture
def mock_credential():
    """Mock credential retrieval."""
    from tp_mcp.auth.keyring import CredentialResult

    with patch("tp_mcp.auth.storage.get_credential_keyring") as mock_keyring:
        with patch("tp_mcp.auth.storage.get_credential_encrypted") as mock_encrypted:
            with patch("tp_mcp.auth.storage.is_keyring_available") as mock_available:
                mock_available.return_value = True
                mock_keyring.return_value = CredentialResult(
                    success=True,
                    message="Credential retrieved",
                    cookie=TEST_COOKIE,
                )
                mock_encrypted.return_value = CredentialResult(
                    success=False,
                    message="No credential file",
                )
                yield


@pytest.fixture
def env_credential():
    """Set credential via environment variable for testing."""
    os.environ["TP_AUTH_COOKIE"] = TEST_COOKIE
    yield
    del os.environ["TP_AUTH_COOKIE"]


@pytest.fixture
def mock_api_responses():
    """Common mock API responses."""
    return {
        "token": {
            "athleteId": TEST_ATHLETE_ID,
            "userId": 999,
            "username": TEST_EMAIL,
        },
        "user": {
            "athleteId": TEST_ATHLETE_ID,
            "userId": 999,
            "username": TEST_EMAIL,
            "firstName": "Test",
            "lastName": "User",
            "accountType": "premium",
        },
        "workouts": [
            {
                "workoutId": 1001,
                "workoutDay": "2025-01-08",
                "title": "Test Workout",
                "workoutTypeFamilyId": "bike",
                "totalTimePlanned": 3600,
                "totalTime": 3500,
                "tssPlanned": 80,
                "tssActual": 75,
                "completed": True,
            },
            {
                "workoutId": 1002,
                "workoutDay": "2025-01-09",
                "title": "Planned Workout",
                "workoutTypeFamilyId": "run",
                "totalTimePlanned": 1800,
                "tssPlanned": 40,
                "completed": False,
            },
        ],
        "workout_detail": {
            "workoutId": 1001,
            "workoutDay": "2025-01-08",
            "title": "Test Workout",
            "workoutTypeFamilyId": "bike",
            "description": "Test description",
            "totalTimePlanned": 3600,
            "totalTime": 3500,
            "tssPlanned": 80,
            "tssActual": 75,
            "powerAverage": 200,
            "normalizedPower": 220,
            "heartRateAverage": 145,
            "completed": True,
        },
        "peaks": [
            {
                "durationSeconds": 5,
                "value": 800,
                "activityDate": "2025-01-05T00:00:00",
                "activityId": 5001,
                "workoutTypeFamilyId": "bike",
            },
            {
                "durationSeconds": 60,
                "value": 350,
                "activityDate": "2025-01-03T00:00:00",
                "activityId": 5002,
                "workoutTypeFamilyId": "bike",
            },
            {
                "durationSeconds": 1200,
                "value": 280,
                "activityDate": "2025-01-01T00:00:00",
                "activityId": 5003,
                "workoutTypeFamilyId": "bike",
            },
        ],
    }
