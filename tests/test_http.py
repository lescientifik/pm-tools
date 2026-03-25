"""Tests for the shared HTTP client factory."""

import threading
import time
from unittest.mock import patch

import httpx

import pm_tools.http
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

    def test_singleton_is_thread_safe(self) -> None:
        """All threads get the same singleton even under contention."""
        # Reset global singleton so we start fresh
        pm_tools.http._client = None

        num_threads = 20
        barrier = threading.Barrier(num_threads)
        results: list[httpx.Client] = [None] * num_threads  # type: ignore[list-item]
        original_init = httpx.Client.__init__

        def slow_init(self: httpx.Client, *args: object, **kwargs: object) -> None:
            """Inject a delay to widen the race window."""
            time.sleep(0.1)
            original_init(self, *args, **kwargs)

        def worker(index: int) -> None:
            barrier.wait()
            results[index] = get_client()

        with patch.object(httpx.Client, "__init__", slow_init):
            threads = [
                threading.Thread(target=worker, args=(i,))
                for i in range(num_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # Every thread must have received the exact same instance
        assert all(r is results[0] for r in results), (
            f"Expected 1 instance, got {len(set(id(r) for r in results))} distinct"
        )

        # Clean up: reset singleton for other tests
        pm_tools.http._client = None
