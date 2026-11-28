from pathlib import Path

import io

import httpx
import segno
from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_MODEL,
    ELEVENLABS_URL,
    ELEVENLABS_VOICE_ID,
)
from agent.loop import process_message
from agent.store import get_session, save_session
from agent.tools import GateError, deploy_group, run_attack_tests


app = FastAPI(
    title="Stokvel Agent API",
    description="AI-powered assistant for creating stokvel groups.",
    version="0.3.0",
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Free ElevenLabs credits are limited (1 credit per character), so identical
# phrases are served from memory instead of being generated again.
TTS_CACHE: dict[str, bytes] = {}
TTS_CACHE_MAX = 64


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    state: str
    reply: str
    can_deploy: bool


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=300)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "stokvel-agent",
    }


@app.post("/chat")
async def chat(request: ChatRequest):
    result = await process_message(
        message=request.message,
        session_id=request.session_id,
    )

    if "error" in result:
        raise HTTPException(
            status_code=404,
            detail=result["error"],
        )

    return result


@app.get("/voice/config")
def voice_config():
    """Tells the web app whether server-side (ElevenLabs) speech is available."""
    return {"elevenlabs": bool(ELEVENLABS_API_KEY)}


@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    if not ELEVENLABS_API_KEY:
        raise HTTPException(status_code=503, detail="ElevenLabs is not configured.")

    cached = TTS_CACHE.get(request.text)
    if cached is not None:
        return Response(content=cached, media_type="audio/mpeg")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{ELEVENLABS_URL}/{ELEVENLABS_VOICE_ID}",
                headers={
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={"text": request.text, "model_id": ELEVENLABS_MODEL},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Text-to-speech failed.")

    if len(TTS_CACHE) >= TTS_CACHE_MAX:
        TTS_CACHE.pop(next(iter(TTS_CACHE)))
    TTS_CACHE[request.text] = response.content

    return Response(content=response.content, media_type="audio/mpeg")


def _session_or_404(session_id: str):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


@app.post("/sessions/{session_id}/test")
def run_tests(session_id: str):
    session = _session_or_404(session_id)
    try:
        report = run_attack_tests(session)
    except GateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    save_session(session)
    return {"session_id": session_id, "tests_passed": session.tests_passed, "report": report}


@app.post("/sessions/{session_id}/deploy")
def deploy(session_id: str):
    session = _session_or_404(session_id)
    try:
        result = deploy_group(session)
    except GateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    save_session(session)
    return {"session_id": session_id, "state": session.state.value, "deployment": result}


@app.get("/sessions/{session_id}/verify")
def verify(session_id: str):
    session = _session_or_404(session_id)
    return {
        "rules_hash": session.spec.rules_hash(),
        "deployed_hash": (session.deployment or {}).get("rules_hash"),
        "matches": bool(session.deployment)
        and session.deployment["rules_hash"] == session.spec.rules_hash(),
        "tests_passed": session.tests_passed,
    }


EXPLORER = "https://explorer.solana.com"


def _share_payload(session) -> dict:
    if session.deployment is None:
        raise HTTPException(status_code=409, detail="Group is not deployed yet.")
    d = session.deployment
    links = {}
    if d.get("mode") == "devnet":
        links = {
            "transaction": f"{EXPLORER}/tx/{d['signature']}?cluster=devnet",
            "group_account": f"{EXPLORER}/address/{d['group_pda']}?cluster=devnet",
            "rules_memo": f"{EXPLORER}/tx/{d['memo_signature']}?cluster=devnet",
        }
    return {
        "group_name": session.spec.group_name,
        "summary": session.spec.summary(),
        "rules_hash": session.spec.rules_hash(),
        "tests_passed": session.tests_passed,
        "test_report": session.test_report,
        "mode": d.get("mode"),
        "links": links,
    }


@app.get("/sessions/{session_id}/share")
def share(session_id: str):
    return _share_payload(_session_or_404(session_id))


@app.get("/sessions/{session_id}/qr.svg")
def qr(session_id: str, url: str):
    _share_payload(_session_or_404(session_id))
    if not url.startswith(("http://", "https://")) or len(url) > 500:
        raise HTTPException(status_code=422, detail="Invalid url.")
    buf = io.BytesIO()
    segno.make(url).save(buf, kind="svg", scale=6, border=2)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


# Mounted last so it never shadows the API routes above.
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
