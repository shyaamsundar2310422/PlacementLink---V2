import pymysql
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

def init_db():
    # Connect without specifying database to create it
    connection = pymysql.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD
    )
    
    try:
        with connection.cursor() as cursor:
            schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
            with open(schema_path, 'r') as file:
                sql_script = file.read()
            
            statements = [s.strip() for s in sql_script.split(';') if s.strip()]
            for statement in statements:
                cursor.execute(statement)
        
        connection.commit()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Error initializing database: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    init_db()
