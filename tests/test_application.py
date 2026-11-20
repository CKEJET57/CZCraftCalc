from __future__ import annotations

from types import SimpleNamespace

from services import application


def test_options_builder_maps_analysis_settings():
    opts = application._options({
        "region": "EU",
        "lang": "en",
        "fee": 7.5,
        "recursive": True,
        "max_depth": 8,
        "no_fallback": True,
        "no_history": True,
        "workers": 2,
        "ignore_missing": True,
        "exclude": ["a", "b"],
        "use_local_data": True,
    })

    assert opts.region == "EU"
    assert opts.lang == "en"
    assert opts.fee == 7.5
    assert opts.recursive is True
    assert opts.max_depth == 8
    assert opts.no_fallback is True
    assert opts.no_history is True
    assert opts.workers == 2
    assert opts.ignore_missing is True
    assert opts.exclude == "a,b"
    assert opts.use_local_data is True
    assert opts.no_heartbeat is True
    assert opts.verbose is False


def test_recipe_operation_returns_serialized_craft_results(monkeypatch):
    state = SimpleNamespace(build_context=lambda opts: SimpleNamespace(item_index={}))
    monkeypatch.setattr(application, "analyze_recipe_by_id", lambda item_id, opts, ctx: [object()])
    monkeypatch.setattr(
        application, "serialize_recipe_list",
        lambda analyses, item_index, lang: [{"profit": 123, "ingredients": []}],
    )

    result = application.recipe_operation(state, {"item_id": "item-42"})

    assert result == {
        "item_id": "item-42",
        "recipes": [{"profit": 123, "ingredients": [], "kind": "craft"}],
    }


def test_recipe_operation_returns_empty_result_when_no_craft_or_barter(monkeypatch):
    state = SimpleNamespace(build_context=lambda opts: SimpleNamespace(item_index={}))
    monkeypatch.setattr(application, "analyze_recipe_by_id", lambda item_id, opts, ctx: [])
    monkeypatch.setattr(application, "_barter_recipes", lambda *args: [])

    assert application.recipe_operation(state, {"item_id": "unknown"}) == {
        "item_id": "unknown",
        "recipes": [],
    }
