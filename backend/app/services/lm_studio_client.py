import httpx
from app.core.config import app_settings, PROMPTS_DIR

def _load_system_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    return path.read_text(encoding='utf-8').strip()

class LMClient:
    def __init__(self):
        self.base_url = app_settings.LM_STUDIO_BASE_URL
        self.model = app_settings.LM_STUDIO_MODEL
        self.temperature = app_settings.TEMPERATURE
        self.timeout = app_settings.TIMEOUT
        self.system_prompt = _load_system_prompt('system_default.txt')

    async def chat_completion(
        self,
        messages: list[dict],
        rag_context: str = "",
    ) -> str:
        system = self.system_prompt
        if rag_context:
            system = f"{system}\n\n{rag_context}"

        payload = {
            "model":       self.model,
            "messages":    [{"role": "system", "content": system}, *messages],
            "temperature": self.temperature,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]