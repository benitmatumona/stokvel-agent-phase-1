from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.loop import process_message


app = FastAPI(
    title="Stokvel Agent API",
    description="AI-powered assistant for creating stokvel groups.",
    version="0.1.0",
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    state: str
    reply: str
    can_deploy: bool


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
