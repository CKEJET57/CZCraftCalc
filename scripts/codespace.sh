#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
RUN_DIR="$ROOT/.run"
API_PID="$RUN_DIR/api.pid"
WEB_PID="$RUN_DIR/frontend.pid"
FRONTEND_DIR="${FRONTEND_DIR:-$ROOT/frontend}"

if [[ ! -f "$FRONTEND_DIR/package.json" && -f "$ROOT/CZWebInterfase/package.json" ]]; then
  FRONTEND_DIR="$ROOT/CZWebInterfase"
fi

mkdir -p "$RUN_DIR"

usage() {
  cat <<'EOF'
Использование:
  bash scripts/codespace.sh up      установить зависимости и запустить API + frontend
  bash scripts/codespace.sh down    остановить запущенные этим скриптом процессы
  bash scripts/codespace.sh status  проверить доступность API и frontend
  bash scripts/codespace.sh logs    смотреть общие логи
EOF
}

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

stop_group() {
  local pid_file="$1"
  if is_running "$pid_file"; then
    local pid
    pid="$(cat "$pid_file")"
    kill -TERM "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

wait_http() {
  local url="$1"
  local label="$2"
  for _ in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "✓ $label доступен: $url"
      return 0
    fi
    sleep 1
  done
  echo "Ошибка запуска $label. Последние строки лога:"
  return 1
}

start() {
  if [[ ! -f "$ROOT/.env" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "Создан .env. Заполните STALCRAFT_CLIENT_SECRET и повторите команду."
    exit 1
  fi
  if ! grep -Eq '^STALCRAFT_CLIENT_SECRET=.+
  if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
    echo "Не найден frontend. Из корня CZCraftCalc выполните:"
    echo "  git clone -b main https://github.com/CKEJET57/CZWebInterfase.git frontend"
    exit 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "Для проверки запуска нужен curl."
    exit 1
  fi
  if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
  fi
  "$VENV/bin/python" -m pip install --upgrade pip
  "$VENV/bin/python" -m pip install -r "$ROOT/requirements.txt"

  if ! curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    if is_running "$API_PID"; then
      echo "API PID записан, но health endpoint не отвечает. Проверьте .run/api.log."
      exit 1
    fi
    nohup "$VENV/bin/python" "$ROOT/server.py" >"$RUN_DIR/api.log" 2>&1 < /dev/null &
    echo "$!" > "$API_PID"
    if ! wait_http http://127.0.0.1:8000/api/health "Backend API"; then
      tail -n 80 "$RUN_DIR/api.log" || true
      exit 1
    fi
  else
    echo "✓ Backend API уже запущен на порту 8000 — повторно не запускаю."
  fi

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    (cd "$FRONTEND_DIR" && npm ci)
  fi

  if ! curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1; then
    if is_running "$WEB_PID"; then
      echo "Frontend PID записан, но порт 5173 не отвечает. Проверьте .run/frontend.log."
      exit 1
    fi
    nohup bash -c 'cd "$1" && exec env VITE_API_URL=/api npm run dev -- --host 0.0.0.0' _ "$FRONTEND_DIR" >"$RUN_DIR/frontend.log" 2>&1 < /dev/null &
    echo "$!" > "$WEB_PID"
    if ! wait_http http://127.0.0.1:5173/ "Frontend"; then
      tail -n 80 "$RUN_DIR/frontend.log" || true
      exit 1
    fi
  else
    echo "✓ Frontend уже отвечает на порту 5173 — повторно не запускаю."
  fi

  echo
  echo "Готово. Откройте порт 5173 в панели Ports вашего Codespace."
  echo "API: http://127.0.0.1:8000/api/health"
  echo "Логи: bash scripts/codespace.sh logs"
  echo "Остановка: bash scripts/codespace.sh down"
}

case "${1:-}" in
  up) start ;;
  down)
    stop_group "$WEB_PID"
    stop_group "$API_PID"
    echo "Процессы остановлены."
    ;;
  status)
    curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 && echo "API: работает" || echo "API: не отвечает"
    curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1 && echo "Frontend: работает" || echo "Frontend: не отвечает"
    ;;
  logs)
    touch "$RUN_DIR/api.log" "$RUN_DIR/frontend.log"
    tail -n 100 -f "$RUN_DIR/api.log" "$RUN_DIR/frontend.log"
    ;;
  *) usage; exit 2 ;;
