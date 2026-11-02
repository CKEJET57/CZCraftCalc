"""
core/context.py — единый контекст анализа: данные + сервисы.
"""

from dataclasses import dataclass

from api.auth import fetch_token
from services.craft import CraftCalculator
from services.price import PriceService, phase
from storage.exclusions import load_exclusions
from storage.hideout import load_hideout_recipes
from storage.listing import build_item_index, load_listing


@dataclass
class AnalysisContext:
    item_index: dict
    hideout: dict
    price_service: PriceService
    craft_calc: CraftCalculator | None
    exclusions: set[str]

    def close(self) -> None:
        self.price_service.stop_heartbeat()


def build_context(opts) -> AnalysisContext:
    """Собирает контекст: данные + токен + сервисы."""
    with phase("Загрузка listing + рецептов"):
        listing = load_listing()
        item_index = build_item_index(listing)
        hideout = load_hideout_recipes()

    with phase("OAuth: получение токена"):
        token = fetch_token()["access_token"]

    exclusions = load_exclusions()
    if opts.exclude:
        exclusions.update(
            x.strip() for x in opts.exclude.split(",") if x.strip()
        )

    price_service = PriceService(
        token,
        region=opts.region,
        fallback_to_lots=not opts.no_fallback,
        use_history=not opts.no_history,
        max_requests=opts.max_requests,
        heartbeat=not opts.no_heartbeat,
        verbose=opts.verbose,
    )
    craft_calc = None
    if opts.recursive:
        craft_calc = CraftCalculator(
            hideout, price_service,
            max_depth=opts.max_depth,
            exclusions=exclusions,
        )
    return AnalysisContext(
        item_index=item_index, hideout=hideout,
        price_service=price_service, craft_calc=craft_calc,
        exclusions=exclusions,
    )