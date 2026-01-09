"""HTTP client wrapper for TrainingPeaks API."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from tp_mcp.auth import clear_credential, get_credential

TP_API_BASE = "https://tpapi.trainingpeaks.com"
DEFAULT_TIMEOUT = 30.0


class APIError(Exception):
    """Base exception for API errors."""

    pass


class AuthenticationError(APIError):
    """Authentication failed or expired."""

    pass


class NotFoundError(APIError):
    """Resource not found."""

    pass


class RateLimitError(APIError):
    """Rate limit exceeded."""

    pass


class ErrorCode(Enum):
    """Error codes for API responses."""

    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_INVALID = "AUTH_INVALID"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    PREMIUM_REQUIRED = "PREMIUM_REQUIRED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    API_ERROR = "API_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"


@dataclass
class APIResponse:
    """Wrapper for API responses."""

    success: bool
    data: dict[str, Any] | list[Any] | None = None
    error_code: ErrorCode | None = None
    message: str = ""

    @property
    def is_error(self) -> bool:
        """Check if response is an error."""
        return not self.success


class TPClient:
    """Async HTTP client for TrainingPeaks API.

    Handles authentication, error handling, and response parsing.
    """

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        """Initialize the client.

        Args:
            timeout: Request timeout in seconds.
        """
        self.base_url = TP_API_BASE
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._athlete_id: int | None = None

    async def __aenter__(self) -> "TPClient":
        """Enter async context."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context."""
        await self.close()

    async def _ensure_client(self) -> None:
        """Ensure the HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_headers(self, cookie: str) -> dict[str, str]:
        """Get request headers with authentication.

        Args:
            cookie: The Production_tpAuth cookie value.

        Returns:
            Headers dict.
        """
        return {
            "Cookie": f"Production_tpAuth={cookie}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> APIResponse:
        """Make an authenticated API request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            endpoint: API endpoint (e.g., "/users/v3/token").
            json: JSON body for POST/PUT requests.
            params: Query parameters.

        Returns:
            APIResponse with data or error.
        """
        await self._ensure_client()
        assert self._client is not None

        # Get credential
        cred = get_credential()
        if not cred.success or not cred.cookie:
            return APIResponse(
                success=False,
                error_code=ErrorCode.AUTH_INVALID,
                message="No credential stored. Run 'tp-mcp auth' to authenticate.",
            )

        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(cred.cookie)

        try:
            response = await self._client.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                params=params,
            )

            return self._handle_response(response)

        except httpx.TimeoutException:
            return APIResponse(
                success=False,
                error_code=ErrorCode.NETWORK_ERROR,
                message="Request timed out. Check your network connection.",
            )
        except httpx.RequestError as e:
            return APIResponse(
                success=False,
                error_code=ErrorCode.NETWORK_ERROR,
                message=f"Network error: {e}",
            )

    def _handle_response(self, response: httpx.Response) -> APIResponse:
        """Handle API response and convert to APIResponse.

        Args:
            response: The httpx response.

        Returns:
            APIResponse with data or error.
        """
        if response.status_code == 200:
            try:
                data = response.json()
                return APIResponse(success=True, data=data)
            except Exception:
                return APIResponse(success=True, data=None)

        if response.status_code == 201:
            try:
                data = response.json()
                return APIResponse(success=True, data=data)
            except Exception:
                return APIResponse(success=True, data=None)

        if response.status_code == 401:
            # Clear stored credential on 401
            clear_credential()
            return APIResponse(
                success=False,
                error_code=ErrorCode.AUTH_EXPIRED,
                message="Session expired. Run 'tp-mcp auth' to re-authenticate.",
            )

        if response.status_code == 403:
            return APIResponse(
                success=False,
                error_code=ErrorCode.AUTH_INVALID,
                message="Access denied. Check your permissions or re-authenticate.",
            )

        if response.status_code == 404:
            return APIResponse(
                success=False,
                error_code=ErrorCode.NOT_FOUND,
                message="Resource not found.",
            )

        if response.status_code == 429:
            return APIResponse(
                success=False,
                error_code=ErrorCode.RATE_LIMITED,
                message="Rate limited. Please wait before making more requests.",
            )

        # Generic error
        return APIResponse(
            success=False,
            error_code=ErrorCode.API_ERROR,
            message=f"API error: {response.status_code}",
        )

    async def get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> APIResponse:
        """Make a GET request.

        Args:
            endpoint: API endpoint.
            params: Query parameters.

        Returns:
            APIResponse.
        """
        return await self._request("GET", endpoint, params=params)

    async def post(
        self, endpoint: str, json: dict[str, Any] | None = None
    ) -> APIResponse:
        """Make a POST request.

        Args:
            endpoint: API endpoint.
            json: JSON body.

        Returns:
            APIResponse.
        """
        return await self._request("POST", endpoint, json=json)

    async def put(
        self, endpoint: str, json: dict[str, Any] | None = None
    ) -> APIResponse:
        """Make a PUT request.

        Args:
            endpoint: API endpoint.
            json: JSON body.

        Returns:
            APIResponse.
        """
        return await self._request("PUT", endpoint, json=json)

    async def delete(self, endpoint: str) -> APIResponse:
        """Make a DELETE request.

        Args:
            endpoint: API endpoint.

        Returns:
            APIResponse.
        """
        return await self._request("DELETE", endpoint)

    @property
    def athlete_id(self) -> int | None:
        """Get the cached athlete ID."""
        return self._athlete_id

    @athlete_id.setter
    def athlete_id(self, value: int | None) -> None:
        """Set the athlete ID."""
        self._athlete_id = value