esac
 "$ROOT/.env" ||
     grep -Eq '^STALCRAFT_CLIENT_SECRET=(replace_with_your_client_secret|your_client_secret)
  if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
    echo "Не найден frontend. Из корня CZCraftCalc выполните:"
    echo "  git clone -b main https://github.com/CKEJET57/CZWebInterfase.git frontend"
    exit 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "Для проверки запуска нужен curl."
    exit 1
  fi
  if ! command -v setsid >/dev/null 2>&1; then
    echo "Для управления фоновыми процессами нужна команда setsid."
    exit 1
  fi

  if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
  fi
  "$VENV/bin/python" -m pip install --upgrade pip
  "$VENV/bin/python" -m pip install -r "$ROOT/requirements.txt"

  if ! curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    if is_running "$API_PID"; then
      echo "API PID записан, но health endpoint не отвечает. Проверьте .run/api.log."
      exit 1
    fi
    setsid "$VENV/bin/python" "$ROOT/server.py" >"$RUN_DIR/api.log" 2>&1 < /dev/null &
    echo "$!" > "$API_PID"
    if ! wait_http http://127.0.0.1:8000/api/health "Backend API"; then
      tail -n 80 "$RUN_DIR/api.log" || true
      exit 1
    fi
  else
    echo "✓ Backend API уже запущен на порту 8000 — повторно не запускаю."
  fi

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    (cd "$FRONTEND_DIR" && npm ci)
  fi

  if ! curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1; then
    if is_running "$WEB_PID"; then
      echo "Frontend PID записан, но порт 5173 не отвечает. Проверьте .run/frontend.log."
      exit 1
    fi
    (cd "$FRONTEND_DIR" && setsid env VITE_API_URL=/api npm run dev -- --host 0.0.0.0) >"$RUN_DIR/frontend.log" 2>&1 < /dev/null &
    echo "$!" > "$WEB_PID"
    if ! wait_http http://127.0.0.1:5173/ "Frontend"; then
      tail -n 80 "$RUN_DIR/frontend.log" || true
      exit 1
    fi
  else
    echo "✓ Frontend уже отвечает на порту 5173 — повторно не запускаю."
  fi

  echo
  echo "Готово. Откройте порт 5173 в панели Ports вашего Codespace."
  echo "API: http://127.0.0.1:8000/api/health"
  echo "Логи: bash scripts/codespace.sh logs"
  echo "Остановка: bash scripts/codespace.sh down"
}

case "${1:-}" in
  up) start ;;
  down)
    stop_group "$WEB_PID"
    stop_group "$API_PID"
    echo "Процессы остановлены."
    ;;
  status)
    curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 && echo "API: работает" || echo "API: не отвечает"
    curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1 && echo "Frontend: работает" || echo "Frontend: не отвечает"
    ;;
  logs)
    touch "$RUN_DIR/api.log" "$RUN_DIR/frontend.log"
    tail -n 100 -f "$RUN_DIR/api.log" "$RUN_DIR/frontend.log"
    ;;
  *) usage; exit 2 ;;
esac
 "$ROOT/.env"; then
    echo "В .env не задан настоящий STALCRAFT_CLIENT_SECRET."
    exit 1
  fi
  if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
    echo "Не найден frontend. Из корня CZCraftCalc выполните:"
    echo "  git clone -b main https://github.com/CKEJET57/CZWebInterfase.git frontend"
    exit 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "Для проверки запуска нужен curl."
    exit 1
  fi
  if ! command -v setsid >/dev/null 2>&1; then
    echo "Для управления фоновыми процессами нужна команда setsid."
    exit 1
  fi

  if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
  fi
  "$VENV/bin/python" -m pip install --upgrade pip
  "$VENV/bin/python" -m pip install -r "$ROOT/requirements.txt"

  if ! curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    if is_running "$API_PID"; then
      echo "API PID записан, но health endpoint не отвечает. Проверьте .run/api.log."
      exit 1
    fi
    setsid "$VENV/bin/python" "$ROOT/server.py" >"$RUN_DIR/api.log" 2>&1 < /dev/null &
    echo "$!" > "$API_PID"
    if ! wait_http http://127.0.0.1:8000/api/health "Backend API"; then
      tail -n 80 "$RUN_DIR/api.log" || true
      exit 1
    fi
  else
    echo "✓ Backend API уже запущен на порту 8000 — повторно не запускаю."
  fi

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    (cd "$FRONTEND_DIR" && npm ci)
  fi

  if ! curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1; then
    if is_running "$WEB_PID"; then
      echo "Frontend PID записан, но порт 5173 не отвечает. Проверьте .run/frontend.log."
      exit 1
    fi
    (cd "$FRONTEND_DIR" && setsid env VITE_API_URL=/api npm run dev -- --host 0.0.0.0) >"$RUN_DIR/frontend.log" 2>&1 < /dev/null &
    echo "$!" > "$WEB_PID"
    if ! wait_http http://127.0.0.1:5173/ "Frontend"; then
      tail -n 80 "$RUN_DIR/frontend.log" || true
      exit 1
    fi
  else
    echo "✓ Frontend уже отвечает на порту 5173 — повторно не запускаю."
  fi

  echo
  echo "Готово. Откройте порт 5173 в панели Ports вашего Codespace."
  echo "API: http://127.0.0.1:8000/api/health"
  echo "Логи: bash scripts/codespace.sh logs"
  echo "Остановка: bash scripts/codespace.sh down"
}

case "${1:-}" in
  up) start ;;
  down)
    stop_group "$WEB_PID"
    stop_group "$API_PID"
    echo "Процессы остановлены."
    ;;
  status)
    curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 && echo "API: работает" || echo "API: не отвечает"
    curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1 && echo "Frontend: работает" || echo "Frontend: не отвечает"
    ;;
  logs)
    touch "$RUN_DIR/api.log" "$RUN_DIR/frontend.log"
    tail -n 100 -f "$RUN_DIR/api.log" "$RUN_DIR/frontend.log"
    ;;
  *) usage; exit 2 ;;
esac
