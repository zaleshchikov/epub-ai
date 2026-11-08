from pydantic import BaseModel
from typing import List, Optional

class CanonicalPos(BaseModel):
    spine_index: int
    block_index: int
    char_offset: int

class AnalyzeRequest(BaseModel):
    user_id: str = "test-user"
    book_id: str
    selected_text: str
    read_pos: CanonicalPos
    local_context: Optional[dict] = {}
    language: str = "ru"
    mode: str = "explain"
