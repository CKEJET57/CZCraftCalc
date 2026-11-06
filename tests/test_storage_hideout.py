from storage.hideout import (
    extract_category_id,
    filter_recipes,
    find_recipes_by_result,
)


def _recipe(
    cat_key: str = "hideout.benches.categories.ammunition.name",
    bench: str = "workbench",
    perks: dict | None = None,
    result: str = "a",
    ingredients: list | None = None,
) -> dict:
    return {
        "bench": bench,
        "category": {"key": cat_key},
        "subcategory": {"key": "x"},
        "result": [{"item": result, "amount": 1}],
        "ingredients": ingredients or [],
        "requirements": {"perks": perks or {}},
    }


def test_extract_category_id():
    assert (
        extract_category_id(
            {"category": {"key": "hideout.benches.categories.ammunition.name"}}
        )
        == "ammunition"
    )
    assert extract_category_id({"category": {"key": "no.markers.here"}}) is None
    assert extract_category_id({}) is None


def test_find_recipes_by_result():
    data = {"recipes": [
        _recipe(result="a"),
        _recipe(result="b"),
        _recipe(result="a"),
    ]}
    assert len(find_recipes_by_result(data, "a")) == 2
    assert len(find_recipes_by_result(data, "z")) == 0


def test_filter_recipes_by_bench():
    data = {"recipes": [
        _recipe(bench="workbench"),
        _recipe(bench="laboratory_table"),
    ]}
    assert len(filter_recipes(data, bench="workbench")) == 1


def test_filter_recipes_by_category():
    data = {"recipes": [
        _recipe(cat_key="hideout.benches.categories.ammunition.name"),
        _recipe(cat_key="hideout.benches.categories.armor.name"),
    ]}
    assert len(filter_recipes(data, category_id="armor")) == 1


def test_filter_recipes_by_perk():
    data = {"recipes": [
        _recipe(perks={"ammunition": 1}),
        _recipe(perks={"armorer": 1}),
    ]}
    assert len(filter_recipes(data, perk_id="ammunition")) == 1