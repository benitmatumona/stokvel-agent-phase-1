import pytest

from agent.llm import extract_group_spec, fallback_extract
from agent.spec import GroupSpec


from agent.llm import fallback_extract
from agent.spec import GroupSpec

from pydantic import ValidationError

def test_extract_member_count():
    spec = fallback_extract(
        "Create a group with 10 members",
        GroupSpec(),
    )
    assert spec.max_members == 10


def test_extract_sol_contribution():
    spec = fallback_extract(
        "Everyone contributes 0.5 SOL",
        GroupSpec(),
    )
    assert spec.contribution_lamports == 500_000_000


def test_extract_half_sol():
    spec = fallback_extract(
        "Everyone contributes half a SOL",
        GroupSpec(),
    )
    assert spec.contribution_lamports == 500_000_000


def test_preserve_existing_values():
    current = GroupSpec(max_members=10)
    spec = fallback_extract(
        "Everyone contributes 1 SOL",
        current,
    )
    assert spec.max_members == 10
    assert spec.contribution_lamports == 1_000_000_000


def test_missing_information_is_not_invented():
    spec = fallback_extract(
        "I want to create a stokvel",
        GroupSpec(),
    )
    assert spec.max_members is None
    assert spec.contribution_lamports is None

@pytest.mark.anyio
async def test_missing_api_key_uses_fallback(monkeypatch):
    monkeypatch.setattr("agent.llm.GROQ_API_KEY", None)

    spec = await extract_group_spec(
        "Create a group with 8 members contributing 0.25 SOL",
        GroupSpec(),
    )

    assert spec.max_members == 8
    assert spec.contribution_lamports == 250_000_000


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, *args, **kwargs):
        import httpx
        raise httpx.TimeoutException("Simulated timeout")


@pytest.mark.anyio
async def test_groq_timeout_uses_fallback(monkeypatch):
    monkeypatch.setattr("agent.llm.GROQ_API_KEY", "fake-test-key")
    monkeypatch.setattr("agent.llm.httpx.AsyncClient", FakeAsyncClient)

    spec = await extract_group_spec(
        "Create a group with 8 members contributing 0.25 SOL",
        GroupSpec(),
    )

    assert spec.max_members == 8
    assert spec.contribution_lamports == 250_000_000

def test_fallback_rejects_invalid_group_size():
    with pytest.raises(ValidationError):
        fallback_extract(
            "Create a group with 100 members",
            GroupSpec(),
        )

class FakeInvalidResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"group_name": "Ubuntu Savings", '
                            '"max_members": 100}'
                        )
                    }
                }
            ]
        }


class FakeInvalidResponseClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, *args, **kwargs):
        return FakeInvalidResponse()

@pytest.mark.anyio
async def test_invalid_groq_data_uses_fallback(monkeypatch):
    monkeypatch.setattr("agent.llm.GROQ_API_KEY", "fake-test-key")
    monkeypatch.setattr(
        "agent.llm.httpx.AsyncClient",
        FakeInvalidResponseClient,
    )

    spec = await extract_group_spec(
        "Create a group with 8 members contributing 0.25 SOL",
        GroupSpec(),
    )

    assert spec.max_members == 8
    assert spec.contribution_lamports == 250_000_000


def test_extract_group_name_with_called():
    spec = fallback_extract(
        "Create a stokvel called Christmas Savings Club",
        GroupSpec(),
    )

    assert spec.group_name == "Christmas Savings Club"


def test_extract_group_name_with_group_name_is():
    spec = fallback_extract(
        "Our group name is Ubuntu Savings",
        GroupSpec(),
    )

    assert spec.group_name == "Ubuntu Savings"


def test_preserve_existing_group_name():
    current = GroupSpec(group_name="December Contributors")

    spec = fallback_extract(
        "Everyone contributes 0.5 SOL",
        current,
    )

    assert spec.group_name == "December Contributors"


def test_extract_group_name_with_called():
    spec = fallback_extract(
        "Create a stokvel called Christmas Savings Club",
        GroupSpec(),
    )

    assert spec.group_name == "Christmas Savings Club"


def test_extract_group_name_with_group_name_is():
    spec = fallback_extract(
        "Our group name is Ubuntu Savings",
        GroupSpec(),
    )

    assert spec.group_name == "Ubuntu Savings"


def test_preserve_existing_group_name():
    current = GroupSpec(group_name="December Contributors")

    spec = fallback_extract(
        "Everyone contributes 0.5 SOL",
        current,
    )

    assert spec.group_name == "December Contributors"


def test_extract_complete_stokvel_details():
    spec = fallback_extract(
        "Create a stokvel called Christmas Savings Club "
        "with 10 members contributing 0.5 SOL each",
        GroupSpec(),
    )

    assert spec.group_name == "Christmas Savings Club"
    assert spec.max_members == 10
    assert spec.contribution_lamports == 500_000_000
    assert spec.is_complete is True


def test_fallback_extracts_standalone_name_when_name_is_missing():
    current = GroupSpec(
        max_members=10,
        contribution_lamports=500_000_000,
    )

    spec = fallback_extract(
        "Christmas Savings Club",
        current,
    )

    assert spec.group_name == "Christmas Savings Club"
    assert spec.max_members == 10
    assert spec.contribution_lamports == 500_000_000

@pytest.mark.parametrize(
    "message",
    [
        "hello",
        "I don't know",
        "maybe",
        "not sure",
        "okay",
    ],
)
def test_fallback_does_not_accept_ambiguous_message_as_name(message):
    current = GroupSpec(
        max_members=10,
        contribution_lamports=500_000_000,
    )

    spec = fallback_extract(message, current)

    assert spec.group_name is None
    assert spec.max_members == 10
    assert spec.contribution_lamports == 500_000_000
