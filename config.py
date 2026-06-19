import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_NAME = os.getenv('DB_NAME', 'placement_db')
    SMTP_HOST = os.getenv('SMTP_HOST', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USER = os.getenv('SMTP_USER', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
    MAIL_FROM = os.getenv('MAIL_FROM', SMTP_USER)

    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
