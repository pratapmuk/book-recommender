"""
Kalshi API Client with RSA Authentication

This module provides a client for interacting with the Kalshi API,
handling RSA signature authentication for all requests.
"""

import base64
import time
from typing import Optional
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class KalshiClient:
    """Client for interacting with the Kalshi API."""

    PROD_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
    DEMO_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"

    def __init__(
        self,
        api_key_id: str,
        private_key_path: str,
        demo: bool = False,
    ):
        """
        Initialize the Kalshi client.

        Args:
            api_key_id: Your Kalshi API key ID
            private_key_path: Path to your RSA private key PEM file
            demo: If True, use the demo API endpoint
        """
        self.api_key_id = api_key_id
        self.base_url = self.DEMO_BASE_URL if demo else self.PROD_BASE_URL
        self.private_key = self._load_private_key(private_key_path)
        self.session = requests.Session()

    def _load_private_key(self, path: str):
        """Load the RSA private key from a PEM file."""
        with open(path, "rb") as key_file:
            return serialization.load_pem_private_key(
                key_file.read(),
                password=None,
            )

    def _get_timestamp(self) -> str:
        """Get current timestamp in milliseconds."""
        return str(int(time.time() * 1000))

    def _sign_request(self, timestamp: str, method: str, path: str) -> str:
        """
        Create RSA signature for the request.

        Args:
            timestamp: Unix timestamp in milliseconds
            method: HTTP method (GET, POST, etc.)
            path: API path without query parameters

        Returns:
            Base64-encoded signature
        """
        # Remove query parameters from path for signing
        parsed = urlparse(path)
        path_without_query = parsed.path

        # Create message to sign: timestamp + method + path
        message = f"{timestamp}{method}{path_without_query}"

        # Sign using RSA-PSS with SHA256
        signature = self.private_key.sign(
            message.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

        return base64.b64encode(signature).decode("utf-8")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        """
        Make an authenticated request to the Kalshi API.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., "/portfolio/balance")
            params: Query parameters
            json_data: JSON body for POST/PUT requests

        Returns:
            Response JSON data
        """
        url = f"{self.base_url}{endpoint}"

        # Generate authentication headers
        timestamp = self._get_timestamp()
        # For signing, we need the full path including /trade-api/v2
        full_path = f"/trade-api/v2{endpoint}"
        signature = self._sign_request(timestamp, method, full_path)

        headers = {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }

        response = self.session.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_data,
        )

        response.raise_for_status()
        return response.json()

    def get_balance(self) -> dict:
        """
        Get account balance information.

        Returns:
            Dict containing balance and portfolio_value (in cents)
        """
        return self._make_request("GET", "/portfolio/balance")

    def get_positions(self, limit: int = 100, cursor: Optional[str] = None) -> dict:
        """
        Get current market positions.

        Args:
            limit: Maximum number of positions to return
            cursor: Pagination cursor

        Returns:
            Dict containing positions and pagination info
        """
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return self._make_request("GET", "/portfolio/positions", params=params)

    def get_portfolio_settlements(
        self, limit: int = 100, cursor: Optional[str] = None
    ) -> dict:
        """
        Get portfolio settlement history.

        Args:
            limit: Maximum number of settlements to return
            cursor: Pagination cursor

        Returns:
            Dict containing settlements and pagination info
        """
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return self._make_request("GET", "/portfolio/settlements", params=params)

    def get_fills(self, limit: int = 100, cursor: Optional[str] = None) -> dict:
        """
        Get trade fill history.

        Args:
            limit: Maximum number of fills to return
            cursor: Pagination cursor

        Returns:
            Dict containing fills and pagination info
        """
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return self._make_request("GET", "/portfolio/fills", params=params)

    def get_market(self, ticker: str) -> dict:
        """
        Get information about a specific market.

        Args:
            ticker: Market ticker symbol

        Returns:
            Dict containing market information
        """
        return self._make_request("GET", f"/markets/{ticker}")

    def get_event(self, event_ticker: str) -> dict:
        """
        Get information about a specific event.

        Args:
            event_ticker: Event ticker symbol

        Returns:
            Dict containing event information
        """
        return self._make_request("GET", f"/events/{event_ticker}")
