from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from config import Settings
from services import cache as cache_module
from services import geocoding, http_client
from services.cache import TTLCache
from services.quality import UpstreamDataError
from services.rate_limit import SlidingWindowLimiter


def test_ttl_cache_is_bounded_copied_and_expires(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: clock[0])
    cache = TTLCache(maxsize=2, ttl_seconds=10)
    original = {"values": [1]}
    cache.set("a", original)
    original["values"].append(2)
    assert cache.get("a") == {"values": [1]}

    cache.set("b", {"value": 2})
    cache.set("c", {"value": 3})
    assert cache.get("a") is None
    clock[0] = 111.0
    assert cache.get("b") is None
    cache.clear()


def test_disabled_cache_stores_nothing():
    cache = TTLCache(maxsize=1, ttl_seconds=0)
    cache.set("key", "value")
    assert cache.get("key") is None


@pytest.mark.anyio
async def test_rate_limiter_returns_retry_after_and_cleans_old_keys(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("services.rate_limit.time.monotonic", lambda: clock[0])
    limiter = SlidingWindowLimiter(max_keys=2)
    request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.1"))
    await limiter.enforce(request, "analysis", 1, window_seconds=10)
    with pytest.raises(HTTPException) as error:
        await limiter.enforce(request, "analysis", 1, window_seconds=10)
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "10"

    clock[0] = 111.0
    await limiter.enforce(request, "analysis", 1, window_seconds=10)
    assert len(limiter._events) <= 2


class _FakeClient:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.is_closed = False

    async def get(self, *args, **kwargs):
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def aclose(self):
        self.is_closed = True


async def _async_none():
    return None


@pytest.mark.anyio
async def test_http_retry_then_success(monkeypatch):
    request = httpx.Request("GET", "https://example.test/data")
    responses = [
        httpx.Response(503, request=request),
        httpx.Response(200, request=request, json={"ok": True}),
    ]
    client = _FakeClient(responses)
    monkeypatch.setattr(http_client, "get_http_client", lambda: client)
    monkeypatch.setattr(
        http_client,
        "get_settings",
        lambda: SimpleNamespace(external_retry_count=1),
    )
    monkeypatch.setattr(http_client.asyncio, "sleep", lambda *_: _async_none())
    response = await http_client.get_with_retries("https://example.test/data")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_http_retry_honors_retry_after_for_429(monkeypatch):
    request = httpx.Request("GET", "https://example.test/data")
    responses = [
        httpx.Response(429, request=request, headers={"Retry-After": "3"}),
        httpx.Response(200, request=request, json={"ok": True}),
    ]
    client = _FakeClient(responses)
    sleeps = []

    async def record_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(http_client, "get_http_client", lambda: client)
    monkeypatch.setattr(
        http_client,
        "get_settings",
        lambda: SimpleNamespace(
            external_retry_count=1,
            external_retry_max_delay_seconds=30.0,
        ),
    )
    monkeypatch.setattr(http_client.asyncio, "sleep", record_sleep)
    response = await http_client.get_with_retries("https://example.test/data")
    assert response.status_code == 200
    assert sleeps == [3.0]


@pytest.mark.anyio
async def test_http_retry_raises_last_network_error(monkeypatch):
    request = httpx.Request("GET", "https://example.test/data")
    failure = httpx.ConnectError("offline", request=request)
    client = _FakeClient([failure])
    monkeypatch.setattr(http_client, "get_http_client", lambda: client)
    monkeypatch.setattr(
        http_client,
        "get_settings",
        lambda: SimpleNamespace(external_retry_count=0),
    )
    with pytest.raises(httpx.ConnectError):
        await http_client.get_with_retries("https://example.test/data")


@pytest.mark.anyio
async def test_shared_http_client_closes(monkeypatch):
    client = _FakeClient([])
    monkeypatch.setattr(http_client, "_client", client)
    await http_client.close_http_client()
    assert client.is_closed is True
    assert http_client._client is None


class _JSONResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.anyio
async def test_geocoding_validates_and_caches_results(monkeypatch):
    calls = []

    async def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return _JSONResponse(
            200,
            [
                {"display_name": "Test Village, India", "lat": "18.5", "lon": "73.8"},
                {"display_name": "", "lat": "18.5", "lon": "73.8"},
                {"display_name": "Invalid", "lat": "not-a-number", "lon": "73.8"},
            ],
        )

    geocoding._cache.clear()
    monkeypatch.setattr(geocoding, "get_with_retries", fake_get)
    monkeypatch.setattr(
        geocoding,
        "settings",
        SimpleNamespace(
            geocoding_min_interval_seconds=1.0,
            geocoding_user_agent="test (+mailto:test@pond.local)",
            geocoding_url="https://example.test/search",
        ),
    )
    monkeypatch.setattr(geocoding, "_last_request_at", -100.0)
    results = await geocoding.search_village("  Test   Village ")
    assert results == [{"display_name": "Test Village, India", "lat": 18.5, "lng": 73.8}]
    assert await geocoding.search_village("Test Village") == results
    assert len(calls) == 1
    assert await geocoding.search_village("x") == []


@pytest.mark.anyio
async def test_geocoding_maps_provider_failure(monkeypatch):
    async def fake_get(*args, **kwargs):
        return _JSONResponse(429, [])

    geocoding._cache.clear()
    monkeypatch.setattr(geocoding, "get_with_retries", fake_get)
    monkeypatch.setattr(geocoding, "_last_request_at", -100.0)
    with pytest.raises(UpstreamDataError):
        await geocoding.search_village("uncached place")


def test_production_configuration_rejects_unsafe_placeholders(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.setenv("TRUSTED_HOSTS", "*")
    monkeypatch.setenv("GEOCODING_USER_AGENT", "app (+https://example.invalid/contact)")
    monkeypatch.setenv("HISTORY_ENABLED", "true")
    monkeypatch.delenv("HISTORY_API_KEY", raising=False)
    monkeypatch.setenv("APPROVED_RUNOFF_COEFFICIENT", "0.3")
    monkeypatch.delenv("APPROVED_RUNOFF_COEFFICIENT_SOURCE", raising=False)
    monkeypatch.setenv("IMAGERY_USE_AUTHORIZED", "false")
    errors = Settings().validation_errors()
    assert len(errors) >= 6
    assert any("HISTORY_API_KEY" in error for error in errors)
    assert any("imagery" in error.lower() for error in errors)
