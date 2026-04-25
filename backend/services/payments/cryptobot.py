import hmac
import hashlib
import json
import httpx
import logging
from typing import Optional, Dict, Any
from backend.core.config import settings

logger = logging.getLogger(__name__)

class CryptoBotService:
    def __init__(self, token: str):
        self.token = token
        self.api_url = "https://pay.crypt.bot/api"
        self.headers = {"Crypto-Pay-API-Token": token}

    async def create_invoice(self, amount: float, payload: str, currency: str = "USD") -> Optional[Dict[str, Any]]:
        url = f"{self.api_url}/createInvoice"
        data = {
            "amount": amount,
            "asset": "USDT", # Or other supported assets
            "payload": payload,
            "allow_anonymous": False,
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=self.headers)
                result = response.json()
                if result.get("ok"):
                    return result["result"]
                logger.error(f"CryptoBot error: {result}")
        except Exception as e:
            logger.error(f"CryptoBot request failed: {e}")
        return None

    def verify_webhook(self, body: str, signature: str) -> bool:
        token_hash = hashlib.sha256(self.token.encode()).digest()
        expected_signature = hmac.new(token_hash, body.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_signature, signature)

    async def get_invoices(self, invoice_ids: str) -> Optional[list]:
        url = f"{self.api_url}/getInvoices"
        params = {"invoice_ids": invoice_ids}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=self.headers)
                result = response.json()
                if result.get("ok"):
                    return result["result"]["items"]
        except Exception as e:
            logger.error(f"CryptoBot polling failed: {e}")
        return None

cryptobot_service = CryptoBotService(settings.CRYPTOBOT_TOKEN)
