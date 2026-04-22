import os
from typing import List, Optional, Any, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Bot Settings
    BOT_TOKEN: str
    ADMIN_IDS: List[int] = []

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> List[int]:
        if isinstance(v, str):
            if not v.strip():
                return []
            try:
                return [int(x.strip()) for x in v.split(",") if x.strip()]
            except ValueError:
                return []
        return v

    # Database Settings
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"

    # VPN Settings (RemnaWave)
    REMNAWAVE_API_URL: str
    REMNAWAVE_API_KEY: str

    # Payment Settings (CryptoBot)
    CRYPTOBOT_TOKEN: str
    USE_WEBHOOK: bool = True
    WEBHOOK_URL: Optional[str] = None
    
    # App Settings
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

settings = Settings()
