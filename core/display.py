"""
core/display.py — функции вывода (бывший cli/render.py).
"""

from config import ENERGY_ITEM_ID
from services.craft import IngredientCost, RecipeAnalysis
from storage.listing import get_item_name


def fmt_price(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{round(v):,} ₽".replace(",", " ")


def fmt_pct(v: float | None) -> str:
    return f"{v:+.1f}%" if v is not None else "—"


def print_ingredient_line(ing: IngredientCost, indent: int = 2,
                          explain: bool = False,
                          show_ids: bool = False) -> None:
    pad = " " * indent
    tag = {"market": "рынок", "craft": "крафт",
           "none": "нет", "excluded": "ноль"}[ing.source]
    is_abnormal = (ing.source in ("none", "excluded")
                   or ing.name.startswith("[неизвестный"))
    id_col = f"{ing.item_id:6s} " if (show_ids or is_abnormal) else "       "
    line = (f"{pad}{id_col}{ing.name:30s} × {ing.amount:3d}  "
            f"[{tag:6s}]  × {fmt_price(ing.unit_price):>12s} = "
            f"{fmt_price(ing.total_price):>12s}")
    if explain and ing.craft_path and ing.craft_path.why:
        line += f"   ← {ing.craft_path.why}"
    print(line)


def print_ingredient_tree(ing, item_index, indent=2, max_depth_display=2,
                          current=0, explain=False, show_ids=False) -> None:
    print_ingredient_line(ing, indent, explain=explain, show_ids=show_ids)
    if ing.craft_path and ing.craft_path.children and current < max_depth_display:
        cp = ing.craft_path
        energy_note = ""
        if cp.energy_cost and cp.energy_cost > 0:
            energy_note = f", энергия {fmt_price(cp.energy_cost)}"
        print(f"{' ' * (indent + 2)}↳ крафт: {cp.craft_runs}× "
              f"(выход {cp.craft_yield}){energy_note}")
        for child in cp.children:
            if child.unit_price is None:
                c_unit = c_total = None
            else:
                c_unit = round(child.unit_price)
                c_total = c_unit * child.amount
            child_ing = IngredientCost(
                item_id=child.item_id,
                name=get_item_name(item_index, child.item_id),
                amount=child.amount,
                unit_price=c_unit, total_price=c_total,
                source=child.source,
                craft_path=child,
            )
            print_ingredient_tree(child_ing, item_index,
                                  indent + 4, max_depth_display,
                                  current + 1, explain=explain,
                                  show_ids=show_ids)


def print_analysis(a: RecipeAnalysis, item_index: dict,
                   craft_calc=None,
                   explain: bool = False,
                   explain_tree: bool = False,
                   show_ids: bool = False) -> None:
    print(f"\n=== {a.result_name} ×{a.result_amount} ===")
    print(f"  Верстак: {a.recipe['bench']} / {a.category_ru} / {a.subcategory_ru}")
    reqs = a.recipe.get("requirements", {})
    print(f"  Перки: {reqs.get('perks', {})}")
    print(f"  Фичи: {', '.join(reqs.get('features', [])) or '—'}")

    print("\n  Ингредиенты:")
    for i in a.ingredients:
        print_ingredient_tree(i, item_index, explain=explain, show_ids=show_ids)

    if a.excluded_summary:
        total_units = sum(a.excluded_summary.values())
        print(f"\n  🎁 Учтено как ноль ({len(a.excluded_summary)} вид., "
              f"{total_units} ед.):")
        for iid, amt in a.excluded_summary.items():
            print(f"     {get_item_name(item_index, iid):30s} × {amt:3d}")

    if a.required_total:
        total_units = sum(amt for amt, _ in a.required_total.values())
        src_priority = {"market": 0, "none": 1, "excluded": 2}
        items_sorted = sorted(
            a.required_total.items(),
            key=lambda kv: (src_priority.get(kv[1][1], 99),
                            get_item_name(item_index, kv[0])),
        )
        print(f"\n  📦 Всего потребуется ({len(a.required_total)} вид., "
              f"{total_units} ед.):")
        for iid, (amt, src) in items_sorted:
            tag = {"market": "рынок", "none": "нет",
                   "excluded": "ноль"}.get(src, src)
            id_part = f"{iid:6s} " if (show_ids or src == "none") else "       "
            print(f"     [{tag:5s}]  {id_part}"
                  f"{get_item_name(item_index, iid):30s} × {amt:4d}")

    if a.full_tree:
        total_units = sum(amt for amt, _ in a.full_tree.values())
        src_priority = {"market": 0, "lots": 0, "none": 1}
        items_sorted = sorted(
            a.full_tree.items(),
            key=lambda kv: (src_priority.get(kv[1][1], 99),
                            get_item_name(item_index, kv[0])),
        )
        print(f"\n  🌳 Если всё крафтить ({len(a.full_tree)} вид., "
              f"{total_units} ед.):")
        for iid, (amt, src) in items_sorted:
            tag = {"market": "рынок", "lots": "рынок",
                   "none": "нет"}.get(src, src)
            id_part = f"{iid:6s} " if (show_ids or src == "none") else "       "
            print(f"     [{tag:5s}]  {id_part}"
                  f"{get_item_name(item_index, iid):30s} × {amt:4d}")

    if explain_tree:
        missing = [i for i in a.ingredients if i.source == "none"]
        if missing:
            print("\n  🔎 Диагностика missing:")
            for m in missing:
                if craft_calc is not None:
                    probs = craft_calc.explain_missing(m.item_id)
                    if probs:
                        print(f"    {m.item_id} ({m.name}) — рецепты "
                              f"требуют без-ценовые: {', '.join(probs)}")
                    else:
                        print(f"    {m.item_id} ({m.name}) — нет цены "
                              f"и нет рабочего рецепта")
                else:
                    print(f"    {m.item_id} ({m.name}) — нет цены "
                          f"(без --recursive глубже нельзя)")

    partial_note = " (частично, ⚠️ ignore-missing)" if a.partial else ""
    print(f"\n  💰 Ингредиенты:   {fmt_price(a.ingredients_cost)}{partial_note}")
    if a.energy_cost is not None:
        j_count = a.energy / 5000 if a.energy > 0 else 0
        print(f"  ⚡ Энергия:       {a.energy:.0f} "
              f"({fmt_price(a.energy_cost)}, ≈{j_count:.2f}× {ENERGY_ITEM_ID})")
    else:
        print(f"  ⚡ Энергия:       {a.energy:.0f} — "
              f"⚠️ нет цены на {ENERGY_ITEM_ID}")

    print(f"  💰 Себестоимость: {fmt_price(a.total_cost)}")
    print(f"  💵 Выручка брутто: {fmt_price(a.result_revenue_gross)}")
    print(f"  💸 Комиссия ({a.fee_pct:.1f}%): -{fmt_price(a.fee_amount)}")
    print(f"  💵 Выручка нетто: {fmt_price(a.result_revenue_net)}")
    print(f"  📈 Прибыль:       {fmt_price(a.profit)}  ({fmt_pct(a.margin_pct)})"
          + ("  ⚠️ приблизительно" if a.partial else ""))

    if a.missing_ingredients:
        missing_ids = [i.item_id for i in a.ingredients if i.source == "none"]
        print(f"  ⚠️  Нет цен на {a.missing_ingredients} ингредиент(ов): "
              f"{', '.join(missing_ids)}")

    if a.missing_energy:
        print(f"  ⚠️  Нет цены на {ENERGY_ITEM_ID} — энергия не учтена")


def print_stats(price_service, craft_calc) -> None:
    st = price_service.stats()
    print(f"\n📊 API: requests={st['requests']}/{st['max_requests']}  "
          f"cache={st['cache_size']}  elapsed={st['elapsed']:.1f}s")
    if craft_calc is not None:
        cs = craft_calc.resolve_stats()
        extra = (f"  exclusions={cs['exclusions']}"
                 if cs.get("exclusions") else "")
        print(f"🧮 Resolve: calls={cs['resolve_calls']}  "
              f"cache_hits={cs['cache_hits']}  memo={cs['memo_size']}{extra}")
    if st["budget_exhausted"]:
        print("⚠️  Бюджет запросов исчерпан — часть цен не получена.")