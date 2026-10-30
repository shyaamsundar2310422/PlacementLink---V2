import os
from urllib.parse import parse_qs, unquote, urlparse
from dotenv import load_dotenv

load_dotenv()


def _database_settings():
    """Resolve either a MySQL URL or the existing individual DB variables."""
    database_url = os.getenv('DATABASE_URL', '').strip()
    if database_url:
        parsed = urlparse(database_url)
        if parsed.scheme not in {'mysql', 'mysql+pymysql'} or not parsed.hostname or not parsed.path.lstrip('/'):
            raise ValueError('DATABASE_URL must be a valid mysql:// connection URL.')
        query = parse_qs(parsed.query)
        return {
            'host': parsed.hostname,
            'port': parsed.port or 3306,
            'user': unquote(parsed.username or ''),
            'password': unquote(parsed.password or ''),
            'database': unquote(parsed.path.lstrip('/')),
            'ssl_ca': query.get('ssl_ca', [os.getenv('DB_SSL_CA', '')])[0],
            'ssl_mode': query.get('ssl-mode', query.get('ssl_mode', [os.getenv('DB_SSL_MODE', 'disabled')]))[0].lower(),
        }
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '3306')),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'placement_db'),
        'ssl_ca': os.getenv('DB_SSL_CA', ''),
        'ssl_mode': os.getenv('DB_SSL_MODE', 'disabled').lower(),
    }


_DB_SETTINGS = _database_settings()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY') or 'default-secret-key'
    APP_ENV = os.getenv('APP_ENV', 'development').lower()
    DB_HOST = _DB_SETTINGS['host']
    DB_PORT = _DB_SETTINGS['port']
    DB_USER = _DB_SETTINGS['user']
    DB_PASSWORD = _DB_SETTINGS['password']
    DB_NAME = _DB_SETTINGS['database']
    DB_SSL_CA = _DB_SETTINGS['ssl_ca']
    DB_SSL_MODE = _DB_SETTINGS['ssl_mode']
    DB_CONNECT_TIMEOUT = int(os.getenv('DB_CONNECT_TIMEOUT', '10'))
    SMTP_HOST = os.getenv('SMTP_HOST', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USER = os.getenv('SMTP_USER', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
    MAIL_FROM = os.getenv('MAIL_FROM', SMTP_USER)

    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.abspath(os.getenv('UPLOAD_FOLDER') or os.path.join(BASE_DIR, 'static/uploads'))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', str(16 * 1024 * 1024)))
    SESSION_COOKIE_SECURE = APP_ENV == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
