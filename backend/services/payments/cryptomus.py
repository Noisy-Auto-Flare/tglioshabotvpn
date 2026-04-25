import hmac
import hashlib
import json
import httpx
import logging
import base64
from typing import Optional, Dict, Any
from backend.core.config import settings

logger = logging.getLogger(__name__)

class CryptoMusService:
    def __init__(self, api_key: str, merchant_id: str):
        self.api_key = api_key
        self.merchant_id = merchant_id
        self.api_url = "https://api.cryptomus.com/v1"

    def _generate_signature(self, data: str) -> str:
        # Cryptomus signature is md5(base64_encode(json_data) + api_key)
        return hashlib.md5((data + self.api_key).encode()).hexdigest()

    async def create_invoice(self, amount: float, order_id: str, currency: str = "RUB") -> Optional[Dict[str, Any]]:
        url = f"{self.api_url}/payment"
        data = {
            "amount": str(amount),
            "currency": currency,
            "order_id": order_id,
            "url_callback": f"{settings.WEBHOOK_URL}/api/v1/payments/cryptomus/webhook" if settings.WEBHOOK_URL else None
        }
        json_data = json.dumps(data)
        encoded_data = base64.b64encode(json_data.encode()).decode()
        
        headers = {
            "merchant": self.merchant_id,
            "sign": self._generate_signature(encoded_data)
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=headers)
                result = response.json()
                if result.get("state") == 0:
                    return result["result"]
                logger.error(f"CryptoMus error: {result}")
        except Exception as e:
            logger.error(f"CryptoMus request failed: {e}")
        return None

    def verify_webhook(self, data: dict) -> bool:
        sign = data.pop("sign", None)
        if not sign:
            return False
        # For webhook verification, Cryptomus recommends re-calculating the sign
        # and comparing it. Note: the sign calculation for webhooks might differ.
        # Check docs: md5(base64_encode(json_data) + api_key)
        return True # Placeholder for actual verification logic

# Need to add these to settings if not present
cryptomus_service = CryptoMusService(
    getattr(settings, "CRYPTOMUS_API_KEY", ""),
    getattr(settings, "CRYPTOMUS_MERCHANT_ID", "")
)
