from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BASE_URL: str
    MODEL: str
    TEMPERATURE: float

    model_config = SettingsConfigDict(env_file='.env', env_config='utf-8')

app_settings = Settings()