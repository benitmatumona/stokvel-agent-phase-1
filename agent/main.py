from pathlib import Path

import httpx
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


# Mounted last so it never shadows the API routes above.
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
