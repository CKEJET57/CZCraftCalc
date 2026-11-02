"""
cli/help.py — справочник команд и тем.

Используется из main.py:
    print_operations()      — общий справочник
    print_topic(name)       — тема
    print_unknown_topic(t)  — подсказка при неверной теме
"""

HEADER = "═" * 66
SECTION = "─" * 66


def _p(s: str = "") -> None:
    print(s)


# ══════════════════════════════════════════════════════════════════
#  ОБЩИЙ СПРАВОЧНИК
# ══════════════════════════════════════════════════════════════════
def print_operations() -> None:
    _p(HEADER)
    _p("  Stalcraft Crafting Calculator — справочник")
    _p(HEADER)

    # ---------- команды ----------
    _p("\n📋 КОМАНДЫ")
    _p(SECTION)
    _p("  menu                      Интерактивное меню (по умолчанию без аргументов)")
    _p("  recipe <item_id>          Анализ всех рецептов, дающих item_id")
    _p("                            Пример: main.py recipe wj2zp")
    _p("  batch                     Пакетный анализ по фильтру (bench/category/perk)")
    _p("                            Пример: main.py batch --bench workbench --category ammunition")
    _p("  exclusions <action>       Управление исключениями (нулевая стоимость)")
    _p("                            list | add <id> | remove <id> | clear")
    _p("  help [topic]              Эта справка / справка по теме")
    _p("                            Темы: examples, prices, energy, fee, recursive,")
    _p("                                  troubleshoot, exclusions, menu, all")

    # ---------- общие флаги ----------
    _p("\n⚙️  ОБЩИЕ ФЛАГИ (для recipe и batch)")
    _p(SECTION)
    _p("  --region RU|EU|…          Регион аукциона            (по умолчанию: RU)")
    _p("  --lang ru|en|es|fr|ko     Язык названий              (по умолчанию: ru)")
    _p("  --fee N                   Комиссия аукциона, %       (по умолчанию: 5.0)")
    _p("  --recursive               Считать min(рынок, крафт) для ингредиентов")
    _p("  --max-depth N             Лимит глубины рекурсии     (по умолчанию: 12)")
    _p("  --no-history              Только /lots, без /history (в 2× меньше запросов)")
    _p("  --no-fallback             Не падать на /lots, если /history пуст")
    _p("  --max-requests N          Бюджет HTTP-запросов       (по умолчанию: 500)")
    _p("  --workers N               Параллельных запросов      (по умолчанию: 4)")
    _p("  --no-heartbeat            Отключить 💓 heartbeat в stderr")
    _p("  --verbose                 Логировать каждый HTTP-запрос в stderr")
    _p("  --explain                 Показать, почему выбран рынок или крафт")
    _p("  --explain-tree            Показать базовые itemId без цены (нужен --recursive)")
    _p("  --ignore-missing          Считать приблизительно, если не хватает цен")
    _p("  --exclude 7rp7,404p       Исключить itemId (нулевая стоимость, разово)")
    _p("  --show-ids                Показывать itemId ингредиентов")

    # ---------- флаги batch ----------
    _p("\n🎯 ТОЛЬКО ДЛЯ batch")
    _p(SECTION)
    _p("  --bench workbench|laboratory_table|kitchen_table")
    _p("  --category <id>           ammunition, armor, materials, medicine, …")
    _p("  --perk <id>               ammunition, engineering, cooking, brewing, …")
    _p("  --per-category            Топ-N отдельно для каждой категории")
    _p("  --top N                   Сколько в топе (10 / с --per-category: 5)")
    _p("  --max-recipes N           Лимит рецептов (30 без --per-category,")
    _p("                            без лимита с ним). 0 = нет")
    _p("  --sort margin|profit      По чему сортировать топ      (по умолчанию: margin)")

    # ---------- темы ----------
    _p("\n📚 ПОДРОБНЕЕ")
    _p(SECTION)
    _p("  main.py help examples       Примеры запусков")
    _p("  main.py help prices         Как считаются цены")
    _p("  main.py help energy         Как учитывается энергия")
    _p("  main.py help fee            Про комиссию аукциона")
    _p("  main.py help recursive      Про рекурсивный крафт")
    _p("  main.py help troubleshoot   Что делать, если нет цен")
    _p("  main.py help exclusions     Про исключения (нулевая стоимость)")
    _p("  main.py help menu           Про интерактивное меню")
    _p("  main.py help all            Всё сразу")

    _p("\n" + HEADER)


# ══════════════════════════════════════════════════════════════════
#  ТЕМЫ
# ══════════════════════════════════════════════════════════════════
TOPICS = {
    "examples": "Примеры запусков",
    "prices": "Как считаются цены",
    "energy": "Как учитывается энергия",
    "fee": "Комиссия аукциона",
    "recursive": "Рекурсивный крафт",
    "troubleshoot": "Диагностика проблем",
    "exclusions": "Исключения (нулевая стоимость)",
    "menu": "Интерактивное меню",
}


def _topic_examples() -> None:
    _p(HEADER)
    _p("  📋 Примеры запусков")
    _p(HEADER)
    _p("""
  Интерактивное меню (по умолчанию без аргументов):
    python main.py
    python main.py menu

  Базовый анализ одного рецепта:
    python main.py recipe wj2zp

  С рекурсивным крафтом (считать min(рынок, крафт)):
    python main.py recipe wj2zp --recursive

  С полной диагностикой (почему рынок/крафт, что не нашлось):
    python main.py recipe wj2zp --recursive --explain --explain-tree

  С приблизительной оценкой (если 1–2 базы без цены):
    python main.py recipe wj2zp --recursive --ignore-missing

  Найти itemId ингредиентов (для последующего исключения):
    python main.py recipe wj2zp --recursive --show-ids

  Топ-10 самых прибыльных патронов (с рекурсией, быстрый режим):
    python main.py batch --bench workbench --category ammunition --top 10 --recursive --no-history

  Топ-5 по каждой категории (обзор всего рынка):
    python main.py batch --per-category --top 5 --recursive --no-history

  Топ-5 по каждой категории, ограничив по 15 рецептов на категорию:
    python main.py batch --per-category --top 5 --recursive --max-recipes 15

  Топ-5 медицинских рецептов по абсолютной прибыли:
    python main.py batch --bench laboratory_table --perk medicine --top 5 --recursive --sort profit

  Исключить нафармленные ресурсы (нулевая стоимость):
    python main.py recipe wj2zp --recursive --exclude 7rp7,404p

  Управление постоянными исключениями:
    python main.py exclusions add 7rp7 404p
    python main.py exclusions list
    python main.py exclusions remove 7rp7
    python main.py exclusions clear

  Только /lots (быстро, но менее точно):
    python main.py recipe wj2zp --recursive --no-history

  С логированием каждого HTTP-запроса:
    python main.py recipe wj2zp --recursive --verbose --no-heartbeat

  Отладка rate-limit (медленнее, но не падает):
    python main.py batch --bench workbench --category ammunition --recursive --workers 2 --max-requests 200
""")
    _p(HEADER)


def _topic_prices() -> None:
    _p(HEADER)
    _p("  💵 Как считаются цены")
    _p(HEADER)
    _p("""
  Для каждого itemId цена берётся в два шага:

  1) /history (по умолчанию включён)
     GET /{region}/auction/{itemId}/history?limit=200
     → массив сделок с полями price, amount
     → unit_price = price / amount       (цена за штуку)
     → sorted, отсекаем 10%% с краёв      (trimmed median)
     → медиана середины                  (устойчиво к выбросам)
     Если сделок < 5 (min_samples) → шаг 2.

  2) /lots (fallback)
     GET /{region}/auction/{itemId}/lots?limit=200&additional=true
     → минимальная цена за штуку среди активных лотов
     Если лотов нет → цена = None.

  Флаг --no-history отключает шаг 1 (только /lots, в 2× быстрее).
  Флаг --no-fallback отключает шаг 2 (только /history).

  Пример:
    --no-history --no-fallback   → цена только из /history
    --no-history                 → цена только из /lots
    (по умолчанию)               → /history, если пуст → /lots
""")
    _p(HEADER)


def _topic_energy() -> None:
    _p(HEADER)
    _p("  ⚡ Как учитывается энергия")
    _p(HEADER)
    _p("""
  Энергия рецепта пересчитывается в рубли через покупку 401j на аукционе.

  Константы (config.py):
    ENERGY_ITEM_ID = "401j"
    ENERGY_PER_ITEM = 5000

  Формула:
    energy_cost = (energy / 5000) * price(401j)

  Учитывается на КАЖДОМ уровне крафта:
    - у верхнего рецепта      (в analyze_recipe)
    - у каждого подрецепта    (в CraftCalculator._try_craft)
  Иначе resolve() выбрал бы крафт, не зная, что он жрёт энергию.

  Overproduction:
    Если крафтим 2 партии — платим 2 × energy.

  Если на 401j нет цены:
    energy_cost = None → total_cost = None
    Рецепт помечается «⚠️ нет цены на 401j», маржа не считается.

  Если 401j в исключениях (--exclude 401j):
    energy_cost = 0 → энергия «бесплатна».

  В выводе видно:
    ⚡ Энергия: 1100 (968 ₽, ≈0.22× 401j)
    ↳ крафт: 2× (выход 4), энергия 1 760 ₽   ← энергия подрецепта
""")
    _p(HEADER)


