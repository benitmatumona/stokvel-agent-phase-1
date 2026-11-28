import httpx
import pytest

from agent import config, store
from agent.session import AgentSession, SessionState


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    store.SESSIONS.clear()
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_KEY", "k")


class FakeDB:
    """Minimal PostgREST stand-in."""
    def __init__(self): self.rows = {}; self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("POST", url, headers))
        self.rows[json["session_id"]] = json["data"]
        return httpx.Response(201, request=httpx.Request("POST", url))

    def get(self, url, headers=None, params=None, timeout=None):
        sid = params["session_id"].removeprefix("eq.")
        data = [{"data": self.rows[sid]}] if sid in self.rows else []
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))


def test_round_trip_survives_restart(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(store.httpx, "post", db.post)
    monkeypatch.setattr(store.httpx, "get", db.get)
    s = AgentSession(session_id="a1", state=SessionState.APPROVED, explicit_approval=True)
    store.save_session(s)
    assert db.calls[0][2]["Prefer"].startswith("resolution=merge-duplicates")
    store.SESSIONS.clear()  # simulate server restart
    loaded = store.get_session("a1")
    assert loaded.state == SessionState.APPROVED and loaded.explicit_approval
    assert store.get_session("missing") is None


def test_supabase_down_falls_back_to_memory(monkeypatch):
    def boom(*a, **k): raise httpx.ConnectError("down")
    monkeypatch.setattr(store.httpx, "post", boom)
    monkeypatch.setattr(store.httpx, "get", boom)
    store.save_session(AgentSession(session_id="b1"))
    assert store.get_session("b1") is not None      # from memory
    store.SESSIONS.clear()
    assert store.get_session("b1") is None          # no crash


def test_disabled_without_config(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    def fail(*a, **k): raise AssertionError("network used")
    monkeypatch.setattr(store.httpx, "post", fail)
    monkeypatch.setattr(store.httpx, "get", fail)
    store.save_session(AgentSession(session_id="c1"))
    assert store.get_session("c1") is not None
