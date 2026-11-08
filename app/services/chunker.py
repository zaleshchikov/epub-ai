def chunk_text(text: str, chunk_size: int = 3000, overlap: int = 300) -> list:
    """
    Разбивает текст на чанки с гарантией отсутствия бесконечных циклов.
    """
    if not text:
        return []
    
    text_len = len(text)
    if text_len <= chunk_size:
        return [{"text": text, "start": 0, "end": text_len}]
    
    chunks = []
    start = 0
    
    while start < text_len:
        end = min(start + chunk_size, text_len)
        
        # Если мы достигли конца текста, забираем остаток и выходим из цикла
        if end == text_len:
            chunks.append({
                "text": text[start:end],
                "start": start,
                "end": end,
            })
            break
        
        # Пытаемся найти красивый разрыв (абзац или предложение) в последних 500 символах
        search_window = text[max(start, end - 500):end]
        
        break_pos = -1
        separator_len = 0
        for sep in ["\n\n", "\n", ". "]:
            pos = search_window.rfind(sep)
            if pos != -1:
                break_pos = pos
                separator_len = len(sep)
                break
        
        if break_pos != -1:
            # Сдвигаем end на найденный разделитель
            end = max(start, end - 500) + break_pos + separator_len
        
        chunks.append({
            "text": text[start:end],
            "start": start,
            "end": end,
        })
        
        # Следующий чанк начинается с перекрытием
        next_start = end - overlap
        
        # ЗАЩИТА ОТ БЕСКОНЕЧНОГО ЦИКЛА: 
        # Если по какой-то причине start не продвинулся вперед, принудительно сдвигаем его
        if next_start <= start:
            next_start = end
            
        start = next_start
    
    return chunks
