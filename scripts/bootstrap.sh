#!/bin/bash
set -e

echo "🚀 Запуск полной автоматической настройки VPS..."

# 1. Установка Docker (идемпотентно)
if ! command -v docker &> /dev/null; then
    echo "📦 Установка Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker установлен."
else
    echo "✅ Docker уже установлен."
fi

# 2. Установка Ollama (идемпотентно)
if ! command -v ollama &> /dev/null; then
    echo "🧠 Установка Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    sudo systemctl start ollama
    sudo systemctl enable ollama
    echo "✅ Ollama установлен и запущен."
else
    echo "✅ Ollama уже установлен."
fi

# 3. НАСТРОЙКА СЕТИ OLLAMA (Критически важно для связи с Docker)
echo "⚙️ Настройка Ollama для доступа из Docker-контейнеров (0.0.0.0)..."
sudo mkdir -p /etc/systemd/system/ollama.service.d
cat <<EOF | sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
sudo systemctl restart ollama

# Даем сервису 2 секунды на полноценный запуск и открытие сокета
sleep 2

# Проверяем, что сервис действительно отвечает, прежде чем идти дальше
if ! curl -s http://localhost:11434 > /dev/null; then
    echo "⚠️ Ollama не отвечает, пытаемся перезапустить еще раз..."
    sudo systemctl restart ollama
    sleep 3
fi
echo "✅ Ollama теперь слушает все интерфейсы и готов к работе."

# 4. Загрузка модели 14B (идемпотентно: если есть, просто проверит хэш)
echo "⏳ Проверка/загрузка модели qwen2.5:14b..."
ollama pull qwen2.5:14b

# 5. Клонирование или обновление репозитория
if [ ! -d "$HOME/epub-ai" ]; then
    echo "📥 Клонирование репозитория..."
    git clone https://${GH_USER}:${GH_TOKEN}@github.com/${GH_REPO}.git $HOME/epub-ai
else
    echo "🔄 Обновление существующего репозитория..."
    cd $HOME/epub-ai
    git fetch origin
    git reset --hard origin/main
    git clean -fd
    echo "✅ Репозиторий обновлен."
fi

cd $HOME/epub-ai

# 6. Создание или обновление .env файла
if [ ! -f ".env" ]; then
    echo "⚙️ Создание базового .env файла..."
    cat <<EOF > .env
DB_USER=epub_user
DB_PASSWORD=epub_pass
DB_HOST=db
DB_PORT=5432
DB_NAME=epub_ai
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen2.5:14b
LLM_API_KEY=ollama
EOF
    echo "✅ .env файл создан."
else
    # Если файл уже есть, принудительно обновляем модель на 14b (на случай апгрейда)
    sed -i 's/LLM_MODEL=qwen2.5:7b/LLM_MODEL=qwen2.5:14b/g' .env
    echo "✅ .env файл проверен и обновлен до модели 14b."
fi

# 7. Запуск или перезапуск сервисов
echo "🐳 Запуск Docker Compose..."
sudo docker compose pull backend
sudo docker compose up -d
sudo docker image prune -f

echo "🎉 Полная настройка и деплой успешно завершены!"