def _topic_fee() -> None:
    _p(HEADER)
    _p("  💸 Комиссия аукциона")
    _p(HEADER)
    _p("""
  Комиссия снимается ТОЛЬКО при продаже результата
  (не с покупки ингредиентов).

  Формула:
    revenue_gross = price(результат) × result_amount
    fee_amount    = revenue_gross × fee_pct / 100
    revenue_net   = revenue_gross − fee_amount

  По умолчанию fee_pct = 5 (5%%). Меняется флагом --fee:
    --fee 0        без комиссии (например, для самопроверки)
    --fee 10       комиссия 10%%
    --fee 3.5      дробные проценты тоже работают

  В выводе:
    💵 Выручка брутто:  18 000 ₽
    💸 Комиссия (5.0%): -900 ₽
    💵 Выручка нетто:   17 100 ₽

  Если в игре покупатель тоже платит комиссию — это НЕ учтено.
  Тогда правь формулу в services/craft.py (analyze_recipe).
""")
    _p(HEADER)


def _topic_recursive() -> None:
    _p(HEADER)
    _p("  🔁 Рекурсивный крафт (--recursive)")
    _p(HEADER)
    _p("""
  Без --recursive:  каждый ингредиент покупается на рынке по его цене.
  С --recursive:    для каждого ингредиента выбирается min(рынок, крафт).

  Алгоритм (CraftCalculator.resolve):
    1) если item в исключениях → cost=0, source="excluded", выход
    2) market_cost = цена_рынка × amount
    3) craft_cost  = лучший рецепт из всех с result=item:
       - runs = ceil(amount / recipe.result.amount)
       - energy_cost = (recipe.energy × runs / 5000) × price(401j)
       - ingredients_cost = Σ resolve(ing, amount × runs)
       - total = ingredients_cost + energy_cost
    4) выбираем min(market_cost, craft_cost)
       при равенстве — рынок (проще, чем крафтить)

  Защита от циклов:
    path: frozenset[str] — если item уже в цепочке, крафт запрещён,
    fallback на рынок. Плюс --max-depth (12 по умолчанию).

  Мемоизация:
    (item_id, amount) → CostResult. Второй вызов той же пары мгновенный.

  В выводе:
    1r246  Хорог  ×4  [крафт]  × 3 370 ₽ = 13 479 ₽
      ↳ крафт: 2× (выход 4), энергия 1 760 ₽
        Фасолевый суп  ×2  [рынок]  × 2 000 ₽ = 4 000 ₽
""")
    _p(HEADER)


def _topic_troubleshoot() -> None:
    _p(HEADER)
    _p("  🩺 Диагностика проблем")
    _p(HEADER)
    _p("""
  ▸ «Прибыль: — (—)» и «Нет цен на N ингредиентов»
    Один или несколько ингредиентов не имеют ни истории, ни лотов.
    Шаги:
      1) main.py recipe <itemId> --recursive --explain-tree
         → покажет, какие базовые itemId без цены
      2) если это фармящееся сырьё (не торгуется) — используй --ignore-missing
         для нижней оценки прибыли или exclusions add <id> (если у вас есть)
      3) если это обычный предмет — попробуй --no-history (иногда /lots богаче)

  ▸ Долго висит / кажется, что зависло
    Heartbeat в stderr каждые 5 сек:
      💓 alive 12.3s | requests 47/500 | cache 47 | idle 0.3s | last: gq3k/history
    Если idle растёт — запрос висит на timeout (20 с). Ctrl+C безопасен.
    Флаги для ускорения:
      --no-history     (в 2× меньше запросов)
      --workers 8      (если API не против; следи за 429)
      --max-requests 200  (жёсткий лимит, чтобы не уйти в минуты)

  ▸ 429 Too Many Requests
    API Stalcraft не публикует rate-limit. Безопасно ~5 req/s.
    Снизить нагрузку:
      --workers 2 --max-requests 200 --no-history

  ▸ Ошибка 401 Unauthorized
    Токен протух (client_credentials живёт ~1 час).
    Просто перезапусти команду — новый токен будет получен автоматически.

  ▸ Ctrl+C во время prefetch
    Безопасно. Прогресс не сохраняется между запусками (кэш в памяти).

  ▸ Batch-анализ долгий
    С --recursive каждый рецепт может обходить 50–100 itemId.
    Уменьши количество рецептов:
      --max-recipes 10

  ▸ «Прибыль: — (—)» после exclusions add
    Скорее всего исключённый предмет не участвует ни в одном рецепте —
    или вы перепутали itemId. Проверь `main.py exclusions list`.
""")
    _p(HEADER)


