import json
import hashlib
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.db import get_db, release_db, init_pool, close_pool
from app.services.epub_parser import parse_epub
from app.services.chunker import chunk_text
from app.services.indexer import index_chunk
from app.services.retriever import get_allowed_beats
from app.services.llm import call_llm

app = FastAPI(title="EPUB AI Agent v0.2 (LLM-driven structure)")

# Стоп-слова для пост-проверки на спойлеры
SPOILER_KEYWORDS = ["позже выяснится", "в конце", "окажется", "в финале", "затем", "вскоре"]

class CanonicalPos(BaseModel):
    char_offset: int

class AnalyzeRequest(BaseModel):
    user_id: str = "test-user"
    book_id: str
    selected_text: str
    read_pos: CanonicalPos
    local_context: Optional[dict] = {}
    language: str = "ru"
    mode: str = "explain"

@app.on_event("startup")
async def startup_event():
    await init_pool()

@app.on_event("shutdown")
async def shutdown_event():
    await close_pool()


# ==========================================
# 1. ЗАГРУЗКА КНИГИ
# ==========================================
@app.post("/v1/books/upload")
async def upload_epub(file: UploadFile = File(...), user_id: str = "test-user"):
    if not file.filename.lower().endswith(".epub"):
        raise HTTPException(400, "Только EPUB файлы")

    file_bytes = await file.read()
    parsed = parse_epub(file_bytes)

    book_id = str(uuid.uuid4())
    conn = await get_db()
    try:
        await conn.execute(
            """INSERT INTO books (id, user_id, sha256, title, status)
               VALUES ($1, $2, $3, $4, 'pending')""",
            book_id, user_id, parsed["sha256"], parsed["title"],
        )
        await conn.execute(
            "INSERT INTO book_text (book_id, full_text) VALUES ($1, $2)",
            book_id, parsed["full_text"],
        )
    except Exception as e:
        raise HTTPException(500, f"Ошибка сохранения в БД: {e}")
    finally:
        await release_db(conn)

    return {
        "book_id": book_id,
        "title": parsed["title"],
        "text_length": len(parsed["full_text"]),
        "sha256": parsed["sha256"],
    }


# ==========================================
# 2. ИНДЕКСАЦИЯ (с пулом соединений)
# ==========================================
@app.post("/v1/books/{book_id}/index")
async def index_book(book_id: str):
    # Получаем текст книги
    conn = await get_db()
    try:
        book = await conn.fetchrow("SELECT * FROM books WHERE id = $1", book_id)
        if not book:
            raise HTTPException(404, "Книга не найдена")

        full_text = await conn.fetchval("SELECT full_text FROM book_text WHERE book_id = $1", book_id)
        if not full_text:
            raise HTTPException(400, "Текст книги не найден. Загрузите заново.")

        # Удаляем старые биты
        await conn.execute("DELETE FROM beats WHERE book_id = $1", book_id)
        await conn.execute("UPDATE books SET status = 'indexing' WHERE id = $1", book_id)
    finally:
        await release_db(conn)

    # Нарезка на чанки
    chunks = chunk_text(full_text, chunk_size=3000, overlap=300)
    print(f"[index] Книга разбита на {len(chunks)} чанков")

    beat_counter = 0
    total_beats = 0

    try:
        for i, chunk in enumerate(chunks):
            print(f"[index] Обработка чанка {i+1}/{len(chunks)}...")
            
            # Вызов LLM (занимает 30-60 секунд, соединение с БД не нужно)
            beats = await index_chunk(
                chunk["text"],
                chunk["start"],
                book_id,
                beat_counter,
            )
            
            # Берём СВЕЖЕЕ соединение из пула для записи в БД
            conn = await get_db()
            try:
                for b in beats:
                    await conn.execute(
                        """INSERT INTO beats (
                            id, book_id, start_char, end_char,
                            chapter_hint, summary_short, summary_past_safe,
                            characters, tags
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                        b["beat_id"], book_id,
                        b["start_char"], b["end_char"],
                        b.get("chapter_hint", ""),
                        b.get("summary_short", ""),
                        b.get("summary_past_safe", ""),
                        b.get("characters", []),
                        b.get("tags", []),
                    )
                    beat_counter += 1
                    total_beats += 1
            finally:
                await release_db(conn)

        # Обновляем статус на ready
        conn = await get_db()
        try:
            await conn.execute("UPDATE books SET status = 'ready' WHERE id = $1", book_id)
        finally:
            await release_db(conn)

        return {"status": "ready", "beats_created": total_beats, "chunks_processed": len(chunks)}
    
    except Exception as e:
        print(f"❌ ОШИБКА ИНДЕКСАЦИИ: {e}")
        conn = await get_db()
        try:
            await conn.execute("UPDATE books SET status = 'failed' WHERE id = $1", book_id)
        finally:
            await release_db(conn)
        raise HTTPException(500, f"Ошибка индексации: {e}")


# ==========================================
# 3. AI-РАЗБОР (Spoiler-safe)
# ==========================================
@app.post("/v1/ai/analyze")
async def analyze_text(req: AnalyzeRequest):
    conn = await get_db()
    try:
        # 1. Проверка кэша
        cache_raw = f"{req.user_id}|{req.book_id}|{req.selected_text}|{req.read_pos.model_dump_json()}"
        cache_hash = hashlib.sha256(cache_raw.encode()).hexdigest()
        
        cached = await conn.fetchval("SELECT response FROM ai_cache WHERE hash = $1", cache_hash)
        if cached:
            return {"answer": cached, "cached": True, "used_beats": []}

        # 2. Spoiler-safe retrieval
        allowed_beats = await get_allowed_beats(conn, req.book_id, req.read_pos.char_offset)
    finally:
        await release_db(conn)
    
    context_str = "\n".join([
        f"- [{b['chapter_hint'] or 'Без названия'}] {b['summary_past_safe']}" 
        for b in allowed_beats
    ])

    system_prompt = """
Ты AI-наставник для читателя. Отвечай на вопросы по выделенному тексту.

СТРОГИЕ ПРАВИЛА:
1. Используй ТОЛЬКО факты из ALLOWED_BEATS и LOCAL_CONTEXT.
2. ЗАПРЕЩЕНО упоминать события, персонажей или факты, которых нет в ALLOWED_BEATS.
3. ЗАПРЕЩЕНЫ фразы: "позже", "в конце", "окажется", "вскоре", "затем выяснится".
4. Если данных не хватает — честно скажи: "В доступном пока контексте этого нет, читайте дальше".
5. Ответ: 120–180 слов, на языке пользователя.
"""

    user_prompt = f"""
READ_POS: символ {req.read_pos.char_offset}

LOCAL_CONTEXT:
{json.dumps(req.local_context, ensure_ascii=False)}

SELECTED TEXT:
{req.selected_text}

ALLOWED_BEATS (только уже прочитанное):
{context_str if context_str else '(пусто — читатель в самом начале книги)'}

Задача: объясни выделенный текст с учётом контекста. Язык: {req.language}.
"""

    answer = await call_llm(system_prompt, user_prompt, temperature=0.3)

    # Post-check на спойлеры
    for kw in SPOILER_KEYWORDS:
        if kw in answer.lower():
            answer = "В доступном пока контексте этого нет — читайте дальше."
            break

    # Сохранение в кэш
    conn = await get_db()
    try:
        await conn.execute(
            "INSERT INTO ai_cache (hash, response) VALUES ($1, $2)",
            cache_hash, json.dumps({"answer": answer}, ensure_ascii=False),
        )
    finally:
        await release_db(conn)

    return {
        "answer": answer,
        "cached": False,
        "used_beats": [b["id"] for b in allowed_beats],
    }


# ==========================================
# 4. СТАТУС И УДАЛЕНИЕ
# ==========================================
@app.get("/v1/books/{book_id}/status")
async def book_status(book_id: str):
    conn = await get_db()
    try:
        row = await conn.fetchrow("SELECT status, title FROM books WHERE id = $1", book_id)
        if not row:
            raise HTTPException(404, "Книга не найдена")
        return {"book_id": book_id, "status": row["status"], "title": row["title"]}
    finally:
        await release_db(conn)


@app.delete("/v1/books/{book_id}")
async def delete_book(book_id: str):
    conn = await get_db()
    try:
        await conn.execute("DELETE FROM ai_cache WHERE hash LIKE $1", f"%{book_id}%")
        await conn.execute("DELETE FROM books WHERE id = $1", book_id)
        return {"status": "deleted", "book_id": book_id}
    finally:
        await release_db(conn)
