from urllib.parse import urlencode

import httpx

from app.utils.config import Settings


class ZohoAuthService:
    """OAuth2 flow for Zoho (supports regional accounts servers, e.g. .in / .eu)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _accounts_base(self, accounts_url: str | None = None) -> str:
        base = (accounts_url or self._settings.zoho_accounts_url).strip()
        return base.rstrip("/")

    @staticmethod
    def _parse_token_response(payload: dict) -> dict:
        if payload.get("access_token"):
            return payload
        err = payload.get("error", "token_exchange_failed")
        detail = (
            payload.get("error_description")
            or payload.get("message")
            or str(payload)
        )
        raise RuntimeError(f"Zoho OAuth error ({err}): {detail}")

    def get_authorization_url(self, state: str) -> str:
        params = {
            "client_id": self._settings.zoho_client_id,
            "response_type": "code",
            "redirect_uri": self._settings.zoho_redirect_uri,
            "scope": "ZohoProjects.projects.ALL,ZohoProjects.tasks.ALL,ZohoProjects.users.READ",
            "access_type": "offline",
            "state": state,
        }
        base = f"{self._accounts_base()}/oauth/v2/auth"
        return f"{base}?{urlencode(params)}"

    async def exchange_code(self, code: str, *, accounts_url: str | None = None) -> dict:
        """Exchange authorization code for tokens."""
        url = f"{self._accounts_base(accounts_url)}/oauth/v2/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": self._settings.zoho_client_id,
            "client_secret": self._settings.zoho_client_secret,
            "redirect_uri": self._settings.zoho_redirect_uri,
            "code": code,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
            payload = response.json()
            if response.is_error:
                self._parse_token_response(payload)
                response.raise_for_status()
            return self._parse_token_response(payload)

    async def refresh_token(
        self, refresh_token: str, *, accounts_url: str | None = None
    ) -> dict:
        url = f"{self._accounts_base(accounts_url)}/oauth/v2/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": self._settings.zoho_client_id,
            "client_secret": self._settings.zoho_client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
            payload = response.json()
            if response.is_error:
                self._parse_token_response(payload)
                response.raise_for_status()
            return self._parse_token_response(payload)