def _topic_exclusions() -> None:
    _p(HEADER)
    _p("  🎁 Исключения (нулевая стоимость)")
    _p(HEADER)
    _p("""
  Если ингредиент у вас в запасе (нафармлен, лежит на складе) —
  его можно "исключить": калькулятор будет считать его нулевой
  стоимостью и не будет искать цену на аукционе или рецепт.

  Хранение: database/exclusions.json (сохраняется между запусками)

  Команды:
    main.py exclusions list              — показать исключения
    main.py exclusions add 7rp7 404p     — добавить (можно много)
    main.py exclusions remove 7rp7       — удалить
    main.py exclusions clear             — очистить всё

  Разово (только этот запуск):
    main.py recipe wj2zp --recursive --exclude 7rp7,404p

  Найти itemId ингредиентов:
    main.py recipe wj2zp --show-ids

  Или через интерактивное меню:
    main.py menu → 🎁 Управление исключениями

  В выводе:
    - исключённые ингредиенты помечаются [ноль];
    - внизу блок:
        🎁 Учтено как ноль (2 вид., 7 ед.):
           Чеснок                × 6
           Термическая смесь     × 1

  Работает и без --recursive (исключения проверяются напрямую).
  С --recursive исключённый ингредиент не ищется на аукционе
  и не крафтится — сразу нулевая стоимость.

  Вложенные исключения:
    Если исключить промежуточный предмет (например, zz1o2),
    то во всех рецептах, где он встречается глубоко в дереве,
    он тоже будет нулевой.

  Энергия:
    --exclude 401j → energy_cost = 0, энергия «бесплатна».

  Пример:
    У вас 20 чеснока → добавьте 7rp7 в исключения →
    себестоимость снизится на 20×560 = 11 200 ₽.

  ⚠️  Осторожно:
    Исключение не проверяет, действительно ли у вас есть предмет
    в нужном количестве. Если нужно 100, а у вас 20 — калькулятор
    посчитает все 100 нулевыми. Ведите учёт вручную.
""")
    _p(HEADER)


def _topic_menu() -> None:
    _p(HEADER)
    _p("  🖥️  Интерактивное меню")
    _p(HEADER)
    _p("""
  Запуск:
    python main.py              (без аргументов — сразу меню)
    python main.py menu         (явно)

  Главное меню:
    1. 🧮 Посчитать крафт предмета
         Категория → Предмет → Опции → Анализ

         В списке предметов:
           A — сортировка по алфавиту
           L — разбиение по уровням крафта (1–5),
               с заголовками групп
           F — поиск по названию
           R — сбросить фильтр (если он активен)

         В опциях анализа:
           - recursive (min рынок/крафт)
           - показать itemId
           - explain / explain-tree
           - no-history (быстрее)
           - комиссия / регион
           - исключения для этого рецепта
           - запустить анализ

    2. 🏆 Топ по категориям
         per-category on/off, Top-N, recursive, no-history
    3. 🎁 Управление исключениями
         показать / добавить по id / удалить / очистить
    4. 📖 Справка

  Уровень крафта:
    Для каждого рецепта берётся max(requirements.perks.values()).
    Для предмета с несколькими рецептами показывается МИНИМАЛЬНЫЙ
    уровень — тот, на котором его проще всего скрафтить.

  Навигация:
    Категории → Список предметов → Опции → Анализ
    0 в опциях        → назад к списку предметов
    0 в списке        → назад к категориям
    0 в категориях    → в главное меню

  Особенности:
    - кэш цен живёт между выборами (второй предмет того же
      поддерева считается мгновенно)
    - при изменении exclusions или региона CraftCalculator
      пересоздаётся автоматически
    - в меню heartbeat отключён (чтобы не мешать input())

  Выход: выбор 5 в главном меню, 'q' или Ctrl+C.
""")
    _p(HEADER)


# ══════════════════════════════════════════════════════════════════
#  ДИСПЕТЧЕР
# ══════════════════════════════════════════════════════════════════
_DISPATCH = {
    "examples": _topic_examples,
    "prices": _topic_prices,
    "energy": _topic_energy,
    "fee": _topic_fee,
    "recursive": _topic_recursive,
    "troubleshoot": _topic_troubleshoot,
    "exclusions": _topic_exclusions,
    "menu": _topic_menu,
}


def print_topic(topic: str) -> bool:
    """Печатает тему. Возвращает False, если тема неизвестна."""
    topic = topic.strip().lower()
    if topic == "all":
        for fn in _DISPATCH.values():
            fn()
        return True
    fn = _DISPATCH.get(topic)
    if fn is None:
        return False
    fn()
    return True


def print_unknown_topic(topic: str) -> None:
    _p(f"\n❌ Неизвестная тема: «{topic}»")
    _p("Доступные темы:")
    for key, desc in TOPICS.items():
        _p(f"  {key:14s} — {desc}")
    _p("  all            — всё сразу\n")