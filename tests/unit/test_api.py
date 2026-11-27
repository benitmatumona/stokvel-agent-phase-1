import pytest
from fastapi.testclient import TestClient

from agent.llm import fallback_extract
from agent.main import app
from agent.store import SESSIONS


@pytest.fixture(autouse=True)
def clear_sessions():
    SESSIONS.clear()
    yield
    SESSIONS.clear()


@pytest.fixture
def client(monkeypatch):
    async def deterministic_extract(message, current):
        return fallback_extract(message, current)

    monkeypatch.setattr(
        "agent.loop.extract_group_spec",
        deterministic_extract,
    )

    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_chat_requests_missing_information(client):
    response = client.post(
        "/chat",
        json={"message": "Create a stokvel with 10 members"},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "drafting"
    assert "contribution per member in SOL" in (
        response.json()["missing_information"]
    )


def test_complete_conversation_and_approval(client):
    first = client.post(
        "/chat",
        json={
            "message": "Create a stokvel with 10 members"
        },
    )

    session_id = first.json()["session_id"]

    second = client.post(
        "/chat",
        json={
            "message": "Everyone contributes 0.5 SOL",
            "session_id": session_id,
        },
    )

    assert second.status_code == 200
    assert second.json()["state"] == "awaiting_approval"
    assert second.json()["group_spec"]["max_members"] == 10
    assert (
        second.json()["group_spec"]["contribution_lamports"]
        == 500_000_000
    )

    third = client.post(
        "/chat",
        json={
            "message": "approve",
            "session_id": session_id,
        },
    )

    assert third.status_code == 200
    assert third.json()["state"] == "approved"
    assert third.json()["can_deploy"] is False


def test_unknown_session_returns_404(client):
    response = client.post(
        "/chat",
        json={
            "message": "0.5 SOL",
            "session_id": "unknown-session",
        },
    )

    assert response.status_code == 404


def test_empty_message_is_rejected(client):
    response = client.post(
        "/chat",
        json={"message": ""},
    )

    assert response.status_code == 422
