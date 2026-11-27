from agent.llm import fallback_extract
from agent.spec import GroupSpec


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
