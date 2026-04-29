import logging
import httpx
from typing import Optional, Dict, Any
from backend.core.config import settings

logger = logging.getLogger(__name__)

class PlategaService:
    def __init__(self, merchant_id: Optional[str], secret: Optional[str]):
        self.merchant_id = merchant_id
        self.secret = secret
        self.base_url = "https://app.platega.io"

    async def create_payment(self, amount: float, order_id: str) -> Optional[str]:
        """
        Создает транзакцию и возвращает ссылку на оплату.
        """
        if not self.merchant_id or not self.secret:
            logger.error("Platega credentials not configured")
            return None

        # Trying /transaction as /transaction/process returns 400 "process is not valid id"
        url = f"{self.base_url}/transaction"
        headers = {
            "X-MerchantId": self.merchant_id,
            "X-Secret": self.secret,
            "Content-Type": "application/json"
        }
        
        # Official docs say paymentDetails object is required
        payload = {
            "paymentMethod": 2,
            "paymentDetails": {
                "amount": float(amount),
                "currency": "RUB"
            },
            "description": f"Оплата подписки (Заказ {order_id})",
            "payload": order_id
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload, timeout=10.0)
                if response.status_code != 200:
                    logger.error(f"Platega API error {response.status_code}: {response.text}")
                    return None
                
                data = response.json()
                
                # Based on typical Platega response
                if data.get("status") == "error":
                    logger.error(f"Platega error: {data.get('message')}")
                    return None
                
                return data.get("paymentUrl") or data.get("url")
        except Exception as e:
            logger.error(f"Failed to create Platega payment: {e}")
            return None

    def verify_webhook(self, data: Dict[str, Any], headers: Dict[str, Any]) -> bool:
        """
        Проверяет подлинность вебхука по заголовкам.
        """
        # Try different cases for headers
        merchant_id = headers.get("X-MerchantId") or headers.get("x-merchantid")
        secret = headers.get("X-Secret") or headers.get("x-secret")
        
        if not merchant_id or not secret:
            return False
            
        return str(merchant_id) == str(self.merchant_id) and str(secret) == str(self.secret)

platega_service = PlategaService(
    settings.PLATEGA_MERCHANT_ID,
    settings.PLATEGA_SECRET
)
