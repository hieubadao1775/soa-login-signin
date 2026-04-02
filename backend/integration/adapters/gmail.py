import base64
from email.mime.text import MIMEText

import requests


def send_email(
    api_base: str,
    access_token: str,
    from_email: str,
    to_email: str,
    subject: str,
    body: str,
) -> dict:
    message = MIMEText(body)
    message["to"] = to_email
    message["from"] = from_email
    message["subject"] = subject

    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    endpoint = f"{api_base.rstrip('/')}/users/{from_email}/messages/send"
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"raw": encoded},
        timeout=12,
    )
    response.raise_for_status()
    return response.json()
