from urllib.parse import quote, urlencode

import requests


def build_authorize_url(client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
        "include_granted_scopes": "true",
        "prompt": "select_account",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params, quote_via=quote)}"


def exchange_code_for_token(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=12,
    )
    response.raise_for_status()
    return response.json()


def get_profile(access_token: str) -> dict:
    response = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()

    data.setdefault("id", data.get("sub"))
    data.setdefault("email", data.get("email"))
    data.setdefault("name", data.get("name"))
    return data
