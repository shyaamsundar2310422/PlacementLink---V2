import pymysql.cursors
import sys
import os

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

def get_db_connection():
    options = dict(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        connect_timeout=Config.DB_CONNECT_TIMEOUT,
        cursorclass=pymysql.cursors.DictCursor
    )
    if Config.DB_SSL_CA:
        options['ssl'] = {
            'ca': Config.DB_SSL_CA,
            'check_hostname': True,
            'verify_mode': 'required',
        }
    elif Config.DB_SSL_MODE in {'required', 'verify-ca', 'verify_identity', 'verify-identity'}:
        options['ssl'] = {
            'check_hostname': Config.DB_SSL_MODE in {'verify_identity', 'verify-identity'},
            'verify_mode': 'required',
        }
    return pymysql.connect(**options)
