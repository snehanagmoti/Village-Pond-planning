"""Shared bounded HTTP client with retry and backoff behavior."""

import asyncio
from typing import Any, Optional

import httpx

from config import get_settings

_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        settings = get_settings()
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.external_timeout_seconds),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def get_with_retries(
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
) -> httpx.Response:
    settings = get_settings()
    last_error: Exception | None = None
    for attempt in range(settings.external_retry_count + 1):
        response: httpx.Response | None = None
        try:
            response = await get_http_client().get(url, params=params, headers=headers)
            if response.status_code < 500 and response.status_code != 429:
                return response
            last_error = httpx.HTTPStatusError(
                f"upstream returned {response.status_code}",
                request=response.request,
                response=response,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
        if attempt < settings.external_retry_count:
            delay = 0.25 * (2**attempt)
            if response is not None and response.status_code == 429:
                delay = max(1.0, delay)
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        pass
            max_delay = getattr(settings, "external_retry_max_delay_seconds", 30.0)
            await asyncio.sleep(min(delay, max_delay))
    if last_error is None:
        raise RuntimeError("upstream request failed")
    raise last_error
