import asyncpg
import os

# Явные настройки подключения (берутся из .env, но имеют надёжные значения по умолчанию)
DB_USER = os.getenv("DB_USER", "epub_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "epub_pass")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "epub_ai")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

_pool = None

async def init_pool():
    """Инициализация пула соединений. Вызывается при старте приложения."""
    global _pool
    if _pool is None:
        print(f"[DB] Подключение к базе: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=5,
            command_timeout=60,
            server_settings={'application_name': 'epub_ai_backend'}
        )
    return _pool

async def get_db():
    """Получить соединение из пула. Автоматически пересоздаёт, если пул мёртв."""
    global _pool
    if _pool is None:
        await init_pool()
    
    try:
        conn = await _pool.acquire()
        return conn
    except Exception as e:
        print(f"[DB] Пул мёртв, пересоздаём: {e}")
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=5,
            command_timeout=60
        )
        conn = await _pool.acquire()
        return conn

async def release_db(conn):
    """Вернуть соединение в пул."""
    global _pool
    if _pool and conn:
        await _pool.release(conn)

async def close_pool():
    """Закрыть пул при остановке приложения."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
