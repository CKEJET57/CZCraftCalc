"""
cli/menu.py — интерактивное меню.
Вся логика анализа — в core/runner.py.
"""

import os
import sys

from api.auth import fetch_token
from cli.help import print_operations
from core.context import AnalysisContext
from core.options import AnalysisOptions
from core.runner import run_batch, run_recipe
from services.craft import CraftCalculator
from services.price import PriceService, phase
from storage.exclusions import (
    add_exclusions, clear_exclusions, load_exclusions, remove_exclusions,
)
from storage.hideout import (
    extract_category_id, find_recipes_by_result, load_hideout_recipes,
)
from storage.listing import build_item_index, get_item_name, load_listing


# ──────────────────────────────────────────────────────────────────
#  Утилиты
# ──────────────────────────────────────────────────────────────────
def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _pause() -> None:
    _ask("\n  ↵ Enter для продолжения...")


# ──────────────────────────────────────────────────────────────────
#  Сессия меню
# ──────────────────────────────────────────────────────────────────
class MenuSession:
    def __init__(self) -> None:
        self._item_index: dict | None = None
        self._hideout: dict | None = None
        self._price_service: PriceService | None = None
        self._region: str | None = None
        self._craft_calc: CraftCalculator | None = None
        self._excl_snapshot: frozenset[str] = frozenset()
        self._data_loaded = False
        self.opts = AnalysisOptions.menu_defaults()

    # ────────── ленивая инициализация ──────────
    def _ensure_data(self) -> None:
        if self._data_loaded:
            return
        with phase("Загрузка listing + рецептов"):
            listing = load_listing()
            self._item_index = build_item_index(listing)
            self._hideout = load_hideout_recipes()
        self._data_loaded = True

    def _ensure_price(self) -> None:
        self._ensure_data()
        if self._price_service is None or self._region != self.opts.region:
            with phase("OAuth: токен"):
                token = fetch_token()["access_token"]
            self._price_service = PriceService(
                token,
                region=self.opts.region,
                use_history=not self.opts.no_history,
                max_requests=self.opts.max_requests,
                heartbeat=False,
                verbose=False,
            )
            self._region = self.opts.region
            self._craft_calc = None
            self._excl_snapshot = frozenset()
    def _menu_character(self) -> None:
        _clear()
        name = _ask("Ник персонажа: ").strip()
        if not name:
            return
        region = _ask(f"Регион [{self.opts.region}]: ").strip().upper()
        if region:
            self.opts.region = region

        ctx = self._context()
        from core.runner import run_character
        try:
            run_character(name, self.opts, ctx)
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {e}")
        _pause()

    def _menu_history(self) -> None:
        """Выбор категории → предмета → опции истории → вывод."""
        self._ensure_data()
        groups, cat_names, order = self._group_recipes()

        while True:  # категории
            _clear()
            print("── Категории (история покупок) ──\n")
            for i, cid in enumerate(order, 1):
                print(f"  {i:2d}. {cat_names[cid]}  ({len(groups[cid])})")
            print("   0. ← Назад")
            choice = _ask("\nВыбор: ")
            if choice in ("", "0"):
                return
            try:
                cid = order[int(choice) - 1]
            except (ValueError, IndexError):
                _pause()
                continue

            # уникальные предметы категории
            seen: dict[str, dict] = {}
            for r in groups[cid]:
                rid = r["result"][0]["item"]
                seen.setdefault(rid, r)
            items = sorted(seen.values(),
                           key=lambda r: get_item_name(
                               self._item_index, r["result"][0]["item"],
                               self.opts.lang))

            while True:  # предметы
                _clear()
                print(f"── {cat_names[cid]} — история покупок ──\n")
                for i, r in enumerate(items, 1):
                    name = get_item_name(self._item_index,
                                        r["result"][0]["item"], self.opts.lang)
                    print(f"  {i:3d}. {name}")
                print("\n    F. 🔍 Поиск по названию")
                print("    0. ← К категориям")
                choice = _ask("\nВыбор: ").strip()
                if choice in ("", "0"):
                    break
                if choice.upper() == "F":
                    q = _ask("Подстрока: ").lower()
                    if q:
                        filtered = [
                            r for r in items
                            if q in get_item_name(
                                self._item_index, r["result"][0]["item"],
                                self.opts.lang).lower()
                        ]
                        if filtered:
                            items = filtered
                        else:
                            print("  Ничего не найдено")
                            _pause()
                    continue
                try:
                    item_id = items[int(choice) - 1]["result"][0]["item"]
                except (ValueError, IndexError):
                    continue
                self._history_options(item_id)
                # после выхода возвращаемся к списку предметов

    def _history_options(self, item_id: str) -> None:
        limit = 200
        sort = "newest"
        days: int | None = None
        while True:
            _clear()
            name = get_item_name(self._item_index, item_id, self.opts.lang)
            print(f"── История: {name} ({item_id}) ──\n")
            print(f"  1. Лимит: {limit}")
            print(f"  2. Сортировка: {sort}")
            print(f"  3. За последние дней: {days if days else 'все'}")
            print(f"  4. ✅ Показать историю")
            print(f"  0. ← К списку предметов")
            choice = _ask("\nДействие [0-4]: ")
            if choice == "1":
                v = _ask("Лимит (1-1000): ")
                try:
                    limit = max(1, min(1000, int(v)))
                except ValueError:
                    pass
            elif choice == "2":
                print("\n  1. newest  2. oldest  3. price-asc  4. price-desc")
                v = _ask("Выбор: ")
                mapping = {"1": "newest", "2": "oldest",
                           "3": "price-asc", "4": "price-desc"}
                if v in mapping:
                    sort = mapping[v]
            elif choice == "3":
                v = _ask("Дней (0 = все): ")
                try:
                    n = int(v)
                    days = n if n > 0 else None
                except ValueError:
                    pass
            elif choice == "4":
                self._run_history(item_id, limit, sort, days)
                _pause()
            elif choice in ("0", ""):
                return

    def _run_history(self, item_id: str, limit: int, sort: str,
                     days: int | None) -> None:
        _clear()
        ctx = self._context()
        from core.runner import run_history
        try:
            run_history(item_id, self.opts, ctx,
                        limit=limit, sort=sort, days=days)
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {e}")

    def _ensure_craft(self) -> set[str]:
        self._ensure_price()
        exclusions = load_exclusions()
        if self.opts.recursive:
            if (self._craft_calc is None
                    or self._excl_snapshot != frozenset(exclusions)):
                self._craft_calc = CraftCalculator(
                    self._hideout, self._price_service,
                    max_depth=self.opts.max_depth,
                    exclusions=exclusions,
                )
                self._excl_snapshot = frozenset(exclusions)
        else:
            self._craft_calc = None
        return exclusions

    def _context(self) -> AnalysisContext:
        exclusions = self._ensure_craft()
        return AnalysisContext(
            item_index=self._item_index,
            hideout=self._hideout,
            price_service=self._price_service,
            craft_calc=self._craft_calc,
            exclusions=exclusions,
        )

    def _shutdown(self) -> None:
        if self._price_service is not None:
            self._price_service.stop_heartbeat()

    # ────────── главное меню ──────────
    def run(self) -> None:
        try:
            while True:
                _clear()
                print("══════════════════════════════════════════════════════")
                print("  🧪 Stalcraft Crafting Calculator — меню")
                print("══════════════════════════════════════════════════════\n")
                print("  1. 🧮 Посчитать крафт предмета")
                print("  2. 🏆 Топ по категориям")
                print("  3. 🎁 Управление исключениями")
                print("  4. 📖 Справка")
                print("  5. 🧑 Профиль персонажа")
                print("  6. 🧾 История покупок предмета")   
                print("  7. 🚪 Выход\n")                  
                choice = _ask("Выбор [1-7]: ")
                if choice == "1":
                    self._menu_recipe()
                elif choice == "2":
                    self._menu_batch()
                elif choice == "3":
                    self._menu_exclusions()
                elif choice == "4":
                    self._menu_help()
                elif choice == "5":
                    self._menu_character()
                elif choice == "6":
                    self._menu_history()                   
                elif choice in ("7", "q", ""):
                    break
        except KeyboardInterrupt:
            print()
        finally:
            self._shutdown()

    # ────────── вспомогательное ──────────
    def _recipe_level(self, recipe: dict) -> int:
        perks = recipe.get("requirements", {}).get("perks", {})
        return max(perks.values()) if perks else 0

    def _group_recipes(self):
        from config import EXCLUDED_TOP_CATEGORIES
        groups: dict[str, list[dict]] = {}
        cat_names: dict[str, str] = {}
        order: list[str] = []
        for r in self._hideout["recipes"]:
            cid = extract_category_id(r) or "other"
            if cid in EXCLUDED_TOP_CATEGORIES:
                continue
            if cid not in groups:
                groups[cid] = []
                order.append(cid)
                cat_names[cid] = (r["category"]["lines"].get(self.opts.lang)
                                  or cid)
            groups[cid].append(r)
        return groups, cat_names, order

    # ────────── 🧮 recipe ──────────
    def _menu_recipe(self) -> None:
        self._ensure_data()
        groups, cat_names, order = self._group_recipes()

        while True:  # категории
            _clear()
            print("── Категории ──\n")
            for i, cid in enumerate(order, 1):
                print(f"  {i:2d}. {cat_names[cid]}  ({len(groups[cid])})")
            print("   0. ← Назад")
            choice = _ask("\nВыбор: ")
            if choice in ("", "0"):
                return
            try:
                cid = order[int(choice) - 1]
            except (ValueError, IndexError):
                _pause()
                continue

            sample_by_item: dict[str, dict] = {}
            levels_by_item: dict[str, int] = {}
            for r in groups[cid]:
                rid = r["result"][0]["item"]
                lvl = self._recipe_level(r)
                if rid not in sample_by_item or lvl < levels_by_item[rid]:
                    sample_by_item[rid] = r
                    levels_by_item[rid] = lvl

            all_item_ids = list(sample_by_item.keys())
            sort_mode = "alpha"
            filter_query = ""

            while True:  # предметы внутри категории
                def _sort_key(iid: str):
                    name = get_item_name(self._item_index, iid,
                                        self.opts.lang).lower()
                    if sort_mode == "level":
                        return (levels_by_item.get(iid, 0), name)
                    return (0, name)

                item_ids = sorted(all_item_ids, key=_sort_key)
                if filter_query:
                    item_ids = [
                        iid for iid in item_ids
                        if filter_query in get_item_name(
                            self._item_index, iid, self.opts.lang).lower()
                    ]

                _clear()
                sort_label = ("по алфавиту" if sort_mode == "alpha"
                              else "по уровню")
                filter_note = (f", фильтр: «{filter_query}»"
                               if filter_query else "")
                print(f"── {cat_names[cid]} ── "
                      f"({len(item_ids)} предметов, {sort_label}{filter_note})\n")

                if not item_ids:
                    print("  Ничего не найдено.")
                elif sort_mode == "level":
                    current_level = -1
                    for i, iid in enumerate(item_ids, 1):
                        lvl = levels_by_item.get(iid, 0)
                        if lvl != current_level:
                            current_level = lvl
                            if lvl:
                                print(f"\n  ── Уровень {lvl} ──")
                            else:
                                print("\n  ── Без перка ──")
                        r = sample_by_item[iid]
                        name = get_item_name(self._item_index, iid,
                                            self.opts.lang)
                        print(f"  {i:3d}. {name}  ×{r['result'][0]['amount']}")
                else:
                    for i, iid in enumerate(item_ids, 1):
                        r = sample_by_item[iid]
                        name = get_item_name(self._item_index, iid,
                                            self.opts.lang)
                        print(f"  {i:3d}. {name}  ×{r['result'][0]['amount']}")

                print()
                print("    A. 🔤 По алфавиту")
                print("    L. 📊 По уровню крафта")
                print("    F. 🔍 Поиск по названию")
                if filter_query:
                    print("    R. ↺ Сбросить фильтр")
                print("    0. ← К категориям")

                choice = _ask("\nВыбор: ").strip()
                if choice in ("", "0"):
                    break
                if choice.upper() == "A":
                    sort_mode = "alpha"
                    continue
                if choice.upper() == "L":
                    sort_mode = "level"
                    continue
                if choice.upper() == "F":
                    q = _ask("Подстрока: ").lower()
                    if q:
                        filter_query = q
                    continue
                if choice.upper() == "R" and filter_query:
                    filter_query = ""
                    continue
                try:
                    iid = item_ids[int(choice) - 1]
                except (ValueError, IndexError):
                    continue
                self._recipe_options(iid)

    def _recipe_options(self, item_id: str) -> None:
        while True:
            _clear()
            name = get_item_name(self._item_index, item_id, self.opts.lang)
            print(f"── {name} ({item_id}) ──\n")
            print("── Опции анализа ──")
            mark = lambda b: "✓" if b else " "
            print(f"  1. Recursive (min рынок/крафт): {mark(self.opts.recursive)}")
            print(f"  2. Показывать itemId: {mark(self.opts.show_ids)}")
            print(f"  3. Explain (почему рынок/крафт): {mark(self.opts.explain)}")
            print(f"  4. Explain-tree (диагностика): {mark(self.opts.explain_tree)}")
            print(f"  5. No-history (быстрее): {mark(self.opts.no_history)}")
            print(f"  6. Комиссия: {self.opts.fee:.1f}%")
            print(f"  7. Регион: {self.opts.region}")
            print(f"  8. 🎁 Исключения (текущих: {len(load_exclusions())})")
            print(f"  9. ✅ Запустить анализ")
            print(f"  0. ← К списку предметов")
            choice = _ask("\nДействие [0-9]: ")

            if choice == "1":
                self.opts.recursive = not self.opts.recursive
            elif choice == "2":
                self.opts.show_ids = not self.opts.show_ids
            elif choice == "3":
                self.opts.explain = not self.opts.explain
            elif choice == "4":
                self.opts.explain_tree = not self.opts.explain_tree
            elif choice == "5":
                self.opts.no_history = not self.opts.no_history
            elif choice == "6":
                v = _ask("Комиссия %: ")
                try:
                    self.opts.fee = float(v)
                except ValueError:
                    pass
            elif choice == "7":
                v = _ask("Регион [RU/EU/...]: ").upper()
                if v:
                    self.opts.region = v
            elif choice == "8":
                self._recipe_exclusions(item_id)
            elif choice == "9":
                self._run_recipe(item_id)
                _pause()
            elif choice in ("0", ""):
                return

    def _recipe_exclusions(self, item_id: str) -> None:
        recipes = find_recipes_by_result(self._hideout, item_id)
        if not recipes:
            print("  Рецепт не найден")
            _pause()
            return
        ing_ids: set[str] = set()
        for r in recipes:
            for ing in r["ingredients"]:
                ing_ids.add(ing["item"])
        items = sorted(
            ing_ids,
            key=lambda x: get_item_name(self._item_index, x, self.opts.lang),
        )

        while True:
            _clear()
            current = load_exclusions()
            name = get_item_name(self._item_index, item_id, self.opts.lang)
            print(f"── Исключения для «{name}» ──\n")
            print("  Прямые ингредиенты (🎁 = уже исключён):\n")
            for i, iid in enumerate(items, 1):
                m = "🎁" if iid in current else "  "
                print(f"  {i:2d}. {m} "
                      f"{get_item_name(self._item_index, iid, self.opts.lang):30s}  ({iid})")
            print("\n  +N — добавить N-й;  -N — убрать N-й;  0 — готово")
            choice = _ask("\nДействие: ").strip()
            if choice in ("", "0"):
                return
            if choice and choice[0] in "+-" and len(choice) > 1:
                try:
                    idx = int(choice[1:]) - 1
                    target = items[idx]
                    if choice[0] == "+":
                        add_exclusions({target})
                    else:
                        remove_exclusions({target})
                except (ValueError, IndexError):
                    pass

    def _run_recipe(self, item_id: str) -> None:
        _clear()
        ctx = self._context()
        run_recipe(item_id, self.opts, ctx)
        # ctx.close() не вызываем — сессия сохраняет PriceService

    # ────────── 🏆 batch ──────────
    def _menu_batch(self) -> None:
        per_cat = True
        top_n = 5
        while True:
            _clear()
            print("── Топ по категориям ──\n")
            print(f"  Режим: {'по категориям' if per_cat else 'общий топ'}")
            print(f"  Top N: {top_n}")
            print(f"  Recursive: {'✓' if self.opts.recursive else ' '}")
            print(f"  No-history: {'✓' if self.opts.no_history else ' '}")
            print(f"  Комиссия: {self.opts.fee:.1f}%")
            print()
            print("  1. ✅ Запустить анализ")
            print("  2. Переключить режим")
            print("  3. Изменить Top N")
            print("  4. Recursive on/off")
            print("  5. No-history on/off")
            print("  0. ← Назад")
            choice = _ask("\nДействие: ")
            if choice == "1":
                self._run_batch(per_cat, top_n)
                _pause()
            elif choice == "2":
                per_cat = not per_cat
            elif choice == "3":
                v = _ask("Top N: ")
                try:
                    top_n = max(1, int(v))
                except ValueError:
                    pass
            elif choice == "4":
                self.opts.recursive = not self.opts.recursive
            elif choice == "5":
                self.opts.no_history = not self.opts.no_history
            elif choice in ("0", ""):
                return

    def _run_batch(self, per_cat: bool, top_n: int) -> None:
        _clear()
        ctx = self._context()
        recipes = list(ctx.hideout["recipes"])
        run_batch(
            self.opts, ctx, recipes,
            per_category=per_cat,
            top=top_n,
            max_recipes=20,
            sort="margin",
        )

    # ────────── 🎁 exclusions ──────────
    def _menu_exclusions(self) -> None:
        self._ensure_data()
        while True:
            _clear()
            current = load_exclusions()
            print("── Исключения (нулевая стоимость) ──\n")
            print(f"  Текущих: {len(current)}\n")
            print("  1. 📋 Показать список")
            print("  2. ➕ Добавить по id (через пробел)")
            print("  3. ➖ Удалить по id")
            print("  4. 🗑️  Очистить всё")
            print("  0. ← Назад")
            choice = _ask("\nДействие: ")
            if choice == "1":
                _clear()
                if not current:
                    print("Исключений нет.")
                else:
                    for iid in sorted(current):
                        print(f"  {iid:8s} "
                              f"{get_item_name(self._item_index, iid, self.opts.lang)}")
                _pause()
            elif choice == "2":
                raw = _ask("itemId (через пробел): ")
                items = [x for x in raw.split() if x]
                if items:
                    add_exclusions(set(items))
            elif choice == "3":
                raw = _ask("itemId (через пробел): ")
                items = [x for x in raw.split() if x]
                if items:
                    remove_exclusions(set(items))
            elif choice == "4":
                if _ask("Точно очистить? [y/N]: ").lower().startswith("y"):
                    clear_exclusions()
            elif choice in ("0", ""):
                return

    # ────────── 📖 help ──────────
    def _menu_help(self) -> None:
        _clear()
        print_operations()
        _pause()


def run_menu() -> int:
    MenuSession().run()
    return 0