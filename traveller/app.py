from flask import Flask
from jinja2 import StrictUndefined
from traveller.classes import Guide

GUIDE_PATH = "korea.zip"


def create_app():
    app = Flask(__name__)
    app.jinja_env.undefined = StrictUndefined
    guide = Guide.from_zip(GUIDE_PATH)
    app.config["guide"] = guide

    # Register blueprints
    from traveller.blueprints.apis import api_bp
    from traveller.blueprints.views import views_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    # @app.context_processor
    # def inject_guide():
    #     return {'GUIDE': GUIDE}

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
