import sys
from pathlib import Path

from flask import Flask
from flask_cors import CORS
from sqlalchemy import inspect, text


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.job.config import JobConfig
from backend.job.models import db
from backend.job.routes import job_bp


JOB_SCHEMA_VERSION = "job-board-v2-2026-03-31"


def ensure_job_schema() -> None:
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    current_version = None

    if "schema_meta" in tables:
        current_version = db.session.execute(text("SELECT version FROM schema_meta WHERE id = 1")).scalar()

    if current_version == JOB_SCHEMA_VERSION:
        return

    db.session.execute(text("PRAGMA foreign_keys = OFF"))
    for table_name in tables:
        if table_name.startswith("sqlite_"):
            continue
        db.session.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
    db.session.execute(text("PRAGMA foreign_keys = ON"))
    db.session.commit()

    db.create_all()
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                id INTEGER PRIMARY KEY,
                version VARCHAR(128) NOT NULL
            )
            """
        )
    )
    db.session.execute(text("DELETE FROM schema_meta"))
    db.session.execute(
        text("INSERT INTO schema_meta (id, version) VALUES (1, :version)"),
        {"version": JOB_SCHEMA_VERSION},
    )
    db.session.commit()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(JobConfig)

    CORS(app, supports_credentials=True)
    db.init_app(app)

    with app.app_context():
        db.create_all()
        ensure_job_schema()

    app.register_blueprint(job_bp, url_prefix="/api")
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5002, debug=True)
