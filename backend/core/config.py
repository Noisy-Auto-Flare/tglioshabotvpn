from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Bot Settings
    BOT_TOKEN: str
    ADMIN_IDS_RAW: str = Field(default="", validation_alias="ADMIN_IDS")

    @property
    def ADMIN_IDS(self) -> List[int]:
        if not self.ADMIN_IDS_RAW:
            return []
        try:
            return [int(x.strip()) for x in self.ADMIN_IDS_RAW.split(",") if x.strip()]
        except (ValueError, TypeError):
            return []

    # Database Settings
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/app.db"

    # VPN Settings (RemnaWave)
    REMNAWAVE_API_URL: str
    REMNAWAVE_API_KEY: str
    REMNAWAVE_COOKIE: str = ""
    SUB_DOMAIN: str = ""
    REMNAWAVE_DEFAULT_SQUAD_UUID: str = ""

    # Payment Settings (CryptoBot)
    CRYPTOBOT_TOKEN: str
    USE_WEBHOOK: bool = True
    WEBHOOK_URL: Optional[str] = None
    
    # App Settings
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

settings = Settings()
