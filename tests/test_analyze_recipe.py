import pytest

from services.craft import analyze_recipe


def _recipe(
    result: str = "a",
    amount: int = 1,
    ingredients: list | None = None,
    energy: float = 0.0,
) -> dict:
    return {
        "result": [{"item": result, "amount": amount}],
        "ingredients": ingredients or [],
        "energy": energy,
        "category": {"lines": {"ru": "cat"}},
        "subcategory": {"lines": {"ru": "sub"}},
    }


# ────────────────────────────────────────────────────────────
#  Базовый расчёт
# ────────────────────────────────────────────────────────────
def test_analyze_recipe_basic(fake_price_service, make_index):
    recipe = _recipe(
        result="a",
        ingredients=[{"item": "b", "amount": 2}],
    )
    index = make_index({"a": "A", "b": "B"})
    ps = fake_price_service({"a": 100.0, "b": 20.0})

    a = analyze_recipe(recipe, index, ps, fee_pct=5.0)

    assert a.result_name == "A"
    assert a.result_amount == 1
    assert a.ingredients_cost == 40.0
    assert a.energy == 0.0
    assert a.energy_cost == 0.0
    assert a.total_cost == 40.0

    assert a.result_revenue_gross == 100.0
    assert a.fee_amount == 5.0
    assert a.result_revenue_net == 95.0
    assert a.profit == 55.0
    assert a.margin_pct == pytest.approx(137.5)

    assert a.missing_ingredients == 0
    assert a.missing_energy is False
    assert a.partial is False


def test_analyze_recipe_zero_fee(fake_price_service, make_index):
    recipe = _recipe(ingredients=[{"item": "b", "amount": 1}])
    index = make_index({"a": "A", "b": "B"})
    ps = fake_price_service({"a": 100.0, "b": 10.0})

    a = analyze_recipe(recipe, index, ps, fee_pct=0.0)
    assert a.fee_amount == 0.0
    assert a.result_revenue_net == 100.0
    assert a.profit == 90.0


# ────────────────────────────────────────────────────────────
#  Пропущенные цены
# ────────────────────────────────────────────────────────────
def test_analyze_recipe_missing_ingredient(fake_price_service, make_index):
    recipe = _recipe(ingredients=[{"item": "b", "amount": 2}])
    index = make_index({"a": "A", "b": "B"})
    ps = fake_price_service({"a": 100.0})  # нет "b"

    a = analyze_recipe(recipe, index, ps)
    assert a.missing_ingredients == 1
    assert a.total_cost is None
    assert a.profit is None
    assert a.margin_pct is None
    assert a.partial is False


def test_analyze_recipe_ignore_missing(fake_price_service, make_index):
    recipe = _recipe(ingredients=[{"item": "b", "amount": 2}])
    index = make_index({"a": "A", "b": "B"})
    ps = fake_price_service({"a": 100.0})

    a = analyze_recipe(recipe, index, ps, ignore_missing=True)
    assert a.partial is True
    assert a.ingredients_cost == 0.0
    assert a.total_cost == 0.0
    assert a.profit == 100.0
    # margin = None, потому что total_cost = 0
    assert a.margin_pct is None


# ────────────────────────────────────────────────────────────
#  Энергия
# ────────────────────────────────────────────────────────────
def test_analyze_recipe_missing_energy(fake_price_service, make_index):
    recipe = _recipe(
        ingredients=[{"item": "b", "amount": 1}],
        energy=5000.0,
    )
    index = make_index({"a": "A", "b": "B"})
    ps = fake_price_service({"a": 100.0, "b": 10.0})  # нет 401j

    a = analyze_recipe(recipe, index, ps)
    assert a.missing_energy is True
    assert a.energy_cost is None
    assert a.total_cost is None
    assert a.profit is None


def test_analyze_recipe_energy_computed(fake_price_service, make_index):
    recipe = _recipe(
        ingredients=[{"item": "b", "amount": 1}],
        energy=5000.0,
    )
    index = make_index({"a": "A", "b": "B"})
    ps = fake_price_service({"a": 1e6, "b": 10.0, "401j": 100.0})

    a = analyze_recipe(recipe, index, ps)
    assert a.energy == 5000.0
    assert a.energy_cost == 100.0
    assert a.total_cost == 110.0


# ────────────────────────────────────────────────────────────
#  Исключения
# ────────────────────────────────────────────────────────────
def test_analyze_recipe_excluded(fake_price_service, make_index):
    recipe = _recipe(ingredients=[{"item": "b", "amount": 3}])
    index = make_index({"a": "A", "b": "B"})
    ps = fake_price_service({"a": 100.0, "b": 999.0})

    a = analyze_recipe(recipe, index, ps, exclusions={"b"})
    assert a.ingredients_cost == 0.0
    assert a.excluded_summary == {"b": 3}
    assert a.total_cost == 0.0


# ────────────────────────────────────────────────────────────
#  Рекурсивный крафт
# ────────────────────────────────────────────────────────────
def test_analyze_recipe_with_craft_calc(make_calc, make_index):
    
    recipe_a = _recipe(ingredients=[{"item": "b", "amount": 1}])
    recipe_b = _recipe(result="b", ingredients=[{"item": "c", "amount": 1}])

    calc = make_calc(
        prices={"a": 500.0, "b": 300.0, "c": 50.0},
        recipes=[recipe_a, recipe_b],
    )
    index = make_index({"a": "A", "b": "B", "c": "C"})

    a = analyze_recipe(recipe_a, index, calc.price_service, craft_calc=calc)
    assert a.ingredients[0].source == "craft"
    assert a.ingredients[0].total_price == 50.0

    # required_total = только листья выбранного пути
    assert a.required_total == {"c": (1, "market")}
    # full_tree — то же самое (c — база, b крафтится, a — верх)
    assert a.full_tree == {"c": (1, "market")}

# ────────────────────────────────────────────────────────────
#  Округление отображаемых цен
# ────────────────────────────────────────────────────────────
def test_analyze_recipe_rounds_unit_price_before_total(fake_price_service, make_index):
    recipe = _recipe(ingredients=[{"item": "b", "amount": 3}])
    index = make_index({"a": "A", "b": "B"})
    ps = fake_price_service({"a": 100.0, "b": 10.6})

    analysis = analyze_recipe(recipe, index, ps)

    assert analysis.ingredients[0].unit_price == 11.0
    assert analysis.ingredients[0].total_price == 33.0
    assert analysis.ingredients_cost == 33.0
