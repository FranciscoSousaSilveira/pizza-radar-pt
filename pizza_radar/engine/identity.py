"""Identidade persistente, variantes de loja e agrupamento visual determinístico.

Resolve formalmente os três níveis de identidade de dados promocionais:
1. Identidade Persistente (PersistentIdentity):
   - ID estável no tempo para rastreio de histórico (tabela `observation_history`).
   - Não se altera quando lojas anteriormente convergentes passam a ter preços
     diferentes, nem quando voltam a convergir.
   - Baseia-se no identificador intrínseco da campanha na marca e canal de atendimento.
2. Variante por Loja (StoreVariant):
   - Modela divergências reais de preço, contagem de pizzas, datas de validade ou condições.
3. Agrupamento Visual (VisualPromoGroup):
   - Garante que a interface do utilizador nunca exibe cartões duplicados para a mesma campanha.
   - Independente da ordem de entrada dos dados (100% determinístico e idempotente).
   - Calcula preço unitário por pizza estritamente a partir de variantes individualmente comparáveis.
   - Calcula o instante mais recente de observação normalizado para UTC.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
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

_KNOWN_VENDOR_PREFIXES = ("pj_", "dom_", "tp_", "ph_")
_KNOWN_CHANNEL_SUFFIX_PATTERNS = [
    r"_in_store(?:_[0-9]+)*$",
    r"_pj_delivery(?:_[0-9]+)*$",
    r"_takeaway(?:_[0-9]+)*$",
    r"_delivery(?:_[0-9]+)*$",
    r"_promo(?:_[0-9]+)*$",
]
_SUFFIX_REGEX = re.compile("|".join(_KNOWN_CHANNEL_SUFFIX_PATTERNS), re.IGNORECASE)


def extract_canonical_campaign_id(promo_id: str) -> str:
    """Extrai o identificador canónico da campanha a partir de um ID de UnifiedPromo.

    Remove prefixos conhecidos de marca (ex.: 'pj_', 'dom_', 'tp_', 'ph_') e sufixos
    de canal e lojas aderentes (ex.: '_in_store', '_delivery_2_13', '_takeaway').
    Preserva underscores ou hífenes internos ao identificador da campanha
    (ex.: 'pj_super_combo_familia_in_store' -> 'super_combo_familia').
    """
    s = promo_id.strip()
    for pfx in _KNOWN_VENDOR_PREFIXES:
        if s.lower().startswith(pfx):
            s = s[len(pfx):]
            break

    match = _SUFFIX_REGEX.search(s)
    if match:
        s = s[:match.start()]

    return s if s else promo_id


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
    pizza_count: int | None = None
    pizza_size: PizzaSize = PizzaSize.UNKNOWN
    is_comparable_for_unit_price: bool = False
    observed_at: str | None = None
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
    def price_per_pizza_cents(self) -> int | None:
        """Calcula o preço unitário apenas se esta variante for individualmente comparável."""
        if self.is_comparable_for_unit_price and self.price_cents is not None and self.pizza_count and self.pizza_count > 0:
            return round(self.price_cents / self.pizza_count)
        return None

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
    image_url: str | None = None
    source_url: str = ""
    days_of_week: list[Weekday] = field(default_factory=list)
    location_scope: str = "Lisboa"

    @property
    def is_comparable_for_unit_price(self) -> bool:
        """Verdadeiro se existir pelo menos uma variante individualmente comparável."""
        return any(v.is_comparable_for_unit_price for v in self.variants)

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
        """Menor preço unitário por pizza calculado apenas entre variantes comparáveis.

        Regra estrita: nunca divide o menor preço global do grupo pela contagem de pizzas
        de outra variante.
        """
        unit_prices = [
            v.price_per_pizza_cents for v in self.variants
            if v.is_comparable_for_unit_price and v.price_per_pizza_cents is not None
        ]
        return min(unit_prices) if unit_prices else None

    @property
    def min_price_per_pizza_euros(self) -> float | None:
        cents = self.min_price_per_pizza_cents
        return round(cents / 100.0, 2) if cents is not None else None

    @property
    def max_discount_percentage(self) -> float | None:
        """Maior percentagem de desconto efetivo comprovado entre as variantes."""
        discounts = [v.computed_discount_percentage for v in self.variants if v.computed_discount_percentage is not None]
        return max(discounts) if discounts else None

    @property
    def most_recent_observed_at(self) -> str | None:
        """Calcula o instante mais recente real entre as variantes normalizado para UTC."""
        timestamps: list[datetime] = []
        for v in self.variants:
            if v.observed_at:
                try:
                    dt = datetime.fromisoformat(v.observed_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    timestamps.append(dt.astimezone(timezone.utc))
                except ValueError:
                    pass
        if not timestamps:
            return None
        return max(timestamps).isoformat()


def group_promos_for_visual_presentation(promos: list[UnifiedPromo]) -> list[VisualPromoGroup]:
    """Agrupa deterministicamente uma lista de UnifiedPromo em VisualPromoGroup.

    Garante:
    - 1 único cartão por par (campanha, canal).
    - Independente da ordem de inserção na lista de entrada.
    - Preserva e agrega lojas aderentes e variantes de preço com rigor.
    """
    grouped: dict[str, list[UnifiedPromo]] = {}

    for promo in promos:
        campaign_id = extract_canonical_campaign_id(promo.id)
        method = promo.dispatch_methods[0] if promo.dispatch_methods else DispatchMethod.DELIVERY
        pid = build_persistent_promo_id(promo.vendor, campaign_id, method)
        grouped.setdefault(pid, []).append(promo)

    visual_groups: list[VisualPromoGroup] = []

    # Ordem determinística estável de chaves
    for pid in sorted(grouped.keys()):
        raw_items = grouped[pid]

        # Ordenar deterministicamente as ofertas do grupo para eliminar dependência da ordem de entrada
        def _item_sort_key(p: UnifiedPromo) -> tuple:
            return (
                p.price_cents if p.price_cents is not None else 999999,
                p.title,
                p.id,
            )
        sorted_items = sorted(raw_items, key=_item_sort_key)
        best_item = sorted_items[0]

        # Extrair lojas e variantes
        all_store_ids_set: set[str] = set()
        all_store_names_set: set[str] = set()
        variants: list[StoreVariant] = []

        for promo in sorted_items:
            for sid in promo.store_ids:
                all_store_ids_set.add(sid)
            for sname in promo.store_names:
                all_store_names_set.add(sname)

            variants.append(
                StoreVariant(
                    variant_id=promo.id,
                    persistent_id=pid,
                    store_ids=sorted(promo.store_ids, key=lambda s: (0, int(s)) if s.isdigit() else (1, s)),
                    store_names=sorted(promo.store_names),
                    price_cents=promo.price_cents,
                    original_price_cents=promo.original_price_cents,
                    pizza_count=promo.pizza_count,
                    pizza_size=promo.pizza_size,
                    is_comparable_for_unit_price=promo.is_comparable_for_unit_price,
                    observed_at=promo.observed_at,
                    conditions=promo.conditions,
                    valid_from=promo.valid_from,
                    valid_until=promo.valid_until,
                )
            )

        sorted_store_ids = sorted(all_store_ids_set, key=lambda s: (0, int(s)) if s.isdigit() else (1, s))
        sorted_store_names = sorted(all_store_names_set)

        # Imagem determinística (primeira válida encontrada na ordem ordenada)
        image_url = next((p.image_url for p in sorted_items if p.image_url), None)

        # Combinação determinística de dias da semana
        all_day_sets = [set(p.days_of_week) for p in sorted_items]
        if any(len(s) == 0 for s in all_day_sets):
            # Se pelo menos uma loja oferece diariamente sem restrição, a oferta é diária
            combined_days: list[Weekday] = []
        else:
            union_days = set().union(*all_day_sets)
            weekday_order = {w: idx for idx, w in enumerate(Weekday)}
            combined_days = sorted(union_days, key=lambda w: weekday_order[w])

        # pizza_count representativo da melhor variante comparável (ou da primeira variante)
        comp_variant = next((v for v in variants if v.is_comparable_for_unit_price), None)
        pizza_count = comp_variant.pizza_count if comp_variant else best_item.pizza_count
        pizza_size = comp_variant.pizza_size if comp_variant else best_item.pizza_size

        vg = VisualPromoGroup(
            persistent_id=pid,
            vendor=best_item.vendor,
            title=best_item.title,
            description=best_item.description,
            dispatch_methods=best_item.dispatch_methods,
            store_scope=best_item.store_scope,
            all_store_ids=sorted_store_ids,
            all_store_names=sorted_store_names,
            variants=variants,
            pizza_count=pizza_count,
            pizza_size=pizza_size,
            image_url=image_url,
            source_url=best_item.source_url,
            days_of_week=combined_days,
            location_scope=best_item.location_scope,
        )
        visual_groups.append(vg)

    return visual_groups
