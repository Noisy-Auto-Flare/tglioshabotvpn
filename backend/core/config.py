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
    
    # FreeKassa (SBP)
    FREEKASSA_MERCHANT_ID: Optional[str] = None
    FREEKASSA_SECRET_1: Optional[str] = None
    FREEKASSA_SECRET_2: Optional[str] = None

    # CryptoMus
    CRYPTOMUS_API_KEY: Optional[str] = None
    CRYPTOMUS_MERCHANT_ID: Optional[str] = None
    
    # Telegram Stars
    STARS_CONVERSION_RATE: int = 50 # 1 USD = 50 Stars (approximately)

    # TonConnect
    TON_WALLET_ADDRESS: Optional[str] = None
    TONCONNECT_MANIFEST_URL: str = "https://raw.githubusercontent.com/ton-connect/demo-dapp/main/public/tonconnect-manifest.json"
    TON_PRICE_USD: float = 6.0
    TONCENTER_API_KEY: Optional[str] = None

    # App Settings
    USD_RUB_RATE: float = 90.0 # 1 USD = 90 RUB
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Mandatory Subscription
    REQUIRED_CHANNEL: str = "@StingerVPN"

    # VPN Plans
    PLANS: dict = {
        "30": {"price": 190, "gb": 300, "label": "30 дней - 190р"},
        "90": {"price": 540, "gb": 900, "label": "90 дней - 540р"},
        "180": {"price": 990, "gb": 1800, "label": "180 дней - 990р"},
        "360": {"price": 1290, "gb": 3600, "label": "360 дней - 1290р"},
    }

settings = Settings()
