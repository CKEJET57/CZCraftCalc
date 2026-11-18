# CZWebInterfase

Веб-интерфейс STALCRAFT Crafting Calculator: React 18, TypeScript и Vite.

## Вариант 1. Orange Pi (backend уже работает)

Этот вариант запускает только frontend. Он **не пересоздаёт backend и collector**, не меняет их Compose и не трогает каталог `database`.

Требования:
- Docker Engine 20.10+ и Docker Compose plugin;
- backend API уже запущен на Orange Pi и опубликован на порту `8000`;
- Orange Pi и устройство с браузером находятся в доступной друг другу сети.

Из каталога репозитория frontend:

```bash
docker compose up -d --build
```

Откройте в браузере:

```text
http://IP_ORANGE_PI:8080
```

По умолчанию Nginx внутри frontend-контейнера проксирует `/api/*` на уже работающий backend через `host.docker.internal:8000`. В Compose для Linux добавлен host-gateway alias.

Полезные команды:

```bash
docker compose ps
docker compose logs -f --tail=100 frontend
docker compose down
```

Чтобы использовать другой порт на хосте:

```bash
WEB_PORT=8081 docker compose up -d --build
```

Тогда интерфейс будет доступен на `http://IP_ORANGE_PI:8081`.

Обновление frontend:

```bash
git pull --ff-only origin main
docker compose up -d --build
```

Важно: не запускайте здесь `docker compose down` из каталога backend и не пересобирайте backend ради обновления интерфейса. Это отдельный Compose-проект.

## Вариант 2. GitHub Codespaces

В Codespace откройте терминал в корне репозитория `CZCraftCalc` (ветка `feature/web-api`) и клонируйте frontend внутрь него:

```bash
git clone -b main https://github.com/CKEJET57/CZWebInterfase.git frontend
```

Убедитесь, что в корне backend есть файл `.env` с актуальным `STALCRAFT_CLIENT_SECRET`. Если файла нет, создайте его из `.env.example` и заполните секрет.

Запуск backend API и frontend одной командой:

```bash
bash scripts/codespace.sh up
```

Скрипт:
- создаёт Python venv и устанавливает backend-зависимости;
- устанавливает frontend-зависимости через `npm ci`;
- запускает только API и Vite, **не запускает collector**;
- использует same-origin путь `/api`, а Vite проксирует его на backend в том же Codespace;
- сохраняет логи и PID-файлы в `.run/`.

В панели **Ports** откройте порт `5173` — это веб-интерфейс. Порт `8000` нужен API и может оставаться Private.

Управление:

```bash
bash scripts/codespace.sh status
bash scripts/codespace.sh logs
bash scripts/codespace.sh down
```

Если frontend уже клонирован в каталог `CZWebInterfase`, скрипт также распознает это имя. Можно указать другой путь через `FRONTEND_DIR=/path/to/frontend`.

## Локальная разработка

Backend должен отвечать на `http://127.0.0.1:8000`.

```bash
npm ci
npm run dev
```

Vite доступен на `http://localhost:5173` и проксирует запросы `/api` к backend.

Проверка и production-сборка:

```bash
npm run typecheck
npm run build
```
