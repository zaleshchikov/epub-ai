import os
import hashlib
import tempfile
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

def parse_epub(file_bytes: bytes) -> dict:
    """
    Извлекает из EPUB только сырой текст. 
    Структуру (главы, beat'ы) определит LLM.
    """
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    
    # 1. Создаем временный файл, так как ebooklib требует путь к файлу
    with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp_file:
        tmp_file.write(file_bytes)
        tmp_file_path = tmp_file.name

    try:
        # 2. Читаем EPUB из временного файла
        book = epub.read_epub(tmp_file_path, options={"ignore_ncx": True})
    finally:
        # 3. Обязательно удаляем временный файл после чтения, чтобы не засорять диск
        if os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)

    title_meta = book.get_metadata("DC", "title")
    title = title_meta[0][0] if title_meta else "Unknown"

    # Собираем текст в порядке spine
    spine_ids = [item_id for item_id, _ in book.spine]
    items_by_id = {item.get_id(): item for item in book.get_items()}

    full_text_parts = []
    for idx, item_id in enumerate(spine_ids):
        item = items_by_id.get(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        html = item.get_content().decode("utf-8", errors="ignore")
        try:
            soup = BeautifulSoup(html, "lxml", features="xml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")

        text = soup.get_text(separator="\n", strip=True)
        if text:
            full_text_parts.append(text)

    full_text = "\n\n".join(full_text_parts)

    return {
        "sha256": sha256,
        "title": title,
        "full_text": full_text,
    }
