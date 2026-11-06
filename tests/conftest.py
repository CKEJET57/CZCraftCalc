import os
# ОБЯЗАТЕЛЬНО до первого import config
os.environ.setdefault("STALCRAFT_CLIENT_SECRET", "test-secret-not-real")

import pytest

from services.craft import CraftCalculator
from services.price import PriceInfo, PriceService


@pytest.fixture
def fake_price_service():
    """Фабрика мок-PriceService с фиксированными ценами.

    get(item_id) -> PriceInfo(unit_price, "history"|"none")
    """
    def make(prices: dict[str, float | None]):
        class _FPS:
            def __init__(self):
                self._prices = dict(prices)

            def get(self, item_id: str) -> PriceInfo:
                p = self._prices.get(item_id)
                if p is None:
                    return PriceInfo(item_id, None, "none", 0)
                return PriceInfo(item_id, p, "history", 10)

            def stop_heartbeat(self) -> None:
                pass

        return _FPS()

    return make


@pytest.fixture
def make_calc(fake_price_service):
    """Фабрика CraftCalculator с заданными ценами и рецептами."""
    def make(
        prices: dict[str, float | None],
        recipes: list[dict],
        exclusions: set[str] | None = None,
        max_depth: int = 12,
    ) -> CraftCalculator:
        ps = fake_price_service(prices)
        return CraftCalculator(
            {"recipes": recipes},
            ps,
            max_depth=max_depth,
            exclusions=exclusions,
        )

    return make


@pytest.fixture
def make_index():
    """Собирает item_index вида {item_id: {"name": {"lines": {lang: name}}}}."""
    def make(names: dict[str, str]) -> dict:
        return {
            iid: {"name": {"lines": {"ru": name, "en": name}}}
            for iid, name in names.items()
        }

    return make


@pytest.fixture
def make_price_service():
    """Реальный PriceService с отключённым heartbeat (для HTTP-моков)."""
    created: list[PriceService] = []

    def make(**kwargs) -> PriceService:
        kwargs.setdefault("heartbeat", False)
        kwargs.setdefault("max_requests", 100)
        ps = PriceService("test-token", **kwargs)
        created.append(ps)
        return ps

    yield make

    for ps in created:
        ps.close()