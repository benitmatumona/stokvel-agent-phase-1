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

    assert second["state"] == "drafting"
    assert "stokvel name" in second["missing_information"]

    third = await process_message(
        "Christmas Savings Club",
        first["session_id"],
    )

    assert third["state"] == "awaiting_approval"
    assert third["group_spec"]["group_name"] == "Christmas Savings Club"
    assert third["group_spec"]["max_members"] == 10
    assert third["group_spec"]["contribution_lamports"] == 500_000_000


@pytest.mark.anyio
async def test_agent_requires_explicit_approval():
    first = await process_message(
        "Create a stokvel called Savings Club with 10 members contributing 0.5 SOL"
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
        "Create a stokvel called Savings Club with 10 members contributing 0.5 SOL"
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
        "Create a stokvel called Savings Club with 10 members contributing 0.5 SOL"
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
        "Create a stokvel called Savings Club with 10 members contributing 0.5 SOL"
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
        "Create a stokvel called Savings Club with 10 members contributing 0.5 SOL"
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
        "Create a stokvel called Savings Club with 10 members contributing 0.5 SOL"
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


@pytest.mark.anyio
async def test_approval_summary_includes_group_name():
    result = await process_message(
        "Create a stokvel called Christmas Savings Club "
        "with 10 members contributing 0.5 SOL"
    )

    assert result["state"] == "awaiting_approval"
    assert result["group_spec"]["group_name"] == "Christmas Savings Club"
    assert "Christmas Savings Club" in result["reply"]


@pytest.mark.anyio
async def test_agent_asks_for_missing_group_name():
    result = await process_message(
        "Create a stokvel with 10 members contributing 0.5 SOL"
    )

    assert result["state"] == "drafting"
    assert "stokvel name" in result["missing_information"]
    assert "name" in result["reply"].lower()
    assert result["group_spec"]["max_members"] == 10
    assert result["group_spec"]["contribution_lamports"] == 500_000_000


@pytest.mark.anyio
async def test_agent_asks_naturally_for_missing_group_name():
    result = await process_message(
        "Create a stokvel with 10 members contributing 0.5 SOL"
    )

    assert result["state"] == "drafting"
    assert "what would you like to name" in result["reply"].lower()


@pytest.mark.anyio
async def test_agent_remembers_details_when_user_provides_group_name():
    first = await process_message(
        "Create a stokvel with 10 members contributing 0.5 SOL"
    )

    session_id = first["session_id"]

    assert first["state"] == "drafting"
    assert "stokvel name" in first["missing_information"]

    second = await process_message(
        "Christmas Savings Club",
        session_id,
    )

    assert second["state"] == "awaiting_approval"
    assert second["group_spec"]["group_name"] == "Christmas Savings Club"
    assert second["group_spec"]["max_members"] == 10
    assert second["group_spec"]["contribution_lamports"] == 500_000_000
    assert "Christmas Savings Club" in second["reply"]
    assert second["can_deploy"] is False


@pytest.mark.anyio
async def test_agent_rejects_ambiguous_name_and_preserves_details():
    first = await process_message(
        "Create a stokvel with 10 members contributing 0.5 SOL"
    )

    session_id = first["session_id"]

    assert first["state"] == "drafting"

    second = await process_message(
        "hello",
        session_id,
    )

    assert second["state"] == "drafting"
    assert second["group_spec"]["group_name"] is None
    assert second["group_spec"]["max_members"] == 10
    assert second["group_spec"]["contribution_lamports"] == 500_000_000
    assert "name" in second["reply"].lower()

    third = await process_message(
        "Christmas Savings Club",
        session_id,
    )

    assert third["state"] == "awaiting_approval"
    assert third["group_spec"]["group_name"] == "Christmas Savings Club"
    assert third["group_spec"]["max_members"] == 10
    assert third["group_spec"]["contribution_lamports"] == 500_000_000
