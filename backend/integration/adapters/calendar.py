import uuid

import requests


def create_event(
    api_base: str,
    access_token: str,
    calendar_id: str,
    summary: str,
    description: str,
    start_iso: str,
    end_iso: str,
    attendees: list,
) -> dict:
    endpoint = f"{api_base.rstrip('/')}/calendars/{calendar_id}/events?conferenceDataVersion=1"

    payload = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
        "attendees": [{"email": email} for email in attendees if email],
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }

    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=12,
    )
    response.raise_for_status()
    return response.json()
