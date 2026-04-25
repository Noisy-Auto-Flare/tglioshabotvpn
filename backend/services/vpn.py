import httpx
import logging
import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union, List
from curl_cffi import requests as curl_requests, CurlHttpVersion
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

    def _build_panel_headers(self, panel_base: str) -> Dict[str, str]:
        headers = {
            "accept": "application/json",
            "accept-language": "ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7",
            "authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
            "origin": panel_base,
            "priority": "u=1, i",
            "sec-ch-ua": '"Microsoft Edge";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0",
            "x-remnawave-client-type": "browser"
        }
        if settings.REMNAWAVE_COOKIE:
            headers["Cookie"] = settings.REMNAWAVE_COOKIE
        return headers

    def _deep_find_first(self, obj: Any, keys: List[str]) -> Optional[Any]:
        """Recursively finds first non-empty value by key name in nested dict/list."""
        if isinstance(obj, dict):
            for k in keys:
                val = obj.get(k)
                if val:
                    return val
            for v in obj.values():
                found = self._deep_find_first(v, keys)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = self._deep_find_first(item, keys)
                if found:
                    return found
        return None

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
            logger.info(f"Request: {method} {url} with {auth_method}")
            # Use a slightly longer timeout for the first connection
            response = await client.request(method, url, json=data, headers=headers, follow_redirects=True)
            
            logger.info(f"Response from {url}: {response.status_code}")
            
            if response.is_success:
                self._working_auth_method = auth_method
                try:
                    return {"success": True, "data": response.json(), "status_code": response.status_code}
                except json.JSONDecodeError:
                    return {"success": True, "data": response.text, "status_code": response.status_code}
            
            # If 404, maybe the endpoint is wrong
            if response.status_code == 404:
                logger.warning(f"Endpoint not found: {url}")
            
            return {"success": False, "status_code": response.status_code, "error": response.text}
        except httpx.ConnectError as e:
            logger.error(f"Connection error to {url}: {str(e)}")
            return {"success": False, "error": f"Connection error: {str(e)}", "type": "connection_error"}
        except httpx.RemoteProtocolError as e:
            logger.error(f"Protocol error (server disconnected) from {url}: {str(e)}")
            return {"success": False, "error": "Server disconnected", "type": "protocol_error"}
        except Exception as e:
            logger.error(f"Request failed to {url} with {auth_method}: {str(e)}")
            return None

    async def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, retries: int = 3) -> Dict[str, Any]:
        # Clean up base URL
        base_url = self.api_url.rstrip("/")
        
        # Clean up endpoint
        clean_endpoint = endpoint.lstrip("/")
        
        # Avoid double /api/ in the URL
        if base_url.endswith("/api"):
            if clean_endpoint.startswith("api/"):
                clean_endpoint = clean_endpoint[4:]
        elif "/api/" not in base_url and not base_url.endswith("/api"):
            # If base_url doesn't have /api at all, and endpoint doesn't start with it, 
            # maybe we should add it? But let's trust the provided endpoints for now.
            pass
            
        url = f"{base_url}/{clean_endpoint}"
        last_error = "Unknown error"
        
        # Use a single client for all retries to benefit from connection pooling
        async with httpx.AsyncClient(
            timeout=15.0, 
            follow_redirects=True, 
            verify=False,
            # Explicitly use HTTP/1.1 to avoid some protocol errors with certain panels
            http2=False 
        ) as client:
            for attempt in range(1, retries + 1):
                # 1. Use working method if known
                auth_methods = [self._working_auth_method] if self._working_auth_method else ["Bearer", "Token", "X-API-Key"]
                
                for auth_method in auth_methods:
                    result = await self._try_request(client, method, url, auth_method, data)
                    
                    if result and result.get("success"):
                        return result
                    
                    if result:
                        # If we got a connection error or protocol error, maybe try switching http/https?
                        if result.get("type") in ["connection_error", "protocol_error"] and url.startswith("https://"):
                            alt_url = url.replace("https://", "http://")
                            logger.info(f"Retrying with HTTP: {alt_url}")
                            alt_result = await self._try_request(client, method, alt_url, auth_method, data)
                            if alt_result and alt_result.get("success"):
                                return alt_result
                        
                        last_error = f"Auth {auth_method} failed: {result.get('status_code', 'ERR')} - {result.get('error')}"
                
                if attempt < retries:
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying request to {url} in {wait_time}s (attempt {attempt}/{retries})...")
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

    def create_user_and_get_link(self, telegram_id: int, data_limit_gb: int = 30, days: int = 30) -> Optional[str]:
        """Creates a RemnaWave user via curl_cffi and returns subscription URL."""
        panel_base = self.api_url
        if panel_base.endswith("/api"):
            panel_base = panel_base[:-4]

        unique_username = f"user_{telegram_id}_{int(time.time())}"
        expire_at = (datetime.now() + timedelta(days=days)).isoformat() + "Z"
        payload = {
            "username": unique_username,
            "status": "ACTIVE",
            "trafficLimitBytes": data_limit_gb * 1024**3,
            "trafficLimitStrategy": "NO_RESET",
            "expireAt": expire_at,
            "description": f"Created by bot for {telegram_id}",
            "activeInternalSquads": [settings.REMNAWAVE_DEFAULT_SQUAD_UUID] if settings.REMNAWAVE_DEFAULT_SQUAD_UUID else []
        }
        headers = self._build_panel_headers(panel_base)

        try:
            # NOTE: verify=False is kept for compatibility with current panel config.
            # For production, use a valid certificate and set verify=True.
            response = curl_requests.post(
                f"{panel_base}/api/users",
                headers=headers,
                json=payload,
                impersonate="chrome120",
                http_version=CurlHttpVersion.V1_1,
                timeout=30,
                verify=False
            )
            if response.status_code not in (200, 201):
                logger.error("RemnaWave create user failed: status=%s body=%s", response.status_code, response.text)
                return None

            data = response.json()
            inner = data.get("response", data) if isinstance(data, dict) else {}
            user_uuid = self._deep_find_first(inner, ["uuid"])
            short_uuid = self._deep_find_first(inner, ["shortUuid"])
            if not short_uuid:
                logger.error("RemnaWave create user response missing shortUuid: %s", data)
                return None

            if not settings.REMNAWAVE_DEFAULT_SQUAD_UUID:
                logger.warning("REMNAWAVE_DEFAULT_SQUAD_UUID is empty; user is created without squad assignment")

            # Diagnostic verification: read created user and log current squads.
            # This helps verify that activeInternalSquads from POST was applied.
            if user_uuid:
                assigned_squads = self.get_user_active_squads(user_uuid)
                if assigned_squads is None:
                    logger.warning("Could not verify squads for user_uuid=%s after create", user_uuid)
                else:
                    logger.info("Created user_uuid=%s activeInternalSquads=%s", user_uuid, assigned_squads)
            else:
                logger.warning("Could not verify squads: uuid missing in create response: %s", data)

            if inner.get("subscriptionUrl"):
                return inner["subscriptionUrl"]
            if settings.SUB_DOMAIN:
                return f"{settings.SUB_DOMAIN.rstrip('/')}/{short_uuid}"
            return None
        except Exception as e:
            logger.exception("create_user_and_get_link failed for telegram_id=%s: %s", telegram_id, e)
            return None

    def delete_user(self, identifier: str) -> bool:
        """
        Deletes user from RemnaWave.
        Tries deleting by UUID directly, and if fails, tries to resolve shortUuid to UUID first.
        """
        if not identifier:
            logger.error("delete_user called with empty identifier")
            return False

        panel_base = self.api_url
        if panel_base.endswith("/api"):
            panel_base = panel_base[:-4]

        headers = self._build_panel_headers(panel_base)
        
        # 1. Try resolving long UUID if it's a short one
        user_uuid = identifier
        if len(identifier) < 32: # Short UUIDs are usually shorter
            resolved_uuid = self.get_uuid_by_short_uuid(identifier)
            if resolved_uuid:
                user_uuid = resolved_uuid
                logger.info("Resolved shortUuid %s to UUID %s", identifier, user_uuid)

        # 2. Delete using long UUID
        try:
            response = curl_requests.delete(
                f"{panel_base}/api/users/{user_uuid}",
                headers=headers,
                impersonate="chrome120",
                http_version=CurlHttpVersion.V1_1,
                timeout=30,
                verify=False
            )
            if response.status_code in (200, 204):
                logger.info("Successfully deleted user_uuid=%s from RemnaWave", user_uuid)
                return True
            
            # If failed and we didn't try resolving yet, try resolving now
            if user_uuid == identifier:
                resolved_uuid = self.get_uuid_by_short_uuid(identifier)
                if resolved_uuid and resolved_uuid != identifier:
                    logger.info("Retrying deletion with resolved UUID %s", resolved_uuid)
                    response = curl_requests.delete(
                        f"{panel_base}/api/users/{resolved_uuid}",
                        headers=headers,
                        impersonate="chrome120",
                        http_version=CurlHttpVersion.V1_1,
                        timeout=30,
                        verify=False
                    )
                    if response.status_code in (200, 204):
                        logger.info("Successfully deleted user_uuid=%s from RemnaWave after resolution", resolved_uuid)
                        return True

            logger.error("RemnaWave delete user failed: status=%s body=%s", response.status_code, response.text)
            return False
        except Exception as e:
            logger.exception("Failed to delete user %s from RemnaWave: %s", identifier, e)
            return False

    def get_uuid_by_short_uuid(self, short_uuid: str) -> Optional[str]:
        """Resolves shortUuid to long UUID via GET /api/users/by-short-uuid/{shortUuid}."""
        panel_base = self.api_url
        if panel_base.endswith("/api"):
            panel_base = panel_base[:-4]

        headers = self._build_panel_headers(panel_base)
        try:
            response = curl_requests.get(
                f"{panel_base}/api/users/by-short-uuid/{short_uuid}",
                headers=headers,
                impersonate="chrome120",
                http_version=CurlHttpVersion.V1_1,
                timeout=30,
                verify=False
            )
            if response.status_code == 200:
                data = response.json()
                inner = data.get("response", data) if isinstance(data, dict) else {}
                return inner.get("uuid")
            logger.warning("Failed to resolve shortUuid %s: status=%s", short_uuid, response.status_code)
            return None
        except Exception as e:
            logger.exception("Error resolving shortUuid %s: %s", short_uuid, e)
            return None

    def add_user_to_squad(self, user_uuid: str, squad_uuid: str) -> bool:
        """Adds user to Internal Squad via PATCH /api/users."""
        panel_base = self.api_url
        if panel_base.endswith("/api"):
            panel_base = panel_base[:-4]

        headers = self._build_panel_headers(panel_base)
        payload = {
            "uuid": user_uuid,
            "activeInternalSquads": [squad_uuid]
        }
        try:
            for attempt in range(1, 3):
                response = curl_requests.patch(
                    f"{panel_base}/api/users",
                    headers=headers,
                    json=payload,
                    impersonate="chrome120",
                    http_version=CurlHttpVersion.V1_1,
                    timeout=30,
                    verify=False
                )
                if response.status_code in (200, 201):
                    return True
                logger.warning(
                    "Squad PATCH attempt %s failed: status=%s body=%s",
                    attempt,
                    response.status_code,
                    response.text
                )
                time.sleep(1)
            return False
        except Exception as e:
            logger.exception("Failed to add user %s to squad %s: %s", user_uuid, squad_uuid, e)
            return False

    def get_user_active_squads(self, user_uuid: str) -> Optional[List[Any]]:
        """Fetches user and returns activeInternalSquads for diagnostics."""
        panel_base = self.api_url
        if panel_base.endswith("/api"):
            panel_base = panel_base[:-4]

        headers = self._build_panel_headers(panel_base)
        try:
            response = curl_requests.get(
                f"{panel_base}/api/users/{user_uuid}",
                headers=headers,
                impersonate="chrome120",
                http_version=CurlHttpVersion.V1_1,
                timeout=30,
                verify=False
            )
            if response.status_code not in (200, 201):
                logger.warning("GET user for squad verification failed: status=%s body=%s", response.status_code, response.text)
                return None

            data = response.json()
            inner = data.get("response", data) if isinstance(data, dict) else {}
            squads = self._deep_find_first(inner, ["activeInternalSquads"])
            return squads if isinstance(squads, list) else []
        except Exception as e:
            logger.exception("Failed to verify squads for user_uuid=%s: %s", user_uuid, e)
            return None

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
