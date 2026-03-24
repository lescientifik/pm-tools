"""Tests for the shared HTTP client factory."""

import httpx

from pm_tools.http import get_client


class TestGetClient:
    """Tests for get_client() factory function."""

    def test_returns_httpx_client(self) -> None:
        """get_client() returns an httpx.Client instance."""
        client = get_client()
        assert isinstance(client, httpx.Client)

    def test_default_timeout_is_30(self) -> None:
        """Default client has a 30-second timeout."""
        client = get_client()
        assert client.timeout == httpx.Timeout(30)

    def test_follow_redirects_enabled(self) -> None:
        """Client follows redirects by default."""
        client = get_client()
        assert client.follow_redirects is True

    def test_custom_timeout(self) -> None:
        """A custom timeout can be passed."""
        client = get_client(timeout=60)
        assert client.timeout == httpx.Timeout(60)
