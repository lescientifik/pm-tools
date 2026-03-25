"""Shared HTTP client factory."""

from __future__ import annotations

import threading

import httpx

_DEFAULT_TIMEOUT = 30

_client: httpx.Client | None = None
_lock = threading.Lock()


def get_client(timeout: int = _DEFAULT_TIMEOUT) -> httpx.Client:
    """Get or create the shared HTTP client.

    When called with the default timeout (30s), returns a cached singleton.
    When called with a custom timeout, creates a new client each time.

    Uses double-checked locking to ensure thread-safe singleton creation.

    Args:
        timeout: Request timeout in seconds.

    Returns:
        An httpx.Client configured with follow_redirects=True.
    """
    global _client
    if timeout != _DEFAULT_TIMEOUT:
        return httpx.Client(timeout=timeout, follow_redirects=True)
    if _client is None:
        with _lock:
            if _client is None:
                _client = httpx.Client(timeout=timeout, follow_redirects=True)
    return _client
