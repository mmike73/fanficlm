from fastapi import APIRouter, HTTPException, Request

from app.schemas.theme import ThemeRequest, ThemeResponse

router = APIRouter()


@router.post("/theme", response_model=ThemeResponse)
async def detect_theme(body: ThemeRequest, request: Request) -> ThemeResponse:
    """Classify a fanfic prompt into one of the supported themes."""
    detector = request.app.state.theme_detector
    try:
        result = await detector.detect(body.prompt)
        return ThemeResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")