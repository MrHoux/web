from flask import Flask
from flask_migrate import Migrate
from flask_login import LoginManager
from app.extensions import db
from app.config import Config
from app.middleware import setup_auth_middleware
import logging
import os
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Prefer UTC+8 (Asia/Shanghai) for log timestamps on Linux (WSL). Storage
# in DB remains UTC.
try:
    os.environ.setdefault('TZ', 'Asia/Shanghai')
    time.tzset()
except Exception:
    pass

migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'


def create_app(config_class=Config):
    static_dir = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "static"))
    app = Flask(
        __name__,
        static_folder=static_dir,
        static_url_path="/static",
    )
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Setup user loader
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from app.blueprints import (
        account,
        admin,
        api,
        auth,
        cart,
        chat,
        merchant,
        orders,
        products,
        public,
        reviews,
    )

    app.register_blueprint(auth.bp, url_prefix='/')
    app.register_blueprint(public.bp, url_prefix='/')
    app.register_blueprint(products.bp, url_prefix='/')
    app.register_blueprint(cart.bp, url_prefix='/')
    app.register_blueprint(orders.bp, url_prefix='/')
    app.register_blueprint(reviews.bp, url_prefix='/')
    app.register_blueprint(account.bp, url_prefix='/')
    # These blueprints already use absolute routes.
    # Using url_prefix here would double the path.
    app.register_blueprint(merchant.bp, url_prefix='/')
    app.register_blueprint(admin.bp, url_prefix='/')
    app.register_blueprint(api.bp, url_prefix='/')
    app.register_blueprint(chat.bp, url_prefix='/')

    # Setup authentication middleware (site-wide login protection)
    setup_auth_middleware(app)

    # Note: Database tables are managed via Flask-Migrate
    # Use 'flask db upgrade' to create/update tables

    logger.info("Flask application initialized")
    return app
