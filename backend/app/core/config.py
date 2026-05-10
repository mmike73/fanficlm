from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    LM_STUDIO_BASE_URL: str
    LM_STUDIO_MODEL: str
    TEMPERATURE: float = 0.7
    TIMEOUT: int = 120

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / '.env',
        env_file_encoding='utf-8'
    )

app_settings = Settings()