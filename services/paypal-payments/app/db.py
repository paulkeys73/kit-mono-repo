from app.config import settings

def get_db():
    conn = settings.get_db_connection()
    try:
        yield conn
    finally:
        conn.close()
