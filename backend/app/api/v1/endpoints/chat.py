from fastapi import APIRouter, HTTPException, Request, logger
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import rag_service
import logging
import traceback

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    lm_client = request.app.state.lm_client
    try:
        messages = [m.model_dump() for m in body.messages]

        last_user_msg = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            ""
        )

        rag_context = ""
        if last_user_msg:
            try:
                results = rag_service.retrieve(last_user_msg, n_results=3)
                logger.info(f"RAG retrieved {len(results)} results:")
                for r in results:
                    logger.info(f"  → {r['character_name']} ({r['media_source']}) [{r['source']}] score={r['score']}")
                rag_context = rag_service.build_context_block(results)
            except Exception as rag_error:
                traceback.print_exc()
                logger.warning(f"RAG failed: {rag_error}")
                rag_context = ""

        reply = await lm_client.chat_completion(messages, rag_context=rag_context)
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")