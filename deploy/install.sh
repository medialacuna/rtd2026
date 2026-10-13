#!/usr/bin/env bash
# RTD.MUAR — установка на домашний сервер (91.203.188.118)
# Требуется: Ubuntu/Debian + Docker + Compose v2
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1. Проверка Docker =="
command -v docker >/dev/null || { echo "Docker не установлен. Выполните: curl -fsSL https://get.docker.com | sh"; exit 1; }
docker compose version >/dev/null || { echo "Нет Compose v2 (пакет docker-compose-plugin)"; exit 1; }

echo "== 2. Секрет и конфиг =="
if [ ! -f .env ]; then
  KEY=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | md5sum | cut -d" " -f1)
  {
    echo "SECRET_KEY=$KEY"
    echo "# Когда поставите llama3.1 на хосте, раскомментируйте:"
    echo "# OLLAMA_URL=http://host.docker.internal:11434"
    echo "# SMTP_HOST=smtp.yourmail.ru"
    echo "# SMTP_PORT=587"
    echo "# SMTP_USER=no-reply@rtd.heartwins.ru"
    echo "# SMTP_PASSWORD=..."
  } > .env
  echo "создан .env (SECRET_KEY сгенерирован)"
fi

mkdir -p backend/data_prod
[ -f backend/data_prod/rtd.db ] || cp backend/rtd.db backend/data_prod/rtd.db

echo "== 3. Запуск контейнеров =="
docker compose up -d --build

echo "== 4. Ожидание API =="
for i in $(seq 1 30); do
  sleep 2
  if curl -sf http://localhost/api/health >/dev/null 2>&1; then break; fi
done
curl -s http://localhost/api/health && echo ""

echo ""
echo "Готово. Если DNS rtd.heartwins.ru -> 91.203.188.118 настроен,"
echo "Caddy сам выпустит Let's Encrypt сертификат при первом обращении."
echo "Проверка: curl -sI https://rtd.heartwins.ru"
echo "Логи:     docker compose logs -f"
