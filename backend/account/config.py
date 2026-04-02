from backend.shared.config import BaseConfig, service_db_uri


class AccountConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = service_db_uri("account")
