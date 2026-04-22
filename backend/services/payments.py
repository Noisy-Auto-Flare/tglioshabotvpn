import httpx
import logging
import hashlib
import hmac
from typing import Optional, Dict, Any, List
from backend.core.config import settings

logger = logging.getLogger(__name__)

class CryptoBotService:
    def __init__(self):
        self.api_token = settings.CRYPTOBOT_TOKEN
        # CryptoBot API URL depends on the token (mainnet vs testnet)
        # Using mainnet by default. Testnet is https://testnet-pay.crypt.bot/api
        self.api_url = "https://pay.crypt.bot/api"
        self.headers = {"Crypto-Pay-API-Token": self.api_token}

    async def create_invoice(self, amount: float, asset: str = "USDT", payload: str = "") -> Optional[Dict[str, Any]]:
        url = f"{self.api_url}/createInvoice"
        data = {
            "asset": asset,
            "amount": str(amount),
            "payload": payload,
            "allow_comments": False,
            "allow_anonymous": False
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=data, headers=self.headers)
                response.raise_for_status()
                res_data = response.json()
                if res_data.get("ok"):
                    return res_data["result"]
                logger.error(f"CryptoBot createInvoice failed: {res_data.get('error')}")
                return None
        except Exception as e:
            logger.error(f"CryptoBot request failed: {e}")
            return None

    async def get_invoices(self, invoice_ids: List[str]) -> List[Dict[str, Any]]:
        """Get status of specific invoices via API polling."""
        if not invoice_ids:
            return []
            
        url = f"{self.api_url}/getInvoices"
        params = {"invoice_ids": ",".join(invoice_ids)}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params, headers=self.headers)
                response.raise_for_status()
                res_data = response.json()
                if res_data.get("ok"):
                    return res_data["result"]["items"]
                logger.error(f"CryptoBot getInvoices failed: {res_data.get('error')}")
                return []
        except Exception as e:
            logger.error(f"CryptoBot getInvoices request failed: {e}")
            return []

    def verify_webhook(self, body: str, signature: str) -> bool:
        """Verify webhook signature from CryptoBot."""
        if not signature:
            return False
        token_hash = hashlib.sha256(self.api_token.encode()).digest()
        expected_sig = hmac.new(token_hash, body.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature)

cryptobot_service = CryptoBotService()
