# Публикация почасовых агрегатов сделок

Публикатор — отдельный одноразовый процесс. Он читает `database/history/deals/*.jsonl`, не изменяет исходные файлы и не читает/не публикует `snapshots`.

## Формат

Завершённые часы агрегируются в часовом поясе `STALCRAFT_TIMEZONE` (по умолчанию `Europe/Moscow`). Текущий незавершённый час не публикуется. Для каждого предмета формируется запись с полями:

- `item`, `hour`, `schema_version`;
- `deals` — число сделок;
- `amount` — суммарное количество;
- `turnover` — сумма полей `price` исходных сделок;
- `min_unit`, `max_unit`, `avg_unit` — средневзвешенная цена (`turnover / amount`), `median_unit`.

Файлы в ветке `market-data`: `deals/YYYY/MM/DD/HH.jsonl`. Один файл содержит по одной агрегированной записи на предмет за час. Повторная публикация обновляет тот же путь, а не добавляет дубликаты.

## Переменные .env

Создайте fine-grained GitHub token с доступом **Contents: Read and write** только к `CKEJET57/CZCraftCalc`, затем задайте:

```dotenv
GITHUB_TOKEN=github_pat_...
GITHUB_REPOSITORY=CKEJET57/CZCraftCalc
GITHUB_DATA_BRANCH=market-data
GITHUB_BASE_BRANCH=feature/monorepo
```

Токен не добавляйте в Git и не передавайте в командной строке. Публикатор создаёт `market-data` от `feature/monorepo`, если ветка ещё не существует.

## Ручной запуск

Из корня проекта:

```bash
docker compose run --rm publisher
```

Предварительный просмотр без отправки в GitHub:

```bash
docker compose run --rm publisher --dry-run
```

## Автоматический запуск на Orange Pi

Установите unit-файлы из `deployment/systemd/` в `/etc/systemd/system/`, затем выполните:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now czcraftcalc-publisher.timer
systemctl list-timers czcraftcalc-publisher.timer
```

Таймер запускает публикацию каждый час в `:05` по `Europe/Moscow`. `Persistent=true` позволяет выполнить пропущенный запуск после включения устройства.

Проверка последнего запуска:

```bash
sudo systemctl status czcraftcalc-publisher.service
sudo journalctl -u czcraftcalc-publisher.service -n 100 --no-pager
```

## Локальное состояние и сохранность исходных данных

- Исходные `database/history/deals/` и `database/history/snapshots/` публикатор не переписывает, не перемещает и не удаляет.
- `database/publish/queue/` содержит локальные подготовленные агрегаты; успешно опубликованные файлы старше 30 дней удаляются.
- `database/publish/state.json` хранит контрольные хеши публикаций, а не исходные сделки.
- Если GitHub недоступен, очередь сохраняется и будет повторно отправлена при следующем запуске. Непубликованная очередь не удаляется автоматически, даже если ей больше 30 дней: это предотвращает потерю данных при длительном сбое. В таком случае она временно превышает обычный 30-дневный срок хранения.
- Ветка Git хранит агрегаты бессрочно.

Публикатор читает только сделки, использует время самой сделки `time`, а не `collected_at`. Ошибки публикации не останавливают контейнер collector.
