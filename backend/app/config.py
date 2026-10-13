"""RTD.MUAR — configuration. All values overridable via env / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), env_prefix="", extra="ignore")

    app_name: str = "RTD.MUAR"
    secret_key: str = "change-me-in-production"
    database_url: str = "sqlite+aiosqlite:///./rtd.db"   # prod: postgresql+asyncpg://...
    redis_url: str = "redis://localhost:6379/0"

    # Auth / magic link
    base_url: str = "http://localhost:5173"              # frontend origin (links point here)
    magic_link_ttl_hours: int = 48
    session_ttl_days: int = 30

    # SMTP (optional). If not configured, magic links are printed to server log
    # and returned in the API response for local development.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "RTD.MUAR <no-reply@rtd.heartwins.ru>"
    smtp_use_tls: bool = True

    # Game rules
    max_replica_len: int = 280
    replicas_per_takt: int = 3
    takt_minutes: int = 30
    scene_weight_threshold: float = 0.6

    # AI
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    embedding_dim: int = 256          # hash-embedding fallback dim; sentence-transformers uses 768

    # Stage mode gate
    maturity_min_for_stage: float = 75.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
