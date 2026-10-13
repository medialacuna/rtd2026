# RTD.MUAR — деплой на rtd.heartwins.ru

## Архитектура (один VPS, всё за одним nginx)
```
rtd.heartwins.ru :443/:80  →  nginx
   ├── /            → frontend/dist (статика, SPA-fallback)
   ├── /api/        → uvicorn 127.0.0.1:8000
   └── /ws          → uvicorn (WebSocket, upgrade)
ollama :11434 (локально, не наружу)
redis :6379 (локально), postgres (локально)
```

## DNS (прописать у регистратора heartwins.ru)
| Тип | Имя | Значение |
|-----|-----|----------|
| A   | rtd | IP твоего VPS |
| AAAA| rtd | IPv6 VPS (если есть) |

Проверка: `dig +short rtd.heartwins.ru` должен вернуть IP сервера.

## Если хостинг сейчас GitHub Pages — нет
GitHub Pages отдаёт только статику: регистрация по email, БД, WebSocket и Llama там работать НЕ будут.
Варианты:
- **VPS в РФ** (Timeweb/Selectel/MTS Cloud, от ~500₽/мес) — рекомендуемый, весь стек один сервер;
- Render/Fly.io для backend + Vercel для фронта — но Ollama там не запустить бесплатно с GPU.

## Установка на VPS (Ubuntu 22.04/24.04)
```bash
sudo apt update && sudo apt install -y git nginx python3.11-venv certbot python3-certbot-nginx
git clone <репозиторий> ~/rtd && cd ~/rtd

# Backend
python3 -m venv ~/.venvs/rtd && source ~/.venvs/rtd/bin/activate
pip install -r backend/requirements.txt
cd backend && cp .env.example .env   # заполнить SECRET_KEY, DATABASE_URL, SMTP_*
uvicorn app.main:app --host 127.0.0.1 --port 8000   # systemd unit ниже

# Frontend
cd ../frontend && npm ci && npm run build           # → frontend/dist

# Ollama + Llama (модель ~5 ГБ, нужна RAM ≥16 ГБ или GPU)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b-instruct-q5_K_M
```

## systemd (`/etc/systemd/system/rtd-backend.service`)
```ini
[Unit]
Description=RTD.MUAR backend
After=network.target postgresql.service redis-server.service
[Service]
WorkingDirectory=/home/YOU/rtd/backend
ExecStart=/home/YOU/.venvs/rtd/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
Restart=always
EnvironmentFile=/home/YOU/rtd/backend/.env
[Install]
WantedBy=multi-user.target
```

## nginx (`/etc/nginx/sites-available/rtd.heartwins.ru`) — файл в репо: deploy/nginx.conf
После `ln -s`, `nginx -t && systemctl reload nginx`:
```bash
sudo certbot --nginx -d rtd.heartwins.ru   # HTTPS автоматически
```

## .env (backend) — ключевые переменные
```
SECRET_KEY=<openssl rand -hex 32>
DATABASE_URL=postgresql+asyncpg://rtd:PASS@localhost:5432/rtd
REDIS_URL=redis://localhost:6379/0
BASE_URL=https://rtd.heartwins.ru
OLLAMA_URL=http://localhost:11434
SMTP_HOST=smtp.timeweb.ru   # или Resend API relay
SMTP_USER=no-reply@rtd.heartwins.ru
SMTP_PASSWORD=...
```
Без SMTP magic-ссылки печатаются в лог и возвращаются в API (dev-режим). Для прода обязательно настроить SMTP — письма участникам.

## Проверка готовности
```bash
curl https://rtd.heartwins.ru/api/health
# {"ok":true,"ollama":true,...}
```
