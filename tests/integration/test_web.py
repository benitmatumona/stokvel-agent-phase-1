import httpx
import pytest
from fastapi.testclient import TestClient

import agent.main as main
from agent.main import app


@pytest.fixture
def client():
    main.TTS_CACHE.clear()
    with TestClient(app) as c:
        yield c
    main.TTS_CACHE.clear()


def test_home_page_is_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Stokvel by Voice" in res.text


def test_static_assets_are_served(client):
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200


def test_api_routes_are_not_shadowed_by_static_files(client):
    assert client.get("/health").json()["status"] == "healthy"


def test_voice_config_reports_missing_key(client, monkeypatch):
    monkeypatch.setattr(main, "ELEVENLABS_API_KEY", None)
    assert client.get("/voice/config").json() == {"elevenlabs": False}


def test_tts_without_key_returns_503(client, monkeypatch):
    monkeypatch.setattr(main, "ELEVENLABS_API_KEY", None)
    assert client.post("/tts", json={"text": "hello"}).status_code == 503


def test_tts_rejects_long_text_to_protect_free_credits(client, monkeypatch):
    monkeypatch.setattr(main, "ELEVENLABS_API_KEY", "test-key")
    assert client.post("/tts", json={"text": "x" * 301}).status_code == 422


def _fake_client(calls, fail=False):
    class FakeResponse:
        content = b"ID3-fake-audio"

        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            calls.append((url, headers, json))
            if fail:
                raise httpx.ConnectError("boom")
            return FakeResponse()

    return FakeClient


def test_tts_returns_audio_and_caches_repeated_phrases(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(main.httpx, "AsyncClient", _fake_client(calls))

    first = client.post("/tts", json={"text": "Do you approve?"})
    second = client.post("/tts", json={"text": "Do you approve?"})

    assert first.status_code == 200 and first.headers["content-type"] == "audio/mpeg"
    assert second.content == first.content
    assert len(calls) == 1  # second request came from the cache, no credits spent
    assert calls[0][1]["xi-api-key"] == "test-key"


def test_tts_provider_failure_returns_502(client, monkeypatch):
    monkeypatch.setattr(main, "ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(main.httpx, "AsyncClient", _fake_client([], fail=True))
    assert client.post("/tts", json={"text": "hello"}).status_code == 502
