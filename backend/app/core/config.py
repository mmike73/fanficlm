from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / 'prompts'

class Settings(BaseSettings):
    LM_STUDIO_BASE_URL: str
    LM_STUDIO_MODEL: str
    LM_STUDIO_EMBEDDING_MODEL: str = "text-embedding-nomic-embed-text-v1.5"
    EMBEDDING_MODEL: str
    VECTOR_STORE_PATH: str = str(Path(__file__).resolve().parent.parent.parent.parent / "vector_store")
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2048
    TIMEOUT: int = 120

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / '.env',
        env_file_encoding='utf-8'
    )

app_settings = Settings()