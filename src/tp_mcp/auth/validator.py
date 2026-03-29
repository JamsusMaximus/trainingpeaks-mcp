"""Cookie validation for TrainingPeaks authentication."""

from dataclasses import dataclass
from enum import Enum

import httpx

TP_API_BASE = "https://tpapi.trainingpeaks.com"
VALIDATION_ENDPOINT = "/users/v3/token"
VALIDATION_TIMEOUT = 10.0


class AuthStatus(Enum):
    """Authentication status codes."""

    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"
    NETWORK_ERROR = "network_error"
    NO_CREDENTIAL = "no_credential"


@dataclass
class AuthResult:
    """Result of authentication validation."""

    status: AuthStatus
    athlete_id: int | None = None
    user_id: int | None = None
    email: str | None = None
    message: str = ""

    @property
    def is_valid(self) -> bool:
        """Check if authentication is valid."""
        return self.status == AuthStatus.VALID


async def validate_auth(cookie: str) -> AuthResult:
    """Validate a TrainingPeaks auth cookie against the API.

    Args:
        cookie: The Production_tpAuth cookie value.

    Returns:
        AuthResult with validation status and user info if valid.
    """
    if not cookie or not cookie.strip():
        return AuthResult(
            status=AuthStatus.NO_CREDENTIAL, message="No credential provided"
        )

    headers = {
        "Cookie": f"Production_tpAuth={cookie.strip()}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=VALIDATION_TIMEOUT) as client:
            response = await client.get(
                f"{TP_API_BASE}{VALIDATION_ENDPOINT}", headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                token_info = data.get("token", {})
                access_token = token_info.get("access_token")

                # Token endpoint only returns the token, not user info.
                # Fetch user profile with the access token.
                email = None
                athlete_id = None
                user_id = None

                if access_token:
                    try:
                        user_resp = await client.get(
                            f"{TP_API_BASE}/users/v3/user",
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Accept": "application/json",
                            },
                        )
                        if user_resp.status_code == 200:
                            user_data = user_resp.json().get("user", {})
                            email = user_data.get("email")
                            user_id = user_data.get("userId")
                            athletes = user_data.get("athletes", [])
                            if athletes:
                                athlete_id = athletes[0].get("athleteId")
                            if not athlete_id:
                                athlete_id = user_data.get("personId")
                    except httpx.RequestError:
                        pass  # User info is best-effort; auth is still valid

                return AuthResult(
                    status=AuthStatus.VALID,
                    athlete_id=athlete_id,
                    user_id=user_id,
                    email=email,
                    message="Authentication valid",
                )
            elif response.status_code == 401:
                return AuthResult(
                    status=AuthStatus.EXPIRED,
                    message="Session expired. Please re-authenticate.",
                )
            elif response.status_code == 403:
                return AuthResult(
                    status=AuthStatus.INVALID,
                    message="Invalid credentials. Please re-authenticate.",
                )
            else:
                return AuthResult(
                    status=AuthStatus.INVALID,
                    message=f"Unexpected response: {response.status_code}",
                )

    except httpx.TimeoutException:
        return AuthResult(
            status=AuthStatus.NETWORK_ERROR,
            message="Request timed out. Check your network connection.",
        )
    except httpx.RequestError as e:
        return AuthResult(
            status=AuthStatus.NETWORK_ERROR,
            message=f"Network error: {e}",
        )


def validate_auth_sync(cookie: str) -> AuthResult:
    """Synchronous wrapper for validate_auth.

    Args:
        cookie: The Production_tpAuth cookie value.

    Returns:
        AuthResult with validation status and user info if valid.
    """
    import asyncio

    return asyncio.run(validate_auth(cookie))
