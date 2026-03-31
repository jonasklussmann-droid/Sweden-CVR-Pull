"""OAuth2 client credentials authentication for Bolagsverket API."""

import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_URL = "https://portal.api.bolagsverket.se/oauth2/token"


class OAuth2Client:
    """Handles OAuth2 Client Credentials Grant for Bolagsverket API."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_url: str = DEFAULT_TOKEN_URL,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0
        self._session = requests.Session()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=16),
        reraise=True,
    )
    def _request_token(self) -> dict:
        """Request a new access token from the OAuth2 token endpoint."""
        logger.info("Requesting new OAuth2 access token from %s", self.token_url)
        response = self._session.post(
            self.token_url,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        response.raise_for_status()
        token_data = response.json()
        logger.info("Successfully obtained access token")
        return token_data

    def get_token(self) -> str:
        """Get a valid access token, refreshing if expired."""
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        token_data = self._request_token()
        self._access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self._token_expiry = time.time() + expires_in
        return self._access_token

    def get_auth_header(self) -> dict[str, str]:
        """Get the Authorization header with a valid bearer token."""
        token = self.get_token()
        return {"Authorization": f"Bearer {token}"}
