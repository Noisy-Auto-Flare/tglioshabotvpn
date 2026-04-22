import httpx
import logging
import os
import asyncio
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class RemnaWaveService:
    def __init__(self):
        self.api_url = os.getenv("REMNAWAVE_API_URL", "").rstrip("/")
        self.api_key = os.getenv("REMNAWAVE_API_KEY")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, retries: int = 3) -> Optional[Dict[str, Any]]:
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.request(method, url, json=data, headers=self.headers)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"RemnaWave API error: {e.response.status_code} - {e.response.text}")
                if attempt == retries - 1:
                    return None
            except Exception as e:
                logger.error(f"RemnaWave request failed: {e}")
                if attempt == retries - 1:
                    return None
            await asyncio.sleep(2 ** attempt)
        return None

    async def create_vpn_user(self, telegram_id: int, expire_at: Optional[int] = None) -> Optional[Dict[str, Any]]:
        # This is a placeholder for actual RemnaWave API endpoint
        # You'll need to adapt it to the actual RemnaWave API documentation
        data = {
            "name": f"user_{telegram_id}",
            "expire_at": expire_at,
            "status": "active"
        }
        return await self._request("POST", "/users", data)

    async def disable_vpn_user(self, user_uuid: str) -> bool:
        response = await self._request("PATCH", f"/users/{user_uuid}", {"status": "disabled"})
        return response is not None

    async def delete_vpn_user(self, user_uuid: str) -> bool:
        response = await self._request("DELETE", f"/users/{user_uuid}")
        return response is not None

    async def get_vpn_config(self, user_uuid: str) -> Optional[str]:
        response = await self._request("GET", f"/users/{user_uuid}/config")
        if response and "config" in response:
            return response["config"]
        return None

vpn_service = RemnaWaveService()
