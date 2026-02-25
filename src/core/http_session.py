"""HTTP session management for efficient request handling."""

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Global session cache
_sessions: dict[str, requests.Session] = {}


def get_session(
    name: str = "default",
    timeout: int = 30,
    max_retries: int = 3,
    backoff_factor: float = 0.5,
) -> requests.Session:
    """
    Get or create a cached HTTP session with retry logic.

    Sessions are reused to benefit from connection pooling and persistent cookies.

    Args:
        name: Session name for caching (use different names for different purposes)
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries for failed requests
        backoff_factor: Backoff factor for retries (delay = backoff_factor * (2 ** retry))

    Returns:
        Configured requests.Session instance
    """
    if name in _sessions:
        return _sessions[name]

    # Create new session
    session = requests.Session()

    # Configure retry strategy
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        raise_on_status=False,
    )

    # Mount adapter with retry strategy
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Set default headers
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )

    # Store timeout in session for convenience
    session._timeout = timeout  # type: ignore[attr-defined]

    _sessions[name] = session
    return session


def close_session(name: str = "default") -> None:
    """
    Close and remove a cached session.

    Args:
        name: Session name to close
    """
    if name in _sessions:
        _sessions[name].close()
        del _sessions[name]


def close_all_sessions() -> None:
    """Close all cached sessions."""
    for session in _sessions.values():
        session.close()
    _sessions.clear()


def request(
    method: str,
    url: str,
    session_name: str = "default",
    timeout: int | None = None,
    **kwargs: Any,
) -> requests.Response:
    """
    Make HTTP request using cached session.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        session_name: Session name for connection pooling
        timeout: Request timeout (uses session default if not specified)
        **kwargs: Additional arguments passed to requests

    Returns:
        requests.Response object
    """
    session = get_session(session_name)

    # Use provided timeout or session default
    if timeout is None:
        timeout = getattr(session, "_timeout", 30)  # type: ignore[attr-defined]

    return session.request(method, url, timeout=timeout, **kwargs)


def get(url: str, session_name: str = "default", **kwargs: Any) -> requests.Response:
    """Make GET request using cached session."""
    return request("GET", url, session_name=session_name, **kwargs)


def post(url: str, session_name: str = "default", **kwargs: Any) -> requests.Response:
    """Make POST request using cached session."""
    return request("POST", url, session_name=session_name, **kwargs)
