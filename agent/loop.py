import re
from uuid import uuid4

from pydantic import ValidationError

from agent.llm import extract_group_spec
from agent.session import AgentSession, SessionState
from agent.store import get_session, save_session
from agent.summary_check import deterministic_check, llm_check


def missing_information(session: AgentSession) -> list[str]:
    missing = []

    if session.spec.group_name is None:
        missing.append("stokvel name")

    if session.spec.max_members is None:
        missing.append("number of members")

    if session.spec.contribution_lamports is None:
        missing.append("contribution per member in SOL")

    return missing


# Speech-to-text returns "Yes." or "Yes, go ahead." so replies are normalised
# before matching. Matching is still exact against a small set: "yes but make
# it 12 members" must NOT approve.
APPROVE_PHRASES = {
    "yes", "yes approve", "approve", "i approve", "approved", "yes i approve",
    "yes please", "yes go ahead", "go ahead", "yeah", "yep",
    "looks good", "yes looks good", "that looks good", "sounds good",
}
REJECT_PHRASES = {"no", "no cancel", "cancel", "reject", "nope", "no thanks"}


def normalize_reply(message: str) -> str:
    cleaned = re.sub(r"[^a-z0-9' ]+", " ", message.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


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
    normalized = normalize_reply(message)

    # Approved configurations are locked.
    if session.state in (SessionState.APPROVED, SessionState.DEPLOYED):
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
        if normalized in APPROVE_PHRASES:
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

        if normalized in REJECT_PHRASES:
            session.state = SessionState.DRAFTING
            session.explicit_approval = False
            save_session(session)

            return {
                "session_id": session.session_id,
                "state": session.state.value,
                "reply": "Approval declined. We can revise your configuration.",
                "can_deploy": False,
            }

    # Extract information without replacing valid details on failure.
    try:
        updated_spec = await extract_group_spec(message, session.spec)
    except ValidationError as exc:
        errors = exc.errors()
        error_message = (
            errors[0]["msg"] if errors else "Invalid configuration."
        )
        error_message = error_message.removeprefix("Value error, ")

        session.state = SessionState.DRAFTING
        save_session(session)

        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "group_spec": session.spec.model_dump(),
            "reply": (
                f"That detail is invalid: {error_message}. "
                "Please provide a valid value."
            ),
            "missing_information": missing_information(session),
            "can_deploy": False,
        }

    session.spec = updated_spec

    # Check which required details are still missing.
    missing = missing_information(session)

    if missing:
        session.state = SessionState.DRAFTING
        save_session(session)

        got = []
        if session.spec.group_name:
            got.append(f"the name {session.spec.group_name}")
        if session.spec.max_members:
            got.append(f"{session.spec.max_members} members")
        if session.spec.contribution_lamports:
            got.append(f"{format_lamports(session.spec.contribution_lamports)} each")
        prefix = f"Got it: {', '.join(got)}. " if got else ""

        if "stokvel name" in missing:
            reply = prefix + "What would you like to name your stokvel?"
        elif len(missing) == 2:
            reply = prefix + "How many members will there be, and how much will each member pay, in SOL?"
        elif "number of members" in missing:
            reply = prefix + "How many members will there be?"
        else:
            reply = prefix + "How much will each member pay, in SOL?"

        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "group_spec": session.spec.model_dump(),
            "reply": reply,
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

    group_name = session.spec.group_name or "your stokvel"

    summary = session.spec.summary()
    problems = deterministic_check(session.spec, summary)
    judged = await llm_check(session.spec, summary)
    if judged:
        problems += judged
    if problems:  # never ask the user to approve a summary that misdescribes the spec
        session.state = SessionState.DRAFTING
        save_session(session)
        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "group_spec": session.spec.model_dump(),
            "reply": "I could not produce a reliable summary of these rules, so I will not ask for approval. Please restate the details.",
            "can_deploy": False,
        }

    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "group_spec": session.spec.model_dump(),
        "summary": summary,
        "reply": (
            f"Let's review {group_name}. "
            f"It will have {session.spec.max_members} members, "
            f"each contributing {contribution}. "
            "Do you approve this configuration?"
        ),
        "can_deploy": False,
    }
