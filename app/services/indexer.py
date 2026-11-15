import uuid
import asyncio
from app.services.llm import call_llm, clean_llm_response

INDEXER_SYSTEM_PROMPT = """
Ты архивариус. Кратко перескажи ВЕСЬ предоставленный фрагмент текста.
ПРАВИЛА:
1. Ответь ТОЛЬКО обычным связным текстом на русском языке.
2. Никакого JSON, фигурных скобок, markdown и списков.
3. Ровно 2-3 предложения в прошедшем времени.
4. Опиши весь фрагмент целиком, а не только его начало.
5. Используй только факты из текста, ничего не придумывай и не добавляй от себя.
6. Не пиши о том, что будет дальше: запрещены слова "позже", "в конце", "окажется", "вскоре".
"""


async def index_chunk(chunk_text: str, chunk_start: int, book_id: str, beat_counter: int) -> list:
    """
    Стратегия B: один бит на весь чанк.
    - Саммари всего куска обычным текстом (без JSON -> нечему ломаться).
    - Оффсеты задаются кодом: start=chunk_start, end=chunk_start+len(текст).
      Модель их не выдумывает -> покрытие 100% и безопасный гейтинг по концу чанка.
    beat_counter оставлен в сигнатуре для совместимости с вызовом в main.py.
    """
    text_to_process = chunk_text  # весь чанк, без обрезки
    user_prompt = (
        f"Фрагмент ({len(text_to_process)} символов):\n"
        f"---\n{text_to_process}\n---\n\n"
        f"Кратко перескажи ВЕСЬ фрагмент в 2-3 предложениях в прошедшем времени."
    )

    max_retries = 3
    summary = ""

    for attempt in range(max_retries):
        try:
            raw = await call_llm(
                INDEXER_SYSTEM_PROMPT, user_prompt,
                temperature=0.1, json_mode=False,
            )
            candidate = " ".join(clean_llm_response(raw).split())[:500]
            if candidate:
                summary = candidate
                break
            print(f"[indexer] Пустой ответ (попытка {attempt+1}), повторяем...")
        except Exception as e:
            print(f"[indexer] Попытка {attempt+1} не удалась ({e}).")
        if attempt < max_retries - 1:
            await asyncio.sleep(5)

    if not summary:
        print("[indexer] LLM не ответила, используем автосводку.")
        safe = " ".join(text_to_process[:200].split())
        summary = f"[Автосводка из-за сбоя LLM]: {safe}..."

    return [{
        "beat_id": str(uuid.uuid4()),
        "book_id": book_id,
        "spine_index": 0,
        "start_char": chunk_start,
        "end_char": chunk_start + len(text_to_process),
        "start_block": 0,
        "end_block": 0,
        "char_offset": 0,
        "end_char_offset": 0,
        "chapter_hint": "Без названия",
        "summary_short": summary,
        "summary_past_safe": summary,
        "characters": [],
        "tags": [],
    }]
