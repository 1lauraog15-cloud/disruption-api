"""Flight disruption tracking API (demo project, synthetic data only)."""

from flask import Flask
from sqlalchemy import Engine

from .config import Settings
from .db import make_engine, make_session_factory
from .routes import bp


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> Flask:
    settings = settings or Settings.from_env()
    app = Flask(__name__)
    app.extensions["api_key_hashes"] = settings.api_key_hashes
    app.extensions["session_factory"] = make_session_factory(engine or make_engine(settings.database_url))
    app.register_blueprint(bp)
    return app
