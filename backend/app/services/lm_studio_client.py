import httpx
from core.config import app_settings

class LMClient:
    def __init___(self):
        self.base_url = app_settings.BASE_URL
        self.model = app_settings.MODEL
        self.temperature = app_settings.TEMPERATURE

    async def chat_completion(self, messages: list[dict]):
        payload = {
            "model":self.model,
            "messages":messages,
            "temperature":self.temperature
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload, timeout=app_settings.TIMEOUT)
            response.raise_for_status()

            data = response.json()
            return data["choices"][0]["message"]["content"]