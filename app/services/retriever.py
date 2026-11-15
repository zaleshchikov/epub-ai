import asyncpg

async def get_allowed_beats(conn: asyncpg.Connection, book_id: str, read_char_offset: int, limit: int = 10) -> list:
    """
    Возвращает beat'ы, которые полностью закончились ДО или НА позиции чтения.
    Берём последние `limit` битов (самые свежие перед позицией чтения),
    но отдаём их в ХРОНОЛОГИЧЕСКОМ порядке (старые -> новые), чтобы модель
    видела сюжет в правильном порядке, а не задом наперёд.
    """
    query = """
        SELECT id, chapter_hint, summary_past_safe, characters, tags
        FROM beats
        WHERE book_id = $1
          AND end_char <= $2
        ORDER BY end_char DESC
        LIMIT $3
    """
    rows = await conn.fetch(query, book_id, read_char_offset, limit)
    return [dict(r) for r in reversed(rows)]
