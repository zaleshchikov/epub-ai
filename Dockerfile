# Используем официальный легкий образ Python
FROM python:3.12-slim

# Устанавливаем переменные окружения для Python (оптимизация)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Рабочая директория в контейнере
WORKDIR /app

# Устанавливаем системные зависимости (если нужны для psycopg2/asyncpg и т.д.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Открываем порт, который слушает Uvicorn
EXPOSE 8000

# Команда запуска (используем gunicorn или uvicorn с воркерами для продакшена)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
