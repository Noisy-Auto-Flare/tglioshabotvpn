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
    
    # Telegram Stars
    STARS_CONVERSION_RATE: int = 50 # 1 USD = 50 Stars (approximately)

    # TonConnect
    TON_WALLET_ADDRESS: Optional[str] = None
    TONCONNECT_MANIFEST_URL: str = "https://raw.githubusercontent.com/ton-connect/demo-dapp/main/public/tonconnect-manifest.json"

    # App Settings
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # VPN Plans
    PLANS: dict = {
        "30": {"price": 5, "gb": 90, "label": "30 дней - 5$"},
        "90": {"price": 12, "gb": 90, "label": "90 дней - 12$"},
        "180": {"price": 20, "gb": 180, "label": "180 дней - 20$"},
        "360": {"price": 35, "gb": 360, "label": "360 дней - 35$"},
    }

settings = Settings()
