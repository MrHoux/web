import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DEFAULT_DB = os.path.join(BASE_DIR, 'instance', 'ecommerce.db')


class Config:
    SECRET_KEY = 'novamart-demo-secret'
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DEFAULT_DB}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Baidu Map config.
    BAIDU_MAP_ENABLED = True
    BAIDU_MAP_AK = 'Mc5Jtr3iTP28Ejgy2H2SsfOJfNYrzeWh'
    # Browser AK used by the map picker.
    # Falls back to BAIDU_MAP_AK when empty.
    BAIDU_MAP_BROWSER_AK = BAIDU_MAP_AK
    BAIDU_MAP_JS_VERSION = '3.0'

    # Pagination configuration
    ITEMS_PER_PAGE = 20

    # Order cancellation window (minutes)
    ORDER_CANCEL_WINDOW_MINUTES = 5
