import pytest


# ────────────────────────────────────────────────────────────
#  База: рынок / нет цены
# ────────────────────────────────────────────────────────────
def test_market_only_no_recipe(make_calc):
    calc = make_calc(prices={"a": 10.0}, recipes=[])
    r = calc.resolve("a", 5)
    assert r.source == "market"
    assert r.cost == 50.0
    assert r.unit_price == 10.0
    assert r.market_cost == 50.0
    assert r.craft_cost is None


def test_no_price_no_recipe(make_calc):
    calc = make_calc(prices={}, recipes=[])
    r = calc.resolve("a", 5)
    assert r.source == "none"
    assert r.cost is None


def test_only_craft_no_market(make_calc):
    recipe = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "b", "amount": 1}],
        "energy": 0.0,
    }
    calc = make_calc(prices={"b": 30.0}, recipes=[recipe])  # нет "a"
    r = calc.resolve("a", 1)
    assert r.source == "craft"
    assert r.cost == 30.0
    assert r.market_cost is None


# ────────────────────────────────────────────────────────────
#  Выбор min(рынок, крафт)
# ────────────────────────────────────────────────────────────
def test_craft_cheaper_than_market(make_calc):
    recipe = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "b", "amount": 1}],
        "energy": 0.0,
    }
    calc = make_calc(prices={"a": 100.0, "b": 30.0}, recipes=[recipe])
    r = calc.resolve("a", 1)
    assert r.source == "craft"
    assert r.cost == 30.0
    assert r.market_cost == 100.0
    assert r.craft_cost == 30.0
    assert r.why and "крафт" in r.why


def test_market_cheaper_than_craft(make_calc):
    recipe = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "b", "amount": 1}],
        "energy": 0.0,
    }
    calc = make_calc(prices={"a": 10.0, "b": 30.0}, recipes=[recipe])
    r = calc.resolve("a", 1)
    assert r.source == "market"
    assert r.cost == 10.0


def test_market_equal_to_craft_prefers_market(make_calc):
    # код: `if market_cost <= craft_result.cost` → при равенстве рынок
    recipe = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "b", "amount": 1}],
        "energy": 0.0,
    }
    calc = make_calc(prices={"a": 30.0, "b": 30.0}, recipes=[recipe])
    r = calc.resolve("a", 1)
    assert r.source == "market"
    assert r.cost == 30.0


def test_best_recipe_chosen_among_many(make_calc):
    r1 = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "b", "amount": 1}],
        "energy": 0.0,
    }
    r2 = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "c", "amount": 1}],
        "energy": 0.0,
    }
    calc = make_calc(
        prices={"a": 1e6, "b": 100.0, "c": 30.0},
        recipes=[r1, r2],
    )
    r = calc.resolve("a", 1)
    assert r.source == "craft"
    assert r.cost == 30.0
    assert r.craft_recipe is r2


# ────────────────────────────────────────────────────────────
#  Энергия
# ────────────────────────────────────────────────────────────
def test_energy_cost_added(make_calc):
    recipe = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "b", "amount": 1}],
        "energy": 5000.0,  # ровно 1 "401j"
    }
    calc = make_calc(
        prices={"a": 1e6, "b": 10.0, "401j": 100.0},
        recipes=[recipe],
    )
    r = calc.resolve("a", 1)
    assert r.source == "craft"
    assert r.ingredients_cost == 10.0
    assert r.energy_cost == 100.0
    assert r.cost == 110.0


def test_energy_missing_skips_craft(make_calc):
    recipe = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "b", "amount": 1}],
        "energy": 1000.0,
    }
    calc = make_calc(prices={"a": 200.0, "b": 10.0}, recipes=[recipe])
    # нет цены на 401j → крафт невозможен → рынок
    r = calc.resolve("a", 1)
    assert r.source == "market"
    assert r.cost == 200.0


def test_energy_excluded_is_free(make_calc):
    recipe = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "b", "amount": 1}],
        "energy": 5000.0,
    }
    calc = make_calc(
        prices={"a": 1e6, "b": 10.0},  # нет 401j
        recipes=[recipe],
        exclusions={"401j"},
    )
    r = calc.resolve("a", 1)
    assert r.source == "craft"
    assert r.energy_cost == 0.0
    assert r.cost == 10.0


# ────────────────────────────────────────────────────────────
#  Исключения
# ────────────────────────────────────────────────────────────
def test_excluded_item_zero_cost(make_calc):
    calc = make_calc(prices={"a": 100.0}, recipes=[], exclusions={"a"})
    r = calc.resolve("a", 3)
    assert r.source == "excluded"
    assert r.cost == 0.0
    assert r.unit_price == 0.0


def test_excluded_ingredient_used_in_craft(make_calc):
    recipe = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "b", "amount": 2}],
        "energy": 0.0,
    }
    calc = make_calc(
        prices={"a": 1e6, "b": 50.0},
        recipes=[recipe],
        exclusions={"b"},
    )
    r = calc.resolve("a", 1)
    assert r.source == "craft"
    assert r.cost == 0.0


# ────────────────────────────────────────────────────────────
#  Циклы, глубина, мемоизация
# ────────────────────────────────────────────────────────────
def test_cycle_protection(make_calc):
    # a -> b -> a
    recipes = [
        {"result": [{"item": "a", "amount": 1}],
         "ingredients": [{"item": "b", "amount": 1}], "energy": 0.0},
        {"result": [{"item": "b", "amount": 1}],
         "ingredients": [{"item": "a", "amount": 1}], "energy": 0.0},
    ]
    calc = make_calc(prices={"a": 100.0, "b": 200.0}, recipes=recipes)
    r = calc.resolve("a", 1)
    # внутренний крафт "a" внутри "b" запрещён (a в path) → для b рынок 200,
    # значит крафт a стоит 200 > рынка 100 → выбираем рынок
    assert r.source == "market"
    assert r.cost == 100.0


def test_max_depth_zero_disables_craft(make_calc):
    recipe = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "b", "amount": 1}],
        "energy": 0.0,
    }
    calc = make_calc(
        prices={"a": 100.0, "b": 1.0},
        recipes=[recipe],
        max_depth=0,
    )
    r = calc.resolve("a", 1)
    assert r.source == "market"
    assert r.cost == 100.0


def test_memoization(make_calc):
    recipe = {
        "result": [{"item": "a", "amount": 1}],
        "ingredients": [{"item": "b", "amount": 1}],
        "energy": 0.0,
    }
    calc = make_calc(prices={"a": 100.0, "b": 10.0}, recipes=[recipe])
    calc.resolve("a", 1)
    before = calc.resolve_stats()["cache_hits"]
    calc.resolve("a", 1)
    after = calc.resolve_stats()["cache_hits"]
    assert after == before + 1


# ────────────────────────────────────────────────────────────
#  Перепроизводство (yield)
# ────────────────────────────────────────────────────────────
def test_overproduction(make_calc):
    # 1 прогон даёт 4 шт. Нужно 5 → 2 прогона.
    recipe = {
        "result": [{"item": "a", "amount": 4}],
        "ingredients": [{"item": "b", "amount": 2}],
        "energy": 0.0,
    }
    calc = make_calc(prices={"a": 1e6, "b": 10.0}, recipes=[recipe])
    r = calc.resolve("a", 5)
    assert r.source == "craft"
    assert r.craft_runs == 2
    assert r.craft_yield == 8
    # ingredients: b * 2 * 2 = 4 ед. * 10 = 40
    assert r.cost == 40.0
    # unit_price = 40 / 5 (запрошено), не 40 / 8
    assert r.unit_price == 8.0