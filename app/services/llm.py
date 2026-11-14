from openai import AsyncOpenAI
import os
import asyncio
import json
import re
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(
    api_key=os.getenv("LLM_API_KEY", "ollama"),
    base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
    timeout=300.0  # 5 минут!
)
MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")

def repair_json(text: str) -> str:
    open_quotes = text.count('"') % 2
    if open_quotes:
        text += '"'
    open_braces = text.count('{') - text.count('}')
    open_brackets = text.count('[') - text.count(']')
    if open_brackets > 0:
        text += ']' * open_brackets
    if open_braces > 0:
        text += '}' * open_braces
    return text


def clean_llm_response(raw: str) -> str:
    """
    Универсальный очиститель ТЕКСТОВОГО ответа модели.
    Снимает JSON-обёртки вида {"ответ": "..."}, двойную упаковку
    (JSON-строка внутри JSON) и code fences. Обычную прозу не трогает.
    """
    text = (raw or "").strip()
    for _ in range(3):  # защита от двойной вложенности
        t = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t).strip()
        if not t or t[0] not in '{["':
            return t
        try:
            data = json.loads(t)
        except json.JSONDecodeError:
            return t
        if isinstance(data, str):
            text = data.strip()
            continue
        if isinstance(data, dict):
            for key in ("ответ", "answer", "response", "text", "summary", "result"):
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    text = val.strip()
                    break
            else:
                return t
            continue
        return t
    return text.strip()


async def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.1,
                   max_tokens: int = 4000, json_mode: bool = True) -> str:
    # json_mode=True  -> индексатор: требуем JSON и чиним обрезанный JSON.
    # json_mode=False -> analyze/summarize: чистая проза, без JSON-приписки и без "починки".
    if json_mode:
        strict_system_prompt = system_prompt + "\n\nВАЖНО: Отвечай ТОЛЬКО валидным JSON. Начинай с '{' и заканчивай '}'."
    else:
        strict_system_prompt = system_prompt

    try:
        stream = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": strict_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            stream=True,
        )

        collected_messages = []
        token_count = 0
        start_time = asyncio.get_event_loop().time()

        async for chunk in stream:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > 240:  # Жесткий обрыв через 4 минуты, чтобы не висло навечно
                print(f"[LLM] Прервано по таймауту (240 сек)")
                break

            if token_count >= max_tokens:
                print(f"[LLM] Прервано по лимиту токенов ({max_tokens})")
                break

            if chunk.choices and chunk.choices[0].delta.content:
                collected_messages.append(chunk.choices[0].delta.content)
                token_count += 1

        full_response = "".join(collected_messages)
        print(f"[LLM] Получено {token_count} токенов, длина: {len(full_response)} символов")

        if json_mode:
            try:
                json.loads(full_response)
            except json.JSONDecodeError:
                print(f"[LLM] JSON обрезан, чиним...")
                full_response = repair_json(full_response)

        return full_response
    except Exception as e:
        print(f"[LLM] Ошибка: {e}")
        raise
