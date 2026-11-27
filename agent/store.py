from agent.session import AgentSession

# Temporary in-memory storage.
# Sessions disappear when the API server restarts.
SESSIONS: dict[str, AgentSession] = {}


def save_session(session: AgentSession) -> None:
    SESSIONS[session.session_id] = session


def get_session(session_id: str) -> AgentSession | None:
    return SESSIONS.get(session_id)
