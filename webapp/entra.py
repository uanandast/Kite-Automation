"""Microsoft Entra ID authorization-code-flow helpers."""

from typing import Any

from msal import ConfidentialClientApplication

from webapp.settings import Settings

# MSAL adds the OpenID Connect reserved scopes (openid, profile, offline_access)
# itself. Supplying them explicitly raises a ValueError in MSAL.
SCOPES = ["email"]


def create_client(settings: Settings) -> ConfidentialClientApplication:
    return ConfidentialClientApplication(
        client_id=settings.entra_client_id,
        client_credential=settings.entra_client_secret,
        authority=f"https://login.microsoftonline.com/{settings.entra_tenant_id}",
    )


def start_login(settings: Settings) -> dict[str, Any]:
    return create_client(settings).initiate_auth_code_flow(
        scopes=SCOPES, redirect_uri=settings.entra_redirect_uri
    )


def complete_login(settings: Settings, flow: dict[str, Any], response: dict[str, Any]):
    return create_client(settings).acquire_token_by_auth_code_flow(flow, response)


def email_from_claims(claims: dict[str, Any]) -> str:
    """Use the Entra sign-in name when the optional email claim is absent."""
    return str(
        claims.get("email") or claims.get("preferred_username") or claims.get("upn") or ""
    ).strip().lower()
