from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./backend/opvs.db"
    workspace_path: str = "./workspace"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    anthropic_api_key: str = ""
    linear_api_key: str = ""
    ollama_host: str = "http://localhost:11434"


settings = Settings()
