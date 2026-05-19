import httpx
from typing import Any, Optional
from urllib.parse import urlparse


class UazapiClient:
    """Cliente HTTP para a instância fixa uazapiGO (v2)."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    @classmethod
    def from_subdomain(cls, subdomain: str) -> "UazapiClient":
        return cls(f"https://{subdomain}.uazapi.com")

    @staticmethod
    def subdomain_from_base_url(base_url: str) -> str:
        host = urlparse(base_url).hostname or ""
        return host.split(".")[0] if host else "free"

    @staticmethod
    def instance_headers(token: str) -> dict[str, str]:
        return {"token": token, "Content-Type": "application/json"}

    async def request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        json: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = self.instance_headers(token)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(method, url, headers=headers, json=json)

        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}

        if response.status_code >= 400:
            return {
                "sucesso": False,
                "status_code": response.status_code,
                "erro": body.get("message") or body.get("error") or response.text,
                "detalhes": body,
            }

        return {"sucesso": True, "status_code": response.status_code, "dados": body}

    async def instance_status(self, token: str):
        return await self.request("GET", "/instance/status", token=token)

    async def list_groups(self, token: str):
        return await self.request("GET", "/group/list", token=token)

    async def group_info(self, token: str, groupjid: str):
        return await self.request(
            "POST", "/group/info", token=token, json={"groupjid": groupjid}
        )

    async def send_text(self, token: str, payload: dict[str, Any]):
        return await self.request("POST", "/send/text", token=token, json=payload)

    async def get_webhook(self, token: str):
        return await self.request("GET", "/webhook", token=token)

    async def set_webhook(self, token: str, payload: dict[str, Any]):
        return await self.request("POST", "/webhook", token=token, json=payload)
