import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or (
        'dev-secret-key-change-in-production'
    )
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or (
        'sqlite:///ecommerce.db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Baidu Map config.
    BAIDU_MAP_ENABLED = (
        os.environ.get('BAIDU_MAP_ENABLED', 'false').lower() == 'true'
    )
    BAIDU_MAP_AK = os.environ.get('BAIDU_MAP_AK', '')
    # Browser AK used by the map picker.
    # Falls back to BAIDU_MAP_AK when empty.
    BAIDU_MAP_BROWSER_AK = (
        os.environ.get('BAIDU_MAP_BROWSER_AK')
        or BAIDU_MAP_AK
        or 'Mc5Jtr3iTP28Ejgy2H2SsfOJfNYrzeWh'
    )
    BAIDU_MAP_JS_VERSION = os.environ.get('BAIDU_MAP_JS_VERSION', '3.0')

    # Pagination configuration
    ITEMS_PER_PAGE = 20

    # Order cancellation window (minutes)
    ORDER_CANCEL_WINDOW_MINUTES = 5
