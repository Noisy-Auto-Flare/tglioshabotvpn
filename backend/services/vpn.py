import httpx
import logging
import asyncio
import json
from typing import Optional, Dict, Any, Union, List
from backend.core.config import settings

logger = logging.getLogger(__name__)

class RemnaWaveService:
    def __init__(self):
        self.api_url = settings.REMNAWAVE_API_URL.rstrip("/")
        self.api_key = settings.REMNAWAVE_API_KEY
        self.base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self._working_auth_method = None

    def _get_auth_headers(self, method: str) -> Dict[str, str]:
        """Returns headers for a specific auth method."""
        headers = self.base_headers.copy()
        if method == "Bearer":
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif method == "Token":
            headers["Authorization"] = f"{self.api_key}"
        elif method == "X-API-Key":
            headers["X-API-Key"] = self.api_key
        return headers

    async def _try_request(self, client: httpx.AsyncClient, method: str, url: str, auth_method: str, data: Optional[Dict[str, Any]] = None) -> Union[Dict[str, Any], None]:
        """Attempts a single request with a specific auth method."""
        headers = self._get_auth_headers(auth_method)
        try:
            logger.info(f"Trying auth method {auth_method}: {method} {url}")
            response = await client.request(method, url, json=data, headers=headers, follow_redirects=True)
            
            # Log full response details for debugging
            logger.info(f"Response Status: {response.status_code}")
            logger.info(f"Response Headers: {dict(response.headers)}")
            logger.info(f"Response Body: {response.text[:500]}") # Log first 500 chars

            if response.is_success:
                self._working_auth_method = auth_method
                try:
                    return {"success": True, "data": response.json(), "status_code": response.status_code}
                except json.JSONDecodeError:
                    return {"success": True, "data": response.text, "status_code": response.status_code}
            
            return {"success": False, "status_code": response.status_code, "error": response.text}
        except Exception as e:
            logger.error(f"Request failed with {auth_method}: {str(e)}")
            return None

    async def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, retries: int = 3) -> Dict[str, Any]:
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        last_error = "Unknown error"
        
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for attempt in range(1, retries + 1):
                # 1. Use working method if known
                auth_methods = [self._working_auth_method] if self._working_auth_method else ["Bearer", "Token", "X-API-Key"]
                
                for auth_method in auth_methods:
                    result = await self._try_request(client, method, url, auth_method, data)
                    if result and result["success"]:
                        return result
                    if result:
                        last_error = f"Auth {auth_method} failed: {result.get('status_code')} - {result.get('error')}"
                
                if attempt < retries:
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
            
        return {"success": False, "error": last_error}

    async def debug_remnawave(self) -> Dict[str, Any]:
        """Debug method to test different endpoints and connectivity."""
        results = {}
        endpoints = ["/", "/api", "/api/health", "/api/clients", "/api/client/add", "/panel/api/inbounds/addClient"]
        
        for ep in endpoints:
            logger.info(f"--- DEBUGGING ENDPOINT: {ep} ---")
            results[ep] = await self._request("GET" if "add" not in ep else "POST", ep)
            
        return results

    async def create_vpn_user(self, telegram_id: int, expire_at: Optional[int] = None) -> Dict[str, Any]:
        # Try different possible user creation endpoints
        endpoints = ["/users", "/api/users", "/api/clients", "/api/client/add"]
        data = {
            "name": f"user_{telegram_id}",
            "expire_at": expire_at,
            "status": "active"
        }
        
        for endpoint in endpoints:
            logger.info(f"Trying user creation at {endpoint}")
            result = await self._request("POST", endpoint, data)
            if result.get("success"):
                logger.info(f"Successfully created user at {endpoint}")
                return result
                
        return {"success": False, "error": "All creation endpoints failed"}

    async def disable_vpn_user(self, user_uuid: str) -> bool:
        result = await self._request("PATCH", f"/users/{user_uuid}", {"status": "disabled"})
        return result.get("success", False)

    async def delete_vpn_user(self, user_uuid: str) -> bool:
        result = await self._request("DELETE", f"/users/{user_uuid}")
        return result.get("success", False)

    async def get_vpn_config(self, user_uuid: str) -> Optional[str]:
        result = await self._request("GET", f"/users/{user_uuid}/config")
        if result.get("success") and isinstance(result["data"], dict) and "config" in result["data"]:
            return result["data"]["config"]
        return None

vpn_service = RemnaWaveService()
