
import pytest
from fastapi.testclient import TestClient

from agent.llm import fallback_extract
from agent.main import app
from agent.store import SESSIONS


@pytest.fixture
def client(monkeypatch):
    # Start every test with an empty session store.
    SESSIONS.clear()

    # Replace the real Groq call with predictable local extraction.
    async def fake_extract(message, current):
        return fallback_extract(message, current)

    monkeypatch.setattr(
        "agent.loop.extract_group_spec",
        fake_extract,
    )

    # Create a test HTTP client.
    with TestClient(app) as test_client:
        yield test_client

    # Clean up after the test.
    SESSIONS.clear()


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "stokvel-agent",
    }


def test_create_stokvel_through_api(client):
    response = client.post(
        "/chat",
        json={
            "message": "Create a group with 8 members"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["state"] == "drafting"
    assert data["session_id"]
    assert "contribution per member in SOL" in data["missing_information"]


def test_complete_stokvel_configuration(client):
    # First request: provide the member count.
    first_response = client.post(
        "/chat",
        json={
            "message": "Create a stokvel called Savings Club with 8 members"
        },
    )

    session_id = first_response.json()["session_id"]

    # Second request: provide the contribution.
    second_response = client.post(
        "/chat",
        json={
            "message": "Everyone contributes 0.25 SOL",
            "session_id": session_id,
        },
    )

    assert second_response.status_code == 200

    data = second_response.json()

    assert data["state"] == "awaiting_approval"
    assert data["group_spec"]["max_members"] == 8
    assert data["group_spec"]["contribution_lamports"] == 250_000_000
    assert data["can_deploy"] is False


def test_approve_configuration_without_deploying(client):
    # Create a complete configuration.
    response = client.post(
        "/chat",
        json={
            "message": "Create a stokvel called Savings Club with 8 members contributing 0.25 SOL"
        },
    )

    session_id = response.json()["session_id"]

    # Explicitly approve it.
    approval_response = client.post(
        "/chat",
        json={
            "message": "approve",
            "session_id": session_id,
        },
    )

    assert approval_response.status_code == 200

    data = approval_response.json()

    assert data["state"] == "approved"
    assert data["can_deploy"] is False


def test_unknown_session_returns_404(client):
    response = client.post(
        "/chat",
        json={
            "message": "Everyone contributes 0.5 SOL",
            "session_id": "unknown-session",
        },
    )

    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


def test_empty_message_returns_422(client):
    response = client.post(
        "/chat",
        json={
            "message": ""
        },
    )

    assert response.status_code == 422
