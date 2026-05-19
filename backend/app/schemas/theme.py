from pydantic import BaseModel


class ThemeRequest(BaseModel):
    prompt: str


class ThemeResponse(BaseModel):
    theme: str
    confidence: float
    scores: dict[str, float]