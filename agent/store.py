"""Session storage: in-memory cache, written through to Supabase when configured.

If Supabase is unset or unreachable the app keeps working from memory, so a
free project that has paused never takes the demo down.
"""
import logging

import httpx

from agent import config
from agent.session import AgentSession

logger = logging.getLogger(__name__)

SESSIONS: dict[str, AgentSession] = {}
TABLE = "sessions"


def _enabled() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_KEY)


def _headers(extra: dict | None = None) -> dict:
    return {
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
        "Content-Type": "application/json",
        **(extra or {}),
    }


def save_session(session: AgentSession) -> None:
    SESSIONS[session.session_id] = session
    if not _enabled():
        return
    try:
        r = httpx.post(
            f"{config.SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json={"session_id": session.session_id, "data": session.model_dump(mode="json")},
            timeout=5,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Supabase save failed, kept in memory: %s", type(exc).__name__)


def get_session(session_id: str) -> AgentSession | None:
    cached = SESSIONS.get(session_id)
    if cached is not None or not _enabled():
        return cached
    try:
        r = httpx.get(
            f"{config.SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={"session_id": f"eq.{session_id}", "select": "data"},
            timeout=5,
        )
        r.raise_for_status()
        rows = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Supabase load failed: %s", type(exc).__name__)
        return None
    if not rows:
        return None
    session = AgentSession.model_validate(rows[0]["data"])
    SESSIONS[session_id] = session
    return session
