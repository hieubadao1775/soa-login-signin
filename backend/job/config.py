import os
from pathlib import Path

from backend.shared.config import BaseConfig, get_env_int, service_db_uri


class JobConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = service_db_uri("job")
    INTEGRATION_SERVICE_URL = os.getenv("INTEGRATION_SERVICE_URL", "http://localhost:5003")
    AI_SHORTLIST_THRESHOLD = float(os.getenv("AI_SHORTLIST_THRESHOLD", "70"))
    API_DEFAULT_PAGE_SIZE = get_env_int("JOB_API_DEFAULT_PAGE_SIZE", 20)
    API_MAX_PAGE_SIZE = get_env_int("JOB_API_MAX_PAGE_SIZE", 100)
    RESUME_MAX_MB = get_env_int("JOB_RESUME_MAX_MB", 5)
    MAX_CONTENT_LENGTH = RESUME_MAX_MB * 1024 * 1024
    RESUME_UPLOAD_DIR = os.getenv(
        "JOB_RESUME_UPLOAD_DIR",
        str((Path(__file__).resolve().parents[2] / "data" / "uploads" / "resumes").resolve()),
    )
