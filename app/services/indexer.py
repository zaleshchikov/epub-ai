import json
import re
import uuid
import asyncio
from app.services.llm import call_llm

INDEXER_SYSTEM_PROMPT = """
Ты архивариус. Опиши текст коротко.
Ответь СТРОГО массивом JSON, вот точный пример формата:
[
  {
    "start_char": 0,
    "end_char": 150,
    "summary_past_safe": "Герой проснулся и посмотрел в окно."
  }
]
ПРАВИЛА:
1. ТОЛЬКО массив JSON. Никаких слов "Вот ваш JSON", никаких ```json.
2. summary_past_safe: максимум 1-2 коротких предложения в прошедшем времени.
"""

async def index_chunk(chunk_text: str, chunk_start: int, book_id: str, beat_counter: int) -> list:
    text_to_process = chunk_text[:2000]
    user_prompt = f"Текст:\n---\n{text_to_process}\n---\n\nВерни массив JSON."
    
    max_retries = 3
    response = ""
    
    # === МЕХАНИЗМ ПОВТОРНЫХ ПОПЫТОК (RETRY) ===
    for attempt in range(max_retries):
        try:
            response = await call_llm(INDEXER_SYSTEM_PROMPT, user_prompt, temperature=0.1)
            break # Если успешно, выходим из цикла retry
        except Exception as e:
            print(f"[indexer] Попытка {attempt+1} не удалась ({e}). Ждем 5 сек и пробуем снова...")
            await asyncio.sleep(5)
            
    # Если все 3 попытки провалились, используем Fallback, чтобы не ломать весь пайплайн
    if not response:
        print(f"[indexer] КРИТИЧЕСКАЯ ОШИБКА: LLM не отвечает. Используем автосводку.")
        safe_summary = text_to_process[:150].replace('\n', ' ').strip() + "..."
        return [{
            "beat_id": str(uuid.uuid4()),
            "book_id": book_id,
            "spine_index": 0,
            "start_char": chunk_start,
            "end_char": chunk_start + len(text_to_process),
            "start_block": 0, "end_block": 0, "char_offset": 0, "end_char_offset": 0,
            "chapter_hint": "Ошибка LLM",
            "summary_short": f"[Автосводка из-за сбоя LLM]: {safe_summary}",
            "summary_past_safe": f"[Автосводка из-за сбоя LLM]: {safe_summary}",
            "characters": [], "tags": []
        }]

    clean = response.strip()
    clean = re.sub(r'^```json\s*', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'^```\s*', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s*```$', '', clean)
    clean = clean.strip()

    beats_data = []

    try:
        data = json.loads(clean)
        if isinstance(data, list):
            beats_data = data
        elif isinstance(data, dict):
            beats_data = data.get("beats", [data])
    except json.JSONDecodeError as e:
        print(f"[indexer] JSON Decode Error: {e}. Пробуем регулярку...")
        pattern = r'"start_char"\s*:\s*(\d+)\s*,\s*"end_char"\s*:\s*(\d+)\s*,\s*"summary_past_safe"\s*:\s*"((?:[^"\\]|\\.)*)"'
        matches = re.finditer(pattern, clean, re.DOTALL)
        for match in matches:
            beats_data.append({
                "start_char": int(match.group(1)),
                "end_char": int(match.group(2)),
                "summary_past_safe": match.group(3).replace('\n', ' ')
            })

    if not beats_data:
        safe_summary = text_to_process[:150].replace('\n', ' ').strip() + "..."
        beats_data = [{
            "start_char": 0,
            "end_char": len(text_to_process),
            "summary_past_safe": f"[Автосводка]: {safe_summary}"
        }]

    result_beats = []
    for b in beats_data:
        try:
            s_char = int(b.get("start_char", 0))
        except (ValueError, TypeError):
            s_char = 0
            
        try:
            e_char = int(b.get("end_char", len(text_to_process)))
        except (ValueError, TypeError):
            e_char = len(text_to_process)
            
        if s_char < 0: s_char = 0
        if e_char < s_char: e_char = s_char + 100

        raw_summary = str(b.get("summary_past_safe", "Нет описания"))
        clean_summary = raw_summary.replace('\n', ' ').strip()[:500]

        result_beats.append({
            "beat_id": str(uuid.uuid4()),
            "book_id": book_id,
            "spine_index": 0,
            "start_char": chunk_start + s_char,
            "end_char": chunk_start + e_char,
            "start_block": 0,
            "end_block": 0,
            "char_offset": 0,
            "end_char_offset": 0,
            "chapter_hint": "Без названия",
            "summary_short": clean_summary,
            "summary_past_safe": clean_summary,
            "characters": [],
            "tags": []
        })
        beat_counter += 1
        
    return result_beats
