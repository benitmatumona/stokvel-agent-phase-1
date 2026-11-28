import json
import subprocess

from agent import config
from agent.session import AgentSession, SessionState

# Test mode: tool calls are recorded instead of executed, so automated
# tests can never run a validator or touch a network.
RECORDED_CALLS: list[dict] = []


class GateError(Exception):
    pass


def deployment_allowed(
    explicit_approval: bool,
    tests_passed: bool,
) -> bool:
    """
    Deployment requires both explicit user approval
    and successful tests.
    """
    return explicit_approval and tests_passed


def run_attack_tests(session: AgentSession) -> dict:
    """Run the on-chain attack suite (anchor test) for an approved session."""
    if session.state != SessionState.APPROVED or not session.explicit_approval:
        raise GateError("Tests run only after explicit approval.")

    if config.TEST_MODE:
        RECORDED_CALLS.append({"tool": "run_attack_tests", "session": session.session_id})
        report = {"passed": True, "mode": "recorded", "output": ""}
    else:
        proc = subprocess.run(
            config.ANCHOR_TEST_COMMAND.split(),
            capture_output=True, text=True, timeout=900,
        )
        report = {
            "passed": proc.returncode == 0,
            "mode": "local-validator",
            "output": (proc.stdout + proc.stderr)[-4000:],
        }

    session.test_report = report
    session.tests_passed = report["passed"]
    return report


def deploy_group(session: AgentSession) -> dict:
    """Create the group on devnet. Refused in code unless the gate is open."""
    if not (session.can_deploy and deployment_allowed(
        session.explicit_approval, session.tests_passed
    )):
        raise GateError("Deployment requires approval and passing tests.")

    spec = session.spec
    call = {
        "tool": "deploy_group",
        "group_id": spec.group_id,
        "contribution_lamports": spec.contribution_lamports,
        "max_members": spec.max_members,
        "rules_hash": spec.rules_hash(),
        "cluster": "devnet",
    }

    if config.TEST_MODE:
        RECORDED_CALLS.append(call)
        result = {**call, "signature": "recorded", "mode": "recorded"}
    else:
        proc = subprocess.run(
            config.DEPLOY_COMMAND.split() + [
                spec.group_id,
                str(spec.contribution_lamports),
                str(spec.max_members),
                spec.rules_hash(),
            ],
            capture_output=True, text=True, timeout=180,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Deploy failed: {proc.stderr[-500:]}")
        result = {**call, **json.loads(proc.stdout.strip().splitlines()[-1]), "mode": "devnet"}

    session.deployment = result
    session.state = SessionState.DEPLOYED
    return result
