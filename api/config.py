from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    ollama_url: str = "http://ollama:11434"
    llm_model: str = "qwen2.5:7b"
    embed_model: str = "nomic-embed-text"

    # Vector store
    qdrant_url: str = "http://qdrant:6333"
    collection_name: str = "contratos"

    # Seguridad
    secret_key: str = "BfzlrnuOb+IesDnSQ4jHggpefwlQz4SFGTBc9s7RD88="
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # Alertas
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    slack_webhook: str = ""
    alert_email: str = ""

    # Paths
    data_dir: str = "/app/data"
    prompts_dir: str = "/app/prompts"

    class Config:
        env_file = ".env"


settings = Settings()
