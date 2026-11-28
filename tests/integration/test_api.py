
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


def test_api_rejects_ambiguous_name_and_preserves_details(client):
    # Step 1: Start creating a stokvel without providing its name.
    first = client.post(
        "/chat",
        json={
            "message": "Create a stokvel with 10 members contributing 0.5 SOL"
        },
    )

    assert first.status_code == 200
    first_data = first.json()
    session_id = first_data["session_id"]

    assert first_data["state"] == "drafting"
    assert first_data["group_spec"]["group_name"] is None

    # Step 2: An ambiguous response must not become the group name.
    second = client.post(
        "/chat",
        json={
            "message": "hello",
            "session_id": session_id,
        },
    )

    assert second.status_code == 200
    second_data = second.json()

    assert second_data["session_id"] == session_id
    assert second_data["state"] == "drafting"
    assert second_data["group_spec"]["group_name"] is None
    assert second_data["group_spec"]["max_members"] == 10
    assert second_data["group_spec"]["contribution_lamports"] == 500_000_000
    assert "name" in second_data["reply"].lower()

    # Step 3: Provide a real name and complete the configuration.
    third = client.post(
        "/chat",
        json={
            "message": "Christmas Savings Club",
            "session_id": session_id,
        },
    )

    assert third.status_code == 200
    third_data = third.json()

    assert third_data["session_id"] == session_id
    assert third_data["state"] == "awaiting_approval"
    assert third_data["group_spec"]["group_name"] == "Christmas Savings Club"
    assert third_data["group_spec"]["max_members"] == 10
    assert third_data["group_spec"]["contribution_lamports"] == 500_000_000
    assert third_data["can_deploy"] is False


@pytest.mark.parametrize(
    "message, expected_error",
    [
        (
            "Create a stokvel with 25 members",
            "between 2 and 20",
        ),
        (
            "Create a stokvel with 10 members contributing 0 SOL",
            "greater than zero",
        ),
    ],
)
def test_invalid_configuration_does_not_crash_api(
    client,
    message,
    expected_error,
):
    response = client.post(
        "/chat",
        json={"message": message},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["state"] == "drafting"
    assert data["can_deploy"] is False
    assert expected_error in data["reply"]


@pytest.mark.parametrize(
    "invalid_update, expected_error",
    [
        (
            "Actually make it 25 members",
            "between 2 and 20",
        ),
        (
            "Change the contribution to 0 SOL",
            "greater than zero",
        ),
    ],
)
def test_invalid_update_preserves_existing_configuration(
    client,
    invalid_update,
    expected_error,
):
    initial_response = client.post(
        "/chat",
        json={
            "message": (
                "Create a stokvel called Christmas Savings Club "
                "with 10 members contributing 0.5 SOL"
            ),
        },
    )

    assert initial_response.status_code == 200

    initial_data = initial_response.json()
    assert initial_data["state"] == "awaiting_approval"

    session_id = initial_data["session_id"]

    response = client.post(
        "/chat",
        json={
            "message": invalid_update,
            "session_id": session_id,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["state"] == "drafting"
    assert data["can_deploy"] is False
    assert expected_error in data["reply"]

    # The original valid configuration must remain unchanged.
    assert data["group_spec"]["group_name"] == "Christmas Savings Club"
    assert data["group_spec"]["max_members"] == 10
    assert data["group_spec"]["contribution_lamports"] == 500_000_000


def test_negative_contribution_is_rejected_by_api(client):
    response = client.post(
        "/chat",
        json={
            "message": (
                "Create a stokvel with 10 members "
                "contributing -0.5 SOL"
            ),
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["state"] == "drafting"
    assert data["can_deploy"] is False
    assert "greater than zero" in data["reply"]
    assert data["group_spec"]["contribution_lamports"] is None
    assert data["group_spec"]["group_name"] is None
