from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://tasks:tasks@postgres:5432/tasks"
    adaptive_url: str = "http://adaptive-service:8002"
    openai_api_key: str
    openai_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"
    aiassist_url: str = "http://ai-assistant:8003"

    class Config:
        extra = "ignore"
        env_file = ".env"


settings = Settings()
