import os

from backend.shared.config import BaseConfig


class IntegrationConfig(BaseConfig):
    LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
    LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
    LINKEDIN_REDIRECT_URI = os.getenv(
        "LINKEDIN_REDIRECT_URI",
        "http://localhost:5003/api/integrations/linkedin/callback",
    )
    LINKEDIN_FRONTEND_CALLBACK_URI = os.getenv(
        "LINKEDIN_FRONTEND_CALLBACK_URI",
        "http://localhost:5004/oauth/linkedin/callback",
    )
    LINKEDIN_SCOPE = os.getenv("LINKEDIN_SCOPE", "r_liteprofile r_emailaddress")

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:5003/api/integrations/google/callback",
    )
    GOOGLE_FRONTEND_CALLBACK_URI = os.getenv(
        "GOOGLE_FRONTEND_CALLBACK_URI",
        "http://localhost:5004/oauth/google/callback",
    )
    GOOGLE_SCOPE = os.getenv("GOOGLE_SCOPE", "openid email profile")

    GMAIL_API_BASE = os.getenv("GMAIL_API_BASE", "https://gmail.googleapis.com/gmail/v1")
    CALENDAR_API_BASE = os.getenv("CALENDAR_API_BASE", "https://www.googleapis.com/calendar/v3")

    AI_API_URL = os.getenv("AI_API_URL", "")
    AI_POTENTIAL_CANDIDATES_URL = os.getenv("AI_POTENTIAL_CANDIDATES_URL", "")
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "12"))
