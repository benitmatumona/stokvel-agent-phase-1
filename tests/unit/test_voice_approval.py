import pytest

from agent.loop import normalize_reply, process_message
from agent.store import get_session

CREATE = "Create a stokvel called Savings Club with 10 members contributing 0.5 SOL"


@pytest.mark.parametrize("raw,expected", [
    ("Yes.", "yes"),
    ("  Yes, go ahead!  ", "yes go ahead"),
    ("Looks   good...", "looks good"),
])
def test_normalize_reply(raw, expected):
    assert normalize_reply(raw) == expected


@pytest.mark.anyio
@pytest.mark.parametrize("spoken", ["Yes.", "Yes, go ahead.", "Looks good!", "Yeah", "I approve."])
async def test_spoken_approval_phrases_approve(spoken):
    first = await process_message(CREATE)
    result = await process_message(spoken, first["session_id"])
    assert result["state"] == "approved"
    assert result["can_deploy"] is False  # approval alone never deploys


@pytest.mark.anyio
@pytest.mark.parametrize("spoken", ["No.", "Cancel!", "Nope"])
async def test_spoken_rejection_phrases_reject(spoken):
    first = await process_message(CREATE)
    result = await process_message(spoken, first["session_id"])
    assert result["state"] == "drafting"


@pytest.mark.anyio
@pytest.mark.parametrize("spoken", ["hmm", "maybe later", "yes but make it 12 members"])
async def test_ambiguous_replies_do_not_approve(spoken):
    first = await process_message(CREATE)
    result = await process_message(spoken, first["session_id"])
    assert result["state"] != "approved"
    assert get_session(first["session_id"]).explicit_approval is False


@pytest.mark.anyio
async def test_conditional_yes_applies_edit_and_needs_fresh_approval():
    first = await process_message(CREATE)
    edited = await process_message("yes but make it 12 members", first["session_id"])
    assert edited["state"] == "awaiting_approval"
    assert edited["group_spec"]["max_members"] == 12
    assert get_session(first["session_id"]).explicit_approval is False
