import logging
from urllib.parse import urlencode

import httpx

from app.utils.config import Settings

logger = logging.getLogger(__name__)


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
        logger.error("Zoho OAuth error parsed: error=%s, detail=%s", err, detail)
        raise RuntimeError(f"Zoho OAuth error ({err}): {detail}")

    def get_authorization_url(self, state: str) -> str:
        params = {
            "client_id": self._settings.zoho_client_id,
            "response_type": "code",
            "redirect_uri": self._settings.zoho_redirect_uri,
            "scope": "ZohoProjects.projects.ALL,ZohoProjects.tasks.ALL,ZohoProjects.users.READ",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        base = f"{self._accounts_base()}/oauth/v2/auth"
        auth_url = f"{base}?{urlencode(params)}"
        logger.info("Constructed Zoho authorization URL: %s", auth_url)
        return auth_url

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
        logger.info("Exchanging authorization code for tokens at URL: %s", url)
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
            payload = response.json()
            if response.is_error:
                logger.error("Zoho token exchange HTTP error: status=%s", response.status_code)
                self._parse_token_response(payload)
                response.raise_for_status()
            parsed = self._parse_token_response(payload)
            logger.info(
                "Successfully exchanged code. Has refresh_token: %s",
                "refresh_token" in parsed and bool(parsed["refresh_token"]),
            )
            return parsed

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
        logger.info("Attempting to refresh Zoho access token at URL: %s", url)
        if not refresh_token:
            logger.warning("refresh_token passed to refresh_token() is empty or None")
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
            payload = response.json()
            if response.is_error:
                logger.error("Zoho token refresh HTTP error: status=%s", response.status_code)
                self._parse_token_response(payload)
                response.raise_for_status()
            parsed = self._parse_token_response(payload)
            logger.info("Successfully refreshed Zoho access token")
            return parsed

