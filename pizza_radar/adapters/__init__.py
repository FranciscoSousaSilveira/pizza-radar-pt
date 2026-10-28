"""Adaptadores de recolha para as quatro marcas de pizza em Lisboa."""

from pizza_radar.adapters.dominos import DominosAdapter
from pizza_radar.adapters.glovo_telepizza import GlovoTelepizzaAdapter
from pizza_radar.adapters.obscura_scraper import (
    ObscuraExecutionError,
    ObscuraFetchResult,
    ObscuraNotFoundError,
    ObscuraScraper,
)
from pizza_radar.adapters.papa_johns import PapaJohnsAdapter
from pizza_radar.adapters.pizza_hut import PizzaHutAdapter
from pizza_radar.adapters.telepizza import TelepizzaAdapter

__all__ = [
    "PapaJohnsAdapter",
    "DominosAdapter",
    "GlovoTelepizzaAdapter",
    "TelepizzaAdapter",
    "PizzaHutAdapter",
    "ObscuraScraper",
    "ObscuraFetchResult",
    "ObscuraNotFoundError",
    "ObscuraExecutionError",
]
