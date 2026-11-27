from agent.session import AgentSession, SessionState
from agent.spec import GroupSpec
from agent.tools import deployment_allowed


def test_approval_without_tests_is_denied():
    assert deployment_allowed(True, False) is False


def test_tests_without_approval_are_denied():
    assert deployment_allowed(False, True) is False


def test_no_approval_and_no_tests_are_denied():
    assert deployment_allowed(False, False) is False


def test_approval_and_tests_are_required():
    assert deployment_allowed(True, True) is True


def test_session_cannot_deploy_without_complete_spec():
    session = AgentSession(
        session_id="test-1",
        state=SessionState.APPROVED,
        explicit_approval=True,
        tests_passed=True,
    )
    assert session.can_deploy is False


def test_complete_approved_session_can_pass_gate():
    session = AgentSession(
        session_id="test-2",
        state=SessionState.APPROVED,
        spec=GroupSpec(
            contribution_lamports=500_000_000,
            max_members=10,
        ),
        explicit_approval=True,
        tests_passed=True,
    )
    assert session.can_deploy is True
