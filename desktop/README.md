# Desktop-прототип CZCraftCalc

Это технический прототип связки **Tauri 2 + существующий React frontend + Python backend через IPC**.

В desktop-версии через IPC подключены поиск персонажа, список предметов, категории, карточка предмета и её варианты, расчёт рецепта, пакетный анализ, история сделок и рыночная аналитика. FastAPI, HTTP API и localhost для обмена между frontend и Python не запускаются.

Frontend подключён как Git submodule из `CKEJET57/CZWebInterfase`, ветка `feature/desktop-prototype`.

## Что потребуется

- Windows 10/11 x64;
- Rust stable и Cargo;
- Tauri CLI 2;
- Node.js LTS и npm;
- Python 3.10+;
- установленный WebView2 Runtime (обычно уже есть в Windows 11).

## Получение исходников

Из корня репозитория:

```powershell
git submodule update --init --remote --recursive
```

Установить frontend-зависимости:

```powershell
cd desktop/frontend
npm ci
cd ../..
```

Создать виртуальное окружение Python в корне backend:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Создать корневой `.env` из `.env.example` и заполнить `STALCRAFT_CLIENT_SECRET`.

Указать интерпретатор Python для Tauri:

```powershell
$env:CZCRAFTCALC_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
```

Установить Tauri CLI (один раз):

```powershell
cargo install tauri-cli --version "^2"
```

Запустить приложение из каталога `desktop`:

```powershell
cd desktop
cargo tauri dev
```

## Как устроен обмен

1. React вызывает глобальный Tauri API `window.__TAURI__.core.invoke`.
2. Rust-команда запускает `desktop/python/bridge.py`.
3. Команда передаётся Python через stdin одной JSON-строкой.
4. Python вызывает существующие `api.auth.fetch_token` и `api.characters.fetch_character_profile`.
5. Результат возвращается одной JSON-строкой через stdout.

Каждый вызов запускает отдельный короткоживущий Python-процесс. Это сделано намеренно для первого прототипа: так проще проверить архитектуру и изоляцию ошибок. Для полноценной версии можно перейти на постоянно работающий процесс с двусторонним IPC.

## Ограничения прототипа

- Страницы используют существующие обработчики `server.routes` напрямую. Это сохраняет бизнес-логику веб-версии и не поднимает HTTP-сервер.
- Иконки предметов передаются в UI как data URI; сами файлы остаются в локальной базе данных.
- Справочник `stats.json` читается из `database/stats.json`; если файла нет, мост скачивает только этот файл из официального репозитория игровых данных.
- Справочник `stats.json` читается из `database/stats.json`; если файла нет, мост скачивает только этот файл из официального репозитория игровых данных.
- Для поиска персонажа требуется OAuth client secret из локального корневого `.env`.
- Секрет нельзя встраивать в публичный desktop-бинарник: извлечь его из приложения технически возможно. До распространения приложения нужно решить модель OAuth — например, отдельный backend-брокер или собственные учётные данные пользователя, если это допускает EXBO.
- Это dev-прототип, а не готовый установщик. Упаковка Python runtime, подпись и безопасное хранение пользовательских настроек пока не реализованы.

## Диагностика

Если Python не найден, задайте `CZCRAFTCALC_PYTHON` на полный путь к `python.exe`.

Если поиск сообщает об ошибке OAuth, проверьте `.env` в корне CZCraftCalc. Не публикуйте этот файл и не отправляйте его содержимое в логах.
