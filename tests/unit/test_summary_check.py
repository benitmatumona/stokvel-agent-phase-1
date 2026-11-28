import asyncio

from agent import summary_check as sc
from agent.loop import process_message
from agent.spec import GroupSpec

SPEC = GroupSpec(group_name="G", contribution_lamports=200_000_000, max_members=5)


def test_generated_summary_passes():
    assert sc.deterministic_check(SPEC, SPEC.summary()) == []


def test_wrong_numbers_and_promises_are_caught():
    bad = "G has 6 members. Each pays 0.2 SOL. You will earn interest."
    problems = sc.deterministic_check(SPEC, bad)
    assert any("members" in p for p in problems)
    assert any("returns" in p for p in problems)
    assert any("withdraw" in p for p in problems)


def test_conditions_come_from_spec():
    joined = " ".join(sc.conditions_from_spec(SPEC))
    assert "5 members" in joined and "0.2 SOL" in joined


def test_llm_judge_skipped_without_key():
    assert asyncio.run(sc.llm_check(SPEC, SPEC.summary())) is None


def test_approval_blocked_if_summary_is_wrong(monkeypatch):
    monkeypatch.setattr(GroupSpec, "summary", lambda self: "Totally different rules.")
    out = asyncio.run(process_message("A stokvel called Gogo with 5 members, each paying 0.2 SOL"))
    assert out["state"] == "drafting" and "approval" in out["reply"]
