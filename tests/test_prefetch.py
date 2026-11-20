from __future__ import annotations

from types import SimpleNamespace

from core.prefetch import build_prefetch_plan, execute_prefetch


class FakePriceService:
    def __init__(self, cached=()):
        self.cached = set(cached)
        self.calls = []

    def is_cached(self, item_id):
        return item_id in self.cached

    def prefetch(self, items, workers=1, progress=None):
        self.calls.append((items, workers, progress))


def make_context(*, cached=(), craft_calc=None, exclusions=None):
    service = FakePriceService(cached)
    ctx = SimpleNamespace(
        exclusions=set(exclusions or ()),
        craft_calc=craft_calc,
        price_service=service,
    )
    return ctx, service


def test_prefetch_plan_collects_direct_items_and_respects_exclusions(monkeypatch):
    monkeypatch.setattr("core.prefetch.ENERGY_ITEM_ID", "energy")
    ctx, service = make_context(cached={"ore"}, exclusions={"ignored"})
    opts = SimpleNamespace(recursive=False, workers=3)
    recipes = [{
        "result": [{"item": "product"}],
        "ingredients": [{"item": "ore"}, {"item": "ignored"}],
    }]

    plan = build_prefetch_plan(opts, ctx, recipes)

    assert plan.items == {"energy", "product", "ore"}
    assert set(plan.missing) == {"energy", "product"}
    assert service.calls == []


def test_prefetch_plan_uses_recursive_tree_when_enabled(monkeypatch):
    monkeypatch.setattr("core.prefetch.ENERGY_ITEM_ID", "energy")
    craft_calc = SimpleNamespace(collect_tree_items=lambda recipes: {"tree-a", "tree-b"})
    ctx, _ = make_context(craft_calc=craft_calc, exclusions={"tree-a"})
    opts = SimpleNamespace(recursive=True, workers=2)

    plan = build_prefetch_plan(opts, ctx, [{"result": [{"item": "ignored"}]}])

    assert plan.items == {"tree-a", "tree-b"}


def test_execute_prefetch_uses_workers_and_progress():
    ctx, service = make_context()
    opts = SimpleNamespace(workers=4)
    progress = lambda done, total, item_id: None
    plan = build_prefetch_plan(
        SimpleNamespace(recursive=False, workers=4),
        ctx,
        [{"result": [{"item": "product"}], "ingredients": []}],
    )

    count = execute_prefetch(plan, opts, ctx, progress=progress)

    assert count == len(plan.missing)
    assert len(service.calls) == 1
    items, workers, callback = service.calls[0]
    assert set(items) == set(plan.missing)
    assert workers == 4
    assert callback is progress


def test_execute_prefetch_skips_service_when_everything_is_cached(monkeypatch):
    monkeypatch.setattr("core.prefetch.ENERGY_ITEM_ID", "energy")
    ctx, service = make_context(cached={"energy", "product"})
    opts = SimpleNamespace(recursive=False, workers=1)
    plan = build_prefetch_plan(
        opts, ctx, [{"result": [{"item": "product"}], "ingredients": []}],
    )

    assert execute_prefetch(plan, opts, ctx) == 0
    assert service.calls == []
