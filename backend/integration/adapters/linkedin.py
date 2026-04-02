from urllib.parse import quote, urlencode

import requests


def build_authorize_url(client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
    }
    return f"https://www.linkedin.com/oauth/v2/authorization?{urlencode(params, quote_via=quote)}"


def exchange_code_for_token(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    response = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        timeout=12,
    )
    response.raise_for_status()
    return response.json()


def _extract_legacy_name(profile: dict) -> tuple[str, str, str]:
    first_name = profile.get("localizedFirstName") or ""
    last_name = profile.get("localizedLastName") or ""

    if not first_name and isinstance(profile.get("firstName"), dict):
        localized = profile["firstName"].get("localized") or {}
        locale = profile["firstName"].get("preferredLocale") or {}
        key = f"{locale.get('language', 'en')}_{locale.get('country', 'US')}"
        first_name = localized.get(key) or next(iter(localized.values()), "")

    if not last_name and isinstance(profile.get("lastName"), dict):
        localized = profile["lastName"].get("localized") or {}
        locale = profile["lastName"].get("preferredLocale") or {}
        key = f"{locale.get('language', 'en')}_{locale.get('country', 'US')}"
        last_name = localized.get(key) or next(iter(localized.values()), "")

    full_name = f"{first_name} {last_name}".strip() or profile.get("formattedName") or "LinkedIn User"
    return first_name, last_name, full_name


def _get_profile_oidc(access_token: str) -> dict:
    response = requests.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()

    # Normalize keys to keep frontend/account service payload stable.
    data.setdefault("id", data.get("sub"))
    data.setdefault("email", data.get("email"))
    return data


def _get_profile_legacy(access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}

    profile_resp = requests.get("https://api.linkedin.com/v2/me", headers=headers, timeout=12)
    profile_resp.raise_for_status()
    profile_data = profile_resp.json()

    email_resp = requests.get(
        "https://api.linkedin.com/v2/emailAddress?q=members&projection=(elements*(handle~))",
        headers=headers,
        timeout=12,
    )
    email_resp.raise_for_status()
    email_data = email_resp.json()

    email = None
    elements = email_data.get("elements") or []
    if elements:
        email = (elements[0].get("handle~") or {}).get("emailAddress")

    first_name, last_name, full_name = _extract_legacy_name(profile_data)
    linkedin_id = profile_data.get("id")

    return {
        "sub": linkedin_id,
        "id": linkedin_id,
        "given_name": first_name,
        "family_name": last_name,
        "name": full_name,
        "email": email,
        "raw_profile": profile_data,
    }


def get_profile(access_token: str, preferred_mode: str = "auto") -> dict:
    mode = (preferred_mode or "auto").strip().lower()
    errors = []

    strategies = []
    if mode == "legacy":
        strategies = [_get_profile_legacy, _get_profile_oidc]
    elif mode == "oidc":
        strategies = [_get_profile_oidc, _get_profile_legacy]
    else:
        strategies = [_get_profile_oidc, _get_profile_legacy]

    for strategy in strategies:
        try:
            return strategy(access_token)
        except Exception as exc:
            errors.append(f"{strategy.__name__}: {exc}")

    raise RuntimeError(" ; ".join(errors))
