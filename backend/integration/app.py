import sys
from pathlib import Path

from flask import Flask
from flask_cors import CORS


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.integration.config import IntegrationConfig
from backend.integration.routes import integration_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(IntegrationConfig)

    CORS(app, supports_credentials=True)
    app.register_blueprint(integration_bp, url_prefix="/api")
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5003, debug=True)
