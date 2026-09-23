import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

def get_db_connection():
    """Создает и возвращает подключение к базе данных."""
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        cursor_factory=RealDictCursor # Чтобы ответы от БД приходили в виде удобных словарей (JSON)
    )
    return conn