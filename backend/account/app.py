import sys
from pathlib import Path

from flask import Flask
from flask_cors import CORS
from sqlalchemy import inspect, text


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.account.config import AccountConfig
from backend.account.models import db
from backend.account.routes import account_bp


def ensure_account_schema() -> None:
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    alter_statements = []

    if "google_id" not in existing_columns:
        alter_statements.append("ALTER TABLE users ADD COLUMN google_id VARCHAR(128)")
    if "google_profile_json" not in existing_columns:
        alter_statements.append("ALTER TABLE users ADD COLUMN google_profile_json TEXT")
    if "phone" not in existing_columns:
        alter_statements.append("ALTER TABLE users ADD COLUMN phone VARCHAR(32)")
    if "address" not in existing_columns:
        alter_statements.append("ALTER TABLE users ADD COLUMN address VARCHAR(255)")
    if "date_of_birth" not in existing_columns:
        alter_statements.append("ALTER TABLE users ADD COLUMN date_of_birth DATE")
    if "bio" not in existing_columns:
        alter_statements.append("ALTER TABLE users ADD COLUMN bio TEXT")
    if "profile_updated_at" not in existing_columns:
        alter_statements.append("ALTER TABLE users ADD COLUMN profile_updated_at DATETIME")

    for statement in alter_statements:
        db.session.execute(text(statement))

    if alter_statements:
        db.session.commit()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(AccountConfig)

    CORS(app, supports_credentials=True)
    db.init_app(app)

    with app.app_context():
        db.create_all()
        ensure_account_schema()

    app.register_blueprint(account_bp, url_prefix="/api")
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5001, debug=True)
