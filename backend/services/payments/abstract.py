import logging
from typing import Optional, Dict, Any
import httpx
from backend.core.config import settings

logger = logging.getLogger(__name__)

class SBPService:
    # Now handled by Platega
    pass

class TONService:
    def __init__(self, wallet_address: str, api_key: Optional[str] = None):
        self.wallet_address = wallet_address
        self.api_key = api_key
        self.api_url = "https://toncenter.com/api/v2"

    async def create_invoice(self, amount_rub: float, order_id: str) -> Dict[str, str]:
        # Convert RUB to TON using TON price in USD and USD/RUB rate
        # 1 TON = TON_PRICE_USD (e.g. 6$)
        # 1 $ = USD_RUB_RATE (e.g. 100р)
        # 1 TON = TON_PRICE_USD * USD_RUB_RATE (e.g. 600р)
        ton_price_rub = settings.TON_PRICE_USD * settings.USD_RUB_RATE
        ton_amount = amount_rub / ton_price_rub
        nanotons = int(ton_amount * 10**9)
        
        # TON Deep Link (ton://transfer/<address>?amount=<nanotons>&text=<comment>)
        pay_url = f"ton://transfer/{self.wallet_address}?amount={nanotons}&text={order_id}"
        
        return {
            "pay_url": pay_url,
            "external_id": order_id,
            "ton_amount": f"{ton_amount:.4f}"
        }

    async def check_transaction(self, order_id: str) -> bool:
        """
        Check if there's an incoming transaction with the given order_id as a comment.
        """
        if not self.wallet_address:
            return False

        logger.info(f"Checking TON transactions for wallet {self.wallet_address}, order {order_id}")
        
        params = {
            "address": self.wallet_address,
            "limit": 20,
        }
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.api_url}/getTransactions", params=params)
                if response.status_code != 200:
                    logger.error(f"TonCenter API error: {response.status_code} {response.text}")
                    return False
                
                data = response.json()
                if not data.get("ok"):
                    logger.error(f"TonCenter API returned not ok: {data}")
                    return False

                transactions = data.get("result", [])
                for tx in transactions:
                    # Look for incoming transactions
                    in_msg = tx.get("in_msg", {})
                    if not in_msg:
                        continue
                    
                    # Check comment
                    msg_text = in_msg.get("message", "")
                    if msg_text == str(order_id):
                        # Transaction found!
                        logger.info(f"TON transaction found for order {order_id}!")
                        return True
                        
                return False
        except Exception as e:
            logger.error(f"Failed to check TON transactions: {e}")
            return False

sbp_service = SBPService()
ton_service = TONService(
    settings.TON_WALLET_ADDRESS or "",
    settings.TONCENTER_API_KEY
)
