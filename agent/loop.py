from uuid import uuid4

from agent.llm import extract_group_spec
from agent.session import AgentSession, SessionState
from agent.store import get_session, save_session


def missing_information(session: AgentSession) -> list[str]:
    missing = []

    if session.spec.max_members is None:
        missing.append("number of members")

    if session.spec.contribution_lamports is None:
        missing.append("contribution per member in SOL")

    return missing


def format_lamports(lamports: int) -> str:
    sol = lamports / 1_000_000_000
    return f"{sol:g} SOL"


async def process_message(
    message: str,
    session_id: str | None = None,
) -> dict:
    # Find an existing conversation or create a new one.
    if session_id:
        session = get_session(session_id)

        if session is None:
            return {
                "error": "Session not found. Start a new conversation.",
            }
    else:
        session = AgentSession(session_id=str(uuid4()))

    # Handle explicit approval separately from ordinary extraction.
    normalized = message.strip().lower()

    # Approved configurations are locked.
    if session.state == SessionState.APPROVED:
        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "group_spec": session.spec.model_dump(),
            "reply": (
                "This configuration has already been approved "
                "and is now locked. Start a new session to create "
                "a different configuration."
            ),
            "can_deploy": False,
        }


    if session.state == SessionState.AWAITING_APPROVAL:
        if normalized in {"yes", "yes, approve", "approve", "i approve"}:
            session.state = SessionState.APPROVED
            session.explicit_approval = True
            save_session(session)

            return {
                "session_id": session.session_id,
                "state": session.state.value,
                "reply": (
                    "Configuration approved. "
                    "No blockchain transaction has been executed."
                ),
                "can_deploy": False,
            }

        if normalized in {"no", "no, cancel", "cancel", "reject"}:
            session.state = SessionState.DRAFTING
            session.explicit_approval = False
            save_session(session)

            return {
                "session_id": session.session_id,
                "state": session.state.value,
                "reply": "Approval declined. We can revise your configuration.",
                "can_deploy": False,
            }

    # Extract information from the latest message.
    session.spec = await extract_group_spec(message, session.spec)

    # Check which required details are still missing.
    missing = missing_information(session)

    if missing:
        session.state = SessionState.DRAFTING
        save_session(session)

        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "reply": f"I still need: {', '.join(missing)}.",
            "missing_information": missing,
            "can_deploy": False,
        }

    # All required details are available.
    session.state = SessionState.AWAITING_APPROVAL
    session.explicit_approval = False
    save_session(session)

    contribution = format_lamports(
        session.spec.contribution_lamports
    )

    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "group_spec": session.spec.model_dump(),
        "reply": (
            f"Your stokvel will have {session.spec.max_members} members, "
            f"each contributing {contribution}. "
            "Do you approve this configuration?"
        ),
        "can_deploy": False,
    }
