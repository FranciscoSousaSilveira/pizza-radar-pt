"""Filtros determinísticos para coleções de promoções e grupos visuais."""

from __future__ import annotations

from typing import TypeVar

from pizza_radar.core.models import Brand, DispatchMethod, UnifiedPromo, Weekday
from pizza_radar.engine.identity import VisualPromoGroup

T = TypeVar("T", UnifiedPromo, VisualPromoGroup)


def filter_by_brand(items: list[T], brands: Brand | list[Brand]) -> list[T]:
    """Filtra ofertas por uma ou mais marcas suportadas."""
    allowed = {brands} if isinstance(brands, Brand) else set(brands)
    return [it for it in items if it.vendor in allowed]


def filter_by_dispatch_method(items: list[T], method: DispatchMethod) -> list[T]:
    """Filtra ofertas disponíveis para um determinado canal de atendimento."""
    return [it for it in items if method in it.dispatch_methods]


def filter_by_store(items: list[T], store_id: str) -> list[T]:
    """Filtra ofertas aplicáveis a uma loja específica no concelho de Lisboa."""
    result: list[T] = []
    for it in items:
        if isinstance(it, UnifiedPromo):
            eligible = it.is_store_eligible(store_id)
            if eligible is True:
                result.append(it)
        elif isinstance(it, VisualPromoGroup):
            if store_id in it.all_store_ids:
                result.append(it)
    return result


def filter_by_weekday(items: list[T], weekday: Weekday) -> list[T]:
    """Filtra ofertas ativas num dia específico da semana.

    Ofertas sem restrição de dia (days_of_week vazio) são consideradas diárias.
    """
    return [it for it in items if not it.days_of_week or weekday in it.days_of_week]


def filter_by_price_range(
    items: list[T],
    min_cents: int | None = None,
    max_cents: int | None = None,
) -> list[T]:
    """Filtra ofertas por intervalo de preço em cêntimos inteiros."""
    result: list[T] = []
    for it in items:
        price = it.price_cents if isinstance(it, UnifiedPromo) else it.min_price_cents
        if price is None:
            continue
        if min_cents is not None and price < min_cents:
            continue
        if max_cents is not None and price > max_cents:
            continue
        result.append(it)
    return result


def filter_comparable_only(items: list[T]) -> list[T]:
    """Filtra estritamente ofertas com dados suficientes para cálculo de preço por pizza."""
    return [it for it in items if it.is_comparable_for_unit_price]
