from fastapi import APIRouter, HTTPException, Request
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    lm_client = request.app.state.lm_client
    try:
        messages = [m.model_dump() for m in body.messages]
        reply = await lm_client.chat_completion(messages)
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")