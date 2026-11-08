-- init.sql
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Книги пользователя
CREATE TABLE books (
    id UUID PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    title VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',  -- pending / indexing / ready / failed
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. Полный нормализованный текст книги (для индексации)
CREATE TABLE book_text (
    book_id UUID PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
    full_text TEXT NOT NULL
);

-- 3. Beat-карточки (индекс)
CREATE TABLE beats (
    id VARCHAR(50) PRIMARY KEY,
    book_id UUID REFERENCES books(id) ON DELETE CASCADE,
    start_char INT NOT NULL,
    end_char INT NOT NULL,
    chapter_hint VARCHAR(255),
    summary_short TEXT,
    summary_past_safe TEXT,
    characters TEXT[],
    tags TEXT[],
    embedding vector(1024)
);

-- Индекс для быстрой spoiler-safe фильтрации по позиции
CREATE INDEX idx_beats_pos ON beats (book_id, end_char);

-- 4. Кэш ответов AI
CREATE TABLE ai_cache (
    hash VARCHAR(64) PRIMARY KEY,
    response JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
