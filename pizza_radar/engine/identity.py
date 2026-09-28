"""Identidade persistente, variantes de loja e agrupamento visual determinístico.

Resolve formalmente os três níveis de identidade de dados promocionais:
1. Identidade Persistente (PersistentIdentity):
   - ID estável no tempo para rastreio de histórico (tabela `observation_history`).
   - Não se altera quando lojas anteriormente convergentes passam a ter preços
     diferentes, nem quando voltam a convergir.
   - Baseia-se no identificador intrínseco da campanha na marca e canal de atendimento.
2. Variante por Loja (StoreVariant):
   - Modela divergências reais de preço, datas de validade ou condições entre lojas físicas.
3. Agrupamento Visual (VisualPromoGroup):
   - Garante que a interface do utilizador nunca exibe cartões duplicados para a mesma campanha.
   - Consolida lojas aderentes, exibindo preço único quando uniforme ou faixa de preços
     ("desde X€") quando existirem divergências entre estabelecimentos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
    Weekday,
)


def extract_canonical_campaign_id(promo_id: str) -> str:
    """Extrai o identificador canónico da campanha a partir de um ID de UnifiedPromo.

    Formatos de ID padronizados pelos adaptadores:
    - pj_<offer_id>_<channel> (ex: 'pj_223_in_store' -> '223')
    - dom_<offer_id>_<channel> (ex: 'dom_2434_delivery' -> '2434')
    - tp_<offer_id>_<channel> (ex: 'tp_2admmk_takeaway' -> '2admmk')
    - ph_<offer_id>_<channel> (ex: 'ph_101_delivery' -> '101')
    """
    parts = promo_id.split("_")
    if len(parts) >= 2 and parts[0].lower() in ("pj", "dom", "tp", "ph"):
        return parts[1]
    return promo_id


def build_persistent_promo_id(vendor: Brand, campaign_id: str, dispatch_method: DispatchMethod) -> str:
    """Gera um identificador estável no tempo para histórico de observações.

    Garantia de invariância:
    - O ID permanece idêntico mesmo que lojas divirjam ou convirjam em preço.
    - Exemplo: 'pid_papa_johns_223_take_away'.
    """
    clean_campaign = campaign_id.strip().lower()
    return f"pid_{vendor.value.lower()}_{clean_campaign}_{dispatch_method.value.lower()}"


@dataclass(slots=True)
class StoreVariant:
    """Variante específica de uma promoção numa loja ou grupo de lojas."""

    variant_id: str
    persistent_id: str
    store_ids: list[str] = field(default_factory=list)
    store_names: list[str] = field(default_factory=list)
    price_cents: int | None = None
    original_price_cents: int | None = None
    conditions: str = ""
    valid_from: str | None = None
    valid_until: str | None = None

    @property
    def price_euros(self) -> float | None:
        return round(self.price_cents / 100.0, 2) if self.price_cents is not None else None

    @property
    def original_price_euros(self) -> float | None:
        return round(self.original_price_cents / 100.0, 2) if self.original_price_cents is not None else None

    @property
    def computed_discount_percentage(self) -> float | None:
        if (
            self.price_cents is not None
            and self.original_price_cents is not None
            and self.original_price_cents > 0
            and self.original_price_cents >= self.price_cents
        ):
            diff = self.original_price_cents - self.price_cents
            return round((diff / self.original_price_cents) * 100.0, 1)
        return None


@dataclass(slots=True)
class VisualPromoGroup:
    """Agrupamento visual determinístico de uma promoção para exibição no frontend.

    Invariante: O frontend nunca exibe cartões duplicados para a mesma campanha
    e modalidade de entrega.
    """

    persistent_id: str
    vendor: Brand
    title: str
    description: str
    dispatch_methods: list[DispatchMethod]
    store_scope: StoreScope
    all_store_ids: list[str] = field(default_factory=list)
    all_store_names: list[str] = field(default_factory=list)
    variants: list[StoreVariant] = field(default_factory=list)
    pizza_count: int | None = None
    pizza_size: PizzaSize = PizzaSize.UNKNOWN
    is_comparable_for_unit_price: bool = False
    image_url: str | None = None
    source_url: str = ""
    days_of_week: list[Weekday] = field(default_factory=list)
    location_scope: str = "Lisboa"

    @property
    def has_uniform_price(self) -> bool:
        """Indica se todas as variantes de loja partilham o mesmo preço."""
        distinct_prices = {v.price_cents for v in self.variants if v.price_cents is not None}
        return len(distinct_prices) <= 1

    @property
    def min_price_cents(self) -> int | None:
        """Menor preço em cêntimos entre todas as lojas aderentes."""
        prices = [v.price_cents for v in self.variants if v.price_cents is not None]
        return min(prices) if prices else None

    @property
    def max_price_cents(self) -> int | None:
        """Maior preço em cêntimos entre todas as lojas aderentes."""
        prices = [v.price_cents for v in self.variants if v.price_cents is not None]
        return max(prices) if prices else None

    @property
    def min_price_euros(self) -> float | None:
        cents = self.min_price_cents
        return round(cents / 100.0, 2) if cents is not None else None

    @property
    def max_price_euros(self) -> float | None:
        cents = self.max_price_cents
        return round(cents / 100.0, 2) if cents is not None else None

    @property
    def display_price_label(self) -> str:
        """Formata o rótulo de preço amigável para o utilizador."""
        min_p = self.min_price_euros
        max_p = self.max_price_euros
        if min_p is None:
            return "Preço sob consulta"
        if min_p == max_p or max_p is None:
            return f"{min_p:.2f}€".replace(".", ",")
        return f"Desde {min_p:.2f}€".replace(".", ",")

    @property
    def min_price_per_pizza_cents(self) -> int | None:
        """Menor preço unitário por pizza quando comparável."""
        if not self.is_comparable_for_unit_price or not self.pizza_count or self.pizza_count <= 0:
            return None
        min_p = self.min_price_cents
        return round(min_p / self.pizza_count) if min_p is not None else None

    @property
    def min_price_per_pizza_euros(self) -> float | None:
        cents = self.min_price_per_pizza_cents
        return round(cents / 100.0, 2) if cents is not None else None

    @property
    def max_discount_percentage(self) -> float | None:
        """Maior percentagem de desconto efetivo comprovado entre as variantes."""
        discounts = [v.computed_discount_percentage for v in self.variants if v.computed_discount_percentage is not None]
        return max(discounts) if discounts else None


def group_promos_for_visual_presentation(promos: list[UnifiedPromo]) -> list[VisualPromoGroup]:
    """Agrupa deterministicamente uma lista de UnifiedPromo em VisualPromoGroup.

    Garante:
    - 1 único cartão por par (campanha, canal).
    - Agregação de todas as lojas aderentes e suas respetivas variantes de preço.
    - Ordenação determinística e estável.
    """
    # Mapeia: persistent_id -> (promos_da_campanha)
    grouped: dict[str, list[UnifiedPromo]] = {}

    for promo in promos:
        campaign_id = extract_canonical_campaign_id(promo.id)
        # Se uma promoção tiver múltiplos dispatch_methods, agrupamos pelo canal primário
        method = promo.dispatch_methods[0] if promo.dispatch_methods else DispatchMethod.DELIVERY
        pid = build_persistent_promo_id(promo.vendor, campaign_id, method)
        grouped.setdefault(pid, []).append(promo)

    visual_groups: list[VisualPromoGroup] = []

    # Ordenação determinística das chaves
    for pid in sorted(grouped.keys()):
        group_items = grouped[pid]
        first = group_items[0]

        # Extrair lojas e variantes
        all_store_ids_set: set[str] = set()
        all_store_names_set: set[str] = set()
        variants: list[StoreVariant] = []

        # Determinar se a promoção tem comparabilidade de pizza unitária
        is_comparable = any(p.is_comparable_for_unit_price for p in group_items)
        pizza_count = next((p.pizza_count for p in group_items if p.pizza_count is not None), None)
        pizza_size = next((p.pizza_size for p in group_items if p.pizza_size != PizzaSize.UNKNOWN), PizzaSize.UNKNOWN)

        # Imagem e dias da semana
        image_url = next((p.image_url for p in group_items if p.image_url), None)
        days_of_week = first.days_of_week

        for promo in group_items:
            for sid in promo.store_ids:
                all_store_ids_set.add(sid)
            for sname in promo.store_names:
                all_store_names_set.add(sname)

            variants.append(
                StoreVariant(
                    variant_id=promo.id,
                    persistent_id=pid,
                    store_ids=list(promo.store_ids),
                    store_names=list(promo.store_names),
                    price_cents=promo.price_cents,
                    original_price_cents=promo.original_price_cents,
                    conditions=promo.conditions,
                    valid_from=promo.valid_from,
                    valid_until=promo.valid_until,
                )
            )

        sorted_store_ids = sorted(all_store_ids_set, key=lambda s: (0, int(s)) if s.isdigit() else (1, s))
        sorted_store_names = sorted(all_store_names_set)

        vg = VisualPromoGroup(
            persistent_id=pid,
            vendor=first.vendor,
            title=first.title,
            description=first.description,
            dispatch_methods=first.dispatch_methods,
            store_scope=first.store_scope,
            all_store_ids=sorted_store_ids,
            all_store_names=sorted_store_names,
            variants=variants,
            pizza_count=pizza_count,
            pizza_size=pizza_size,
            is_comparable_for_unit_price=is_comparable,
            image_url=image_url,
            source_url=first.source_url,
            days_of_week=days_of_week,
            location_scope=first.location_scope,
        )
        visual_groups.append(vg)

    return visual_groups
