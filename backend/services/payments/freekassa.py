import hashlib
import logging
import urllib.parse
from typing import Optional, Dict, Any
from backend.core.config import settings

logger = logging.getLogger(__name__)

class FreeKassaService:
    def __init__(self, merchant_id: str, secret_1: str, secret_2: str):
        self.merchant_id = merchant_id
        self.secret_1 = secret_1
        self.secret_2 = secret_2
        self.api_url = "https://pay.freekassa.ru/"

    def generate_payment_url(self, amount: float, order_id: str, currency: str = "RUB") -> str:
        # Signature: merchant_id:amount:secret_word:currency:order_id
        # FreeKassa requires amount to be formatted as string
        amount_str = str(amount)
        sign_str = f"{self.merchant_id}:{amount_str}:{self.secret_1}:{currency}:{order_id}"
        signature = hashlib.md5(sign_str.encode()).hexdigest()
        
        params = {
            "m": self.merchant_id,
            "oa": amount_str,
            "o": order_id,
            "s": signature,
            "currency": currency,
            "lang": "ru"
        }
        
        query_string = urllib.parse.urlencode(params)
        return f"{self.api_url}?{query_string}"

    def verify_webhook(self, data: Dict[str, Any]) -> bool:
        # Signature for webhook: merchant_id:amount:secret_word_2:order_id
        merchant_id = data.get("MERCHANT_ID")
        amount = data.get("AMOUNT")
        order_id = data.get("MERCHANT_ORDER_ID")
        signature = data.get("SIGN")
        
        if not all([merchant_id, amount, order_id, signature]):
            return False
            
        sign_str = f"{merchant_id}:{amount}:{self.secret_2}:{order_id}"
        expected_signature = hashlib.md5(sign_str.encode()).hexdigest()
        
        return str(signature).lower() == expected_signature.lower()

freekassa_service = FreeKassaService(
    settings.FREEKASSA_MERCHANT_ID or "",
    settings.FREEKASSA_SECRET_1 or "",
    settings.FREEKASSA_SECRET_2 or ""
)
