import pytest
from fastapi.testclient import TestClient

from agent import config, tools
from agent.main import app
from agent.session import AgentSession, SessionState
from agent.spec import GroupSpec
from agent.store import save_session


@pytest.fixture(autouse=True)
def test_mode(monkeypatch):
    monkeypatch.setattr(config, "TEST_MODE", True)
    tools.RECORDED_CALLS.clear()


def make(approved=True):
    s = AgentSession(
        session_id="s1",
        state=SessionState.APPROVED if approved else SessionState.AWAITING_APPROVAL,
        explicit_approval=approved,
        spec=GroupSpec(group_name="G", contribution_lamports=10, max_members=3),
    )
    save_session(s)
    return s


def test_rules_hash_is_stable_and_changes_with_rules():
    a = GroupSpec(group_id="x", contribution_lamports=1, max_members=2)
    b = GroupSpec(group_id="x", contribution_lamports=1, max_members=2)
    c = GroupSpec(group_id="x", contribution_lamports=2, max_members=2)
    assert a.rules_hash() == b.rules_hash() != c.rules_hash()


def test_deploy_refused_before_tests():
    with pytest.raises(tools.GateError):
        tools.deploy_group(make())
    assert tools.RECORDED_CALLS == []


def test_tests_refused_before_approval():
    with pytest.raises(tools.GateError):
        tools.run_attack_tests(make(approved=False))


def test_full_flow_records_instead_of_deploying():
    s = make()
    assert tools.run_attack_tests(s)["passed"]
    result = tools.deploy_group(s)
    assert result["rules_hash"] == s.spec.rules_hash()
    assert s.state == SessionState.DEPLOYED
    assert [c["tool"] for c in tools.RECORDED_CALLS] == ["run_attack_tests", "deploy_group"]
    with pytest.raises(tools.GateError):  # no double deploy
        tools.deploy_group(s)


def test_endpoints_gate_and_verify():
    make()
    c = TestClient(app)
    assert c.post("/sessions/s1/deploy").status_code == 409
    assert c.post("/sessions/s1/test").json()["tests_passed"] is True
    assert c.post("/sessions/s1/deploy").status_code == 200
    assert c.get("/sessions/s1/verify").json()["matches"] is True
    assert c.post("/sessions/nope/deploy").status_code == 404


def test_summary_matches_spec():
    spec = GroupSpec(group_name="Gogo", contribution_lamports=500_000_000, max_members=4)
    text = spec.summary()
    assert "4 members" in text and "0.5 SOL" in text and "2 SOL" in text
    assert "cannot withdraw" in text


def test_share_requires_deployment_and_serves_qr():
    s = make()
    c = TestClient(app)
    assert c.get("/sessions/s1/share").status_code == 409
    c.post("/sessions/s1/test"); c.post("/sessions/s1/deploy")
    body = c.get("/sessions/s1/share").json()
    assert body["rules_hash"] == s.spec.rules_hash() and body["tests_passed"]
    r = c.get("/sessions/s1/qr.svg", params={"url": "https://example.com/x"})
    assert r.status_code == 200 and b"<svg" in r.content
    assert c.get("/sessions/s1/qr.svg", params={"url": "javascript:1"}).status_code == 422


def test_deployed_session_is_locked_in_chat():
    import asyncio
    from agent.loop import process_message
    s = make(); tools.run_attack_tests(s); tools.deploy_group(s)
    out = asyncio.run(process_message("make it 9 members", s.session_id))
    assert "locked" in out["reply"] and s.spec.max_members == 3
