from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Northwind Expense AI"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # Anthropic
    # Optional so the app boots without a key; services that need it raise a
    # clear error at call time (mirrors the OpenAI handling in retrieval.py).
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_MAX_TOKENS: int = 1500

    # OpenAI (policy embeddings)
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # CORS
    # Sensible defaults cover local dev and the current Render frontend, so the
    # app works out of the box. To point at a different deployed frontend, set
    # FRONTEND_ORIGIN (a single URL) — it is merged into the allowed origins
    # without having to override the whole list.
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",  # local development
        "https://northwind-expense-ai-1.onrender.com",  # deployed frontend (Render)
    ]
    FRONTEND_ORIGIN: str = ""  # optional extra origin from the environment

    @property
    def cors_origins(self) -> list[str]:
        """Allowed origins with the optional FRONTEND_ORIGIN merged in (de-duped)."""
        origins = list(self.ALLOWED_ORIGINS)
        extra = self.FRONTEND_ORIGIN.strip().rstrip("/")
        if extra and extra not in origins:
            origins.append(extra)
        return origins

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()
