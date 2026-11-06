"""
services/craft.py — анализ прибыльности рецепта с учётом энергии.

Фичи:
  - --recursive: min(рынок, крафт) с мемоизацией и защитой от циклов
  - --fee: комиссия аукциона при продаже
  - энергия через покупку 401j
  - --explain / --explain-tree / --ignore-missing
  - исключения (нулевая стоимость)
  - required_total: листья выбранного пути (📦)
  - full_tree: базовые ресурсы при "всё крафтим сами" (🌳)
  - согласованное округление сумм для UI
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from config import ENERGY_ITEM_ID, ENERGY_PER_ITEM
from services.price import PriceService
from storage.listing import get_item_name


# ---------- результат resolve() для одного item/amount ----------
@dataclass
class CostResult:
    item_id: str
    amount: int
    cost: float | None
    source: str                     # "market" | "craft" | "excluded" | "none"
    unit_price: float | None
    craft_recipe: dict | None = None
    craft_runs: int = 0
    craft_yield: int = 0
    children: list["CostResult"] = field(default_factory=list)
    ingredients_cost: float | None = None
    energy_cost: float | None = None
    market_cost: float | None = None
    craft_cost: float | None = None
    why: str = ""


# ---------- сбор leaf-листьев выбранного пути (📦) ----------
def _collect_required(node: "CostResult",
                      out: dict[str, tuple[int, str]]) -> None:
    if node.source == "craft" and node.children:
        for child in node.children:
            _collect_required(child, out)
        return
    prev_amt, prev_src = out.get(node.item_id, (0, node.source))
    out[node.item_id] = (prev_amt + node.amount, prev_src)


# ---------- полное дерево: принудительно разворачиваем всё (🌳) ----------
_SRC_PRIORITY = {"history": 0, "market": 0, "lots": 0, "none": 1}


def _worse_source(a: str, b: str) -> str:
    return a if _SRC_PRIORITY.get(a, 99) >= _SRC_PRIORITY.get(b, 99) else b


def _collect_full_tree(item_id: str, amount: int,
                       calc: "CraftCalculator",
                       out: dict[str, tuple[int, str]],
                       path: frozenset[str],
                       depth: int) -> None:
    """
    Принудительно разворачивает рецепт до базовых ресурсов
    (игнорирует выбор resolve market vs craft).

    Исключённые предметы пропускаются — они уже есть на складе.
    """
    if item_id in calc.exclusions:
        return

    is_leaf = (
        item_id in path
        or depth > calc.max_depth
        or item_id not in calc.recipes_by_result
    )

    craft = None
    if not is_leaf:
        craft = calc._try_craft(item_id, amount, path, depth)
        if craft is None or not craft.children:
            is_leaf = True

    if is_leaf:
        info = calc.price_service.get(item_id)
        src = info.source if info.unit_price is not None else "none"
        prev, prev_src = out.get(item_id, (0, src))
        out[item_id] = (prev + amount, _worse_source(prev_src, src))
        return

    for child in craft.children:
        _collect_full_tree(child.item_id, child.amount, calc, out,
                           path | {item_id}, depth + 1)


class CraftCalculator:
    """Выбирает лучшее: купить на рынке или скрафтить. Учитывает энергию и исключения."""

    def __init__(self, hideout_data: dict, price_service: PriceService,
                 max_depth: int = 12, exclusions: set[str] | None = None):
        self.price_service = price_service
        self.max_depth = max_depth
        self.exclusions: set[str] = set(exclusions or [])
        self.recipes_by_result: dict[str, list[dict]] = {}
        for r in hideout_data["recipes"]:
            for res in r.get("result", []):
                self.recipes_by_result.setdefault(res["item"], []).append(r)
        self._memo: dict[tuple[str, int], CostResult] = {}
        self._resolve_calls = 0
        self._resolve_cache_hits = 0

    def resolve_stats(self) -> dict:
        return {
            "resolve_calls": self._resolve_calls,
            "cache_hits": self._resolve_cache_hits,
            "memo_size": len(self._memo),
            "exclusions": len(self.exclusions),
        }

    # ---------------- публичный API ----------------
    def resolve(self, item_id: str, amount: int,
                path: frozenset[str] = frozenset(),
                depth: int = 0) -> CostResult:
        self._resolve_calls += 1

        if item_id in self.exclusions:
            result = CostResult(
                item_id, amount, 0.0, "excluded", 0.0,
                ingredients_cost=0.0, energy_cost=0.0,
                why="исключён (нулевая стоимость)",
            )
            self._memo[(item_id, amount)] = result
            return result

        key = (item_id, amount)
        if item_id not in path and key in self._memo:
            self._resolve_cache_hits += 1
            return self._memo[key]

        price_info = self.price_service.get(item_id)
        market_unit = price_info.unit_price
        market_cost = market_unit * amount if market_unit is not None else None

        craft_result = None
        if (
            item_id not in path
            and depth < self.max_depth
            and item_id in self.recipes_by_result
        ):
            craft_result = self._try_craft(item_id, amount, path, depth)

        if market_cost is not None and craft_result is not None:
            if market_cost <= craft_result.cost:
                result = CostResult(
                    item_id, amount, market_cost, "market", market_unit,
                    ingredients_cost=market_cost, energy_cost=0.0,
                    market_cost=market_cost, craft_cost=craft_result.cost,
                    why=f"рынок {market_cost:.0f} ≤ крафт {craft_result.cost:.0f}",
                )
            else:
                craft_result.market_cost = market_cost
                craft_result.craft_cost = craft_result.cost
                craft_result.why = (f"крафт {craft_result.cost:.0f} < "
                                    f"рынок {market_cost:.0f}")
                result = craft_result
        elif market_cost is not None:
            why = ("только рынок (нет рецепта)"
                   if item_id not in self.recipes_by_result
                   else "только рынок (все рецепты недоступны)")
            result = CostResult(item_id, amount, market_cost, "market", market_unit,
                                ingredients_cost=market_cost, energy_cost=0.0,
                                market_cost=market_cost, why=why)
        elif craft_result is not None:
            craft_result.market_cost = None
            craft_result.craft_cost = craft_result.cost
            craft_result.why = "только крафт (нет цены на рынке)"
            result = craft_result
        else:
            why = ("нет цены и нет рецепта"
                   if item_id not in self.recipes_by_result
                   else "нет цены и все рецепты недоступны")
            result = CostResult(item_id, amount, None, "none", None, why=why)

        if item_id not in path:
            self._memo[key] = result
        return result

    # ---------------- энергия ----------------
    def _energy_cost(self, energy: float) -> float | None:
        if energy <= 0:
            return 0.0
        if ENERGY_ITEM_ID in self.exclusions:
            return 0.0
        info = self.price_service.get(ENERGY_ITEM_ID)
        if info.unit_price is None:
            return None
        return (energy / ENERGY_PER_ITEM) * info.unit_price

    # ---------------- рекурсивный крафт ----------------
    def _try_craft(self, item_id, amount, path, depth) -> CostResult | None:
        best: CostResult | None = None
        for recipe in self.recipes_by_result[item_id]:
            res = recipe["result"][0]
            yld = res["amount"]
            runs = math.ceil(amount / yld) if yld > 0 else 0
            if runs == 0:
                continue

            energy_total = recipe.get("energy", 0.0) * runs
            energy_cost = self._energy_cost(energy_total)
            if energy_cost is None:
                continue

            ingredients_sum = 0.0
            children: list[CostResult] = []
            ok = True
            for ing in recipe["ingredients"]:
                need = ing["amount"] * runs
                child = self.resolve(ing["item"], need, path | {item_id}, depth + 1)
                if child.cost is None:
                    ok = False
                    break
                ingredients_sum += child.cost
                children.append(child)
            if not ok:
                continue

            total = ingredients_sum + energy_cost
            if best is None or total < best.cost:
                best = CostResult(
                    item_id=item_id, amount=amount, cost=total, source="craft",
                    unit_price=total / amount,
                    craft_recipe=recipe, craft_runs=runs,
                    craft_yield=runs * yld, children=children,
                    ingredients_cost=ingredients_sum,
                    energy_cost=energy_cost,
                )
        return best

    # ---------------- explain-tree ----------------
    def explain_missing(self, item_id: str, depth: int = 0,
                        path: frozenset[str] = frozenset()) -> list[str]:
        if depth > 4 or item_id in path:
            return []
        if item_id in self.exclusions:
            return []
        recipes = self.recipes_by_result.get(item_id, [])
        if not recipes:
            return []
        problems: set[str] = set()
        for recipe in recipes:
            for ing in recipe["ingredients"]:
                ing_id = ing["item"]
                if ing_id in self.exclusions:
                    continue
                info = self.price_service.get(ing_id)
                if info.unit_price is not None:
                    continue
                if ing_id in self.recipes_by_result:
                    sub = self.explain_missing(ing_id, depth + 1, path | {item_id})
                    problems.update(sub if sub else {ing_id})
                else:
                    problems.add(ing_id)
        return sorted(problems)

    # ---------------- сбор дерева для prefetch ----------------
    def collect_tree_items(self, recipes: list[dict]) -> set[str]:
        seen_recipes: set[int] = set()
        items: set[str] = set()
        frontier = list(recipes)
        for _ in range(self.max_depth):
            nxt: list[dict] = []
            for r in frontier:
                rid = id(r)
                if rid in seen_recipes:
                    continue
                seen_recipes.add(rid)
                for res in r.get("result", []):
                    items.add(res["item"])
                for ing in r.get("ingredients", []):
                    if ing["item"] in self.exclusions:
                        continue
                    items.add(ing["item"])
                    for child in self.recipes_by_result.get(ing["item"], []):
                        nxt.append(child)
            if not nxt:
                break
            frontier = nxt
        if ENERGY_ITEM_ID not in self.exclusions:
            items.add(ENERGY_ITEM_ID)
        return items


# ---------- данные для отчёта ----------
@dataclass
class IngredientCost:
    item_id: str
    name: str
    amount: int
    unit_price: float | None
    total_price: float | None
    source: str
    craft_path: CostResult | None = None


@dataclass
class RecipeAnalysis:
    recipe: dict
    result_item_id: str
    result_name: str
    result_amount: int
    result_revenue_gross: float | None
    fee_pct: float
    fee_amount: float | None
    result_revenue_net: float | None
    ingredients: list[IngredientCost]
    ingredients_cost: float | None
    energy: float
    energy_cost: float | None
    total_cost: float | None
    profit: float | None
    margin_pct: float | None
    missing_ingredients: int
    missing_energy: bool
    partial: bool
    excluded_summary: dict[str, int]                # 🎁
    required_total: dict[str, tuple[int, str]]      # 📦 (листья выбранного пути)
    full_tree: dict[str, tuple[int, str]]           # 🌳 (базовые, если всё крафтим)
    category_ru: str
    subcategory_ru: str


# ---------- согласованное округление ----------
def _display_prices(unit_price: float | None,
                    amount: int) -> tuple[float | None, float | None]:
    if unit_price is None:
        return None, None
    return float(u), float(u * amount)


# ---------- анализ одного рецепта ----------
def analyze_recipe(
    recipe: dict,
    item_index: dict[str, dict],
    price_service: PriceService,
    fee_pct: float = 0.0,
    craft_calc: CraftCalculator | None = None,
    lang: str = "ru",
    ignore_missing: bool = False,
    exclusions: set[str] | frozenset[str] = frozenset(),
) -> RecipeAnalysis:
    result = recipe["result"][0]
    result_item_id = result["item"]
    result_amount = result["amount"]
    result_name = get_item_name(item_index, result_item_id, lang)

    result_info = price_service.get(result_item_id)
    revenue_gross = (result_info.unit_price * result_amount
                     if result_info.unit_price is not None else None)
    fee_amount = (revenue_gross * fee_pct / 100.0
                  if revenue_gross is not None else None)
    revenue_net = (revenue_gross - fee_amount
                   if revenue_gross is not None else None)

    ingredients: list[IngredientCost] = []
    ingredients_sum = 0.0
    missing = 0
    required_total: dict[str, tuple[int, str]] = {}   # 📦
    full_tree: dict[str, tuple[int, str]] = {}        # 🌳

    for ing in recipe["ingredients"]:
        name = get_item_name(item_index, ing["item"], lang)
        craft_path: CostResult | None = None

        if craft_calc is not None:
            cr = craft_calc.resolve(ing["item"], ing["amount"])
            _collect_required(cr, required_total)
            _collect_full_tree(ing["item"], ing["amount"], craft_calc,
                               full_tree, frozenset(), 0)
            if cr.cost is None:
                unit_disp = total_disp = None
                source = "none"
            else:
                source = cr.source
                unit_disp, total_disp = _display_prices(
                    cr.cost / ing["amount"], ing["amount"]
                )
            if cr.source == "craft" or cr.why:
                craft_path = cr
        elif ing["item"] in exclusions:
            unit_disp, total_disp = 0.0, 0.0
            source = "excluded"
            prev, prev_src = required_total.get(ing["item"], (0, "excluded"))
            required_total[ing["item"]] = (prev + ing["amount"], prev_src)
            # в full_tree исключённые не попадают
        else:
            info = price_service.get(ing["item"])
            if info.unit_price is None:
                unit_disp = total_disp = None
                source = "none"
                src_for_total = "none"
            else:
                # info.source = "history" | "lots" — для UI это всё "market"
                source = "market"
                src_for_total = "market"
                unit_disp, total_disp = _display_prices(
                    info.unit_price, ing["amount"]
                )
            prev, prev_src = required_total.get(ing["item"], (0, src_for_total))
            required_total[ing["item"]] = (prev + ing["amount"], prev_src)
            prev, prev_src = full_tree.get(ing["item"], (0, src_for_total))
            full_tree[ing["item"]] = (prev + ing["amount"], prev_src)

        if total_disp is None:
            missing += 1
        else:
            ingredients_sum += total_disp

        ingredients.append(IngredientCost(
            item_id=ing["item"], name=name, amount=ing["amount"],
            unit_price=unit_disp, total_price=total_disp,
            source=source, craft_path=craft_path,
        ))

    excluded_summary = {
        k: v[0] for k, v in required_total.items() if v[1] == "excluded"
    }

    if missing == 0:
        ingredients_cost = round(ingredients_sum)
        partial = False
    elif ignore_missing:
        ingredients_cost = round(ingredients_sum)
        partial = True
    else:
        ingredients_cost = None
        partial = False

    energy = recipe.get("energy", 0.0)
    energy_cost: float | None
    missing_energy = False
    if energy > 0:
        if ENERGY_ITEM_ID in exclusions:
            energy_cost = 0.0
        else:
            e_info = price_service.get(ENERGY_ITEM_ID)
            if e_info.unit_price is not None:
                energy_cost = round((energy / ENERGY_PER_ITEM) * e_info.unit_price)
            else:
                energy_cost = None
                missing_energy = True
    else:
        energy_cost = 0.0

    if ingredients_cost is not None and energy_cost is not None:
        total_cost = ingredients_cost + energy_cost
    else:
        total_cost = None

    cat = recipe["category"]["lines"].get(lang) or ""
    subcat = recipe["subcategory"]["lines"].get(lang) or ""

    if total_cost is None or revenue_net is None:
        return RecipeAnalysis(
            recipe=recipe, result_item_id=result_item_id,
            result_name=result_name, result_amount=result_amount,
            result_revenue_gross=revenue_gross, fee_pct=fee_pct,
            fee_amount=fee_amount, result_revenue_net=revenue_net,
            ingredients=ingredients,
            ingredients_cost=ingredients_cost,
            energy=energy, energy_cost=energy_cost,
            total_cost=None, profit=None, margin_pct=None,
            missing_ingredients=missing, missing_energy=missing_energy,
            partial=partial,
            excluded_summary=excluded_summary,
            required_total=required_total,
            full_tree=full_tree,
            category_ru=cat, subcategory_ru=subcat,
        )

    profit = revenue_net - total_cost
    margin = (profit / total_cost * 100) if total_cost > 0 else None

    return RecipeAnalysis(
        recipe=recipe, result_item_id=result_item_id,
        result_name=result_name, result_amount=result_amount,
        result_revenue_gross=revenue_gross, fee_pct=fee_pct,
        fee_amount=fee_amount, result_revenue_net=revenue_net,
        ingredients=ingredients,
        ingredients_cost=ingredients_cost,
        energy=energy, energy_cost=energy_cost,
        total_cost=total_cost, profit=profit, margin_pct=margin,
        missing_ingredients=missing, missing_energy=missing_energy,
        partial=partial,
        excluded_summary=excluded_summary,
        required_total=required_total,
        full_tree=full_tree,
        category_ru=cat, subcategory_ru=subcat,
    )