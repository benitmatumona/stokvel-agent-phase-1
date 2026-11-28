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

@pytest.mark.anyio
async def test_approved_configuration_cannot_be_modified():
    first = await process_message(
        "Create a group with 10 members contributing 0.5 SOL"
    )

    session_id = first["session_id"]

    approved = await process_message(
        "approve",
        session_id,
    )

    assert approved["state"] == "approved"

    follow_up = await process_message(
        "Actually make it 12 members",
        session_id,
    )

    assert follow_up["state"] == "approved"
    assert follow_up["group_spec"]["max_members"] == 10
    assert follow_up["group_spec"]["contribution_lamports"] == 500_000_000


@pytest.mark.anyio
async def test_agent_can_edit_configuration_before_approval():
    first = await process_message(
        "Create a group with 10 members contributing 0.5 SOL"
    )

    session_id = first["session_id"]

    updated = await process_message(
        "Actually make it 12 members",
        session_id,
    )

    assert updated["state"] == "awaiting_approval"
    assert updated["group_spec"]["max_members"] == 12
    assert updated["group_spec"]["contribution_lamports"] == 500_000_000
    assert updated["can_deploy"] is False
    assert "approve" in updated["reply"].lower()


@pytest.mark.anyio
async def test_configuration_edit_requires_fresh_approval():
    first = await process_message(
        "Create a group with 10 members contributing 0.5 SOL"
    )

    session_id = first["session_id"]

    updated = await process_message(
        "Actually make it 12 members",
        session_id,
    )

    session = SESSIONS[session_id]

    assert updated["state"] == "awaiting_approval"
    assert session.explicit_approval is False
    assert updated["can_deploy"] is False


@pytest.mark.anyio
async def test_rejected_configuration_can_be_revised_and_approved():
    first = await process_message(
        "Create a group with 10 members contributing 0.5 SOL"
    )

    session_id = first["session_id"]

    rejected = await process_message("no", session_id)

    assert rejected["state"] == "drafting"

    revised = await process_message(
        "Actually make it 12 members",
        session_id,
    )

    assert revised["state"] == "awaiting_approval"
    assert revised["group_spec"]["max_members"] == 12
    assert revised["group_spec"]["contribution_lamports"] == 500_000_000

    approved = await process_message("approve", session_id)

    assert approved["state"] == "approved"
    assert approved["can_deploy"] is False
    assert SESSIONS[session_id].explicit_approval is True
