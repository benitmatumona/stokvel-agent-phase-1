import pytest

from agent.loop import process_message
from agent.session import SessionState
from agent.store import SESSIONS


@pytest.fixture(autouse=True)
def clear_sessions():
    SESSIONS.clear()
    yield
    SESSIONS.clear()


@pytest.mark.anyio
async def test_agent_asks_for_missing_contribution():
    result = await process_message(
        "Create a group with 10 members"
    )

    assert result["state"] == "drafting"
    assert "contribution per member in SOL" in result["missing_information"]


@pytest.mark.anyio
async def test_agent_preserves_information_between_messages():
    first = await process_message(
        "Create a group with 10 members"
    )

    second = await process_message(
        "Everyone contributes 0.5 SOL",
        first["session_id"],
    )

    assert second["state"] == "awaiting_approval"
    assert second["group_spec"]["max_members"] == 10
    assert second["group_spec"]["contribution_lamports"] == 500_000_000


@pytest.mark.anyio
async def test_agent_requires_explicit_approval():
    first = await process_message(
        "Create a group with 10 members contributing 0.5 SOL"
    )

    assert first["state"] == "awaiting_approval"
    assert first["can_deploy"] is False

    approved = await process_message(
        "approve",
        first["session_id"],
    )

    assert approved["state"] == "approved"
    assert approved["can_deploy"] is False


@pytest.mark.anyio
async def test_agent_can_reject_configuration():
    first = await process_message(
        "Create a group with 10 members contributing 0.5 SOL"
    )

    rejected = await process_message(
        "no",
        first["session_id"],
    )

    assert rejected["state"] == "drafting"


@pytest.mark.anyio
async def test_unknown_session_is_rejected():
    result = await process_message(
        "0.5 SOL",
        "unknown-session",
    )

    assert "error" in result
