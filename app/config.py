from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    oracle_user: str = "ADMIN"
    oracle_password: SecretStr = SecretStr("")
    oracle_dsn: str = "carrierdb_low"
    oracle_wallet_dir: Path = Path("/opt/oracle/wallet")
    oracle_wallet_password: SecretStr = SecretStr("")
    oracle_pool_max: int = Field(default=4, ge=1, le=16)
    robot_api_token: str = Field(default="dev-robot-token", min_length=8)
    admin_password_hash: SecretStr = SecretStr("")
    admin_session_secret: SecretStr = SecretStr("")
    admin_session_ttl_seconds: int = Field(default=1800, ge=300, le=86400)
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_configured(self) -> bool:
        return bool(
            self.oracle_user
            and self.oracle_password.get_secret_value()
            and self.oracle_dsn
            and self.oracle_wallet_password.get_secret_value()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
