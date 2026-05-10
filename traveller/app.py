import os
from pathlib import Path

from flask import Flask
from jinja2 import StrictUndefined

from traveller.migrate import maybe_import
from traveller.storage import Storage

STATE_DIR = Path(os.environ.get("STATE_DIRECTORY", "."))
DB_PATH = STATE_DIR / "traveller.db"
LEGACY_ZIP_PATH = STATE_DIR / "guide.zip"


def create_app() -> Flask:
    app = Flask(__name__)
    app.jinja_env.undefined = StrictUndefined

    storage = Storage(DB_PATH)
    # One-shot import of any legacy zip on first boot.
    maybe_import(storage, LEGACY_ZIP_PATH)
    app.config["storage"] = storage

    from traveller.blueprints.apis import api_bp
    from traveller.blueprints.views import views_bp

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
