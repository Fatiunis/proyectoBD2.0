from flask import Flask
from flask_cors import CORS

from .config import SQLALCHEMY_DATABASE_URI
from .extensions import db
from .blueprints.auth import bp as auth_bp
from .blueprints.catalogo import bp as catalogo_bp
from .blueprints.checkout import bp as checkout_bp
from .blueprints.historial import bp as historial_bp
from .blueprints.vendedores import bp as vendedores_bp


def create_app():
    app = Flask(__name__)
    CORS(app)

    app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(catalogo_bp)
    app.register_blueprint(historial_bp)
    app.register_blueprint(vendedores_bp)

    return app
