# RTD.MUAR — архив для домашнего сервера 91.203.188.118

## Быстрый старт (3 команды на сервере)
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin curl   # если docker ещё нет
tar xzf rtd-muar.tar.gz && cd rtd-muar
sudo bash deploy/install.sh
```
Открой https://rtd.heartwins.ru (DNS A-запись `rtd` → 91.203.188.118 должен быть уже прописан).

## Что внутри
- `backend/` FastAPI: регистрация по email (magic link), реплики, муар-алгоритм, RAG, Stage Mode
- `backend/data_prod/rtd.db` — **готовая база**: 18 пьес «Комарово» усвоены ИИ, maturity_score 57.6
- `frontend/dist/` — собранная статика (Vite build): элитная адаптивная верстка, RU/EN, PWA
- `data/komarovo/` — тексты пьес; `data/*.md` — Лестница/Генезис/Муар/Теории
- `deploy/Caddyfile` — HTTPS Let's Encrypt автоматически + прокси /api и /ws на backend
- `docker-compose.yml` — backend + Caddy + Redis + mock-Ollama (Llama-совместимый без GPU)

## Порты на роутере (home server за NAT)
Пробросить на машину с Docker: **TCP 80** и **TCP 443**.

## Настоящая Llama (по желанию)
На хосте: `curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3.1:8b`.
Затем в `.env`: `OLLAMA_URL=http://host.docker.internal:11434`, удалить сервис `mock-ollama`
из docker-compose.yml (или оставить как fallback) и `docker compose up -d`.

## Email для magic-ссылок
Без SMTP ссылка возвращается в ответе API (dev-режим, страница /join покажет её сама).
Для боевой почты — раскомментируй SMTP_* в `.env` (любой SMTP, например Yandex/Mail.ru).

## Обновление
Заменить файлы из нового архива поверх старой папки и выполнить `docker compose up -d --build`.
База (`backend/data_prod/rtd.db`) сохраняется между запусками — сделай её копию перед обновлением.
