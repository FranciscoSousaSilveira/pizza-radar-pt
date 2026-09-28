"""Rankings determinísticos, explicáveis e transparentes para ofertas de pizza.

Implementa quatro eixos de ordenação objetivos e independentes:
1. BEST_UNIT_PRICE: Menor custo por pizza individual (estritamente para ofertas comparáveis).
2. HIGHEST_DISCOUNT: Maior percentagem de desconto efetivo comprovado.
3. LOWEST_ABSOLUTE_PRICE: Menor desembolso absoluto total.
4. RECENTLY_OBSERVED: Ofertas mais recentemente observadas (normalizadas em UTC).

Regras de ouro:
- Zero IA em runtime (cálculos 100% matemáticos e determinísticos).
- Explicações transparentes geradas por regras para cada posição de ranking.
- Desempates estáveis por menor preço e identificador persistente.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pizza_radar.core.models import UnifiedPromo
from pizza_radar.engine.identity import VisualPromoGroup


class RankingCriteria(str, Enum):
    """Eixos independentes de classificação de ofertas."""

    BEST_UNIT_PRICE = "BEST_UNIT_PRICE"
    HIGHEST_DISCOUNT = "HIGHEST_DISCOUNT"
    LOWEST_ABSOLUTE_PRICE = "LOWEST_ABSOLUTE_PRICE"
    RECENTLY_OBSERVED = "RECENTLY_OBSERVED"


@dataclass(slots=True)
class RankedItem:
    """Registo classificado num ranking determinístico com justificação explicável."""

    rank: int
    item: UnifiedPromo | VisualPromoGroup
    criteria: RankingCriteria
    score: float | int
    explanation: str

    @property
    def promo_id(self) -> str:
        if isinstance(self.item, UnifiedPromo):
            return self.item.id
        return self.item.persistent_id


def rank_by_unit_price(items: list[UnifiedPromo | VisualPromoGroup]) -> list[RankedItem]:
    """Ordena ofertas pelo menor preço unitário por pizza (apenas comparáveis).

    Regra estrita: apenas calcula a partir de variantes individualmente comparáveis.
    Nunca divide o menor preço global do grupo pela contagem de pizzas de outra variante.
    """
    eligible: list[tuple[int, UnifiedPromo | VisualPromoGroup, str]] = []

    for item in items:
        if isinstance(item, UnifiedPromo):
            if (
                item.is_comparable_for_unit_price
                and item.price_per_pizza_cents is not None
                and item.price_euros is not None
                and item.pizza_count
            ):
                unit_cents = item.price_per_pizza_cents
                unit_euros = unit_cents / 100.0
                expl = (
                    f"{unit_euros:.2f}€ por pizza ({item.pizza_count} pizzas por {item.price_euros:.2f}€)"
                    .replace(".", ",")
                )
                eligible.append((unit_cents, item, expl))
        elif isinstance(item, VisualPromoGroup):
            # Encontra variantes estritamente comparáveis dentro do grupo
            comp_variants = [
                v for v in item.variants
                if v.is_comparable_for_unit_price and v.price_per_pizza_cents is not None and v.pizza_count
            ]
            if comp_variants:
                # Escolhe a melhor variante comparável do grupo
                best_var = min(
                    comp_variants,
                    key=lambda v: (v.price_per_pizza_cents or 999999, v.price_cents or 999999)
                )
                if best_var.price_per_pizza_cents is not None and best_var.price_cents is not None:
                    unit_cents = best_var.price_per_pizza_cents
                    unit_euros = unit_cents / 100.0
                    total_euros = best_var.price_cents / 100.0
                    prefix = "desde " if not item.has_uniform_price else ""
                    expl = (
                        f"{prefix}{unit_euros:.2f}€ por pizza ({best_var.pizza_count} pizzas por {total_euros:.2f}€)"
                        .replace(".", ",")
                    )
                    eligible.append((unit_cents, item, expl))

    # Ordenação: menor preço por pizza, desempate por menor preço total, depois por ID
    def sort_key(entry: tuple[int, Any, str]) -> tuple[int, int, str]:
        unit_c, it, _ = entry
        total_c = it.price_cents if isinstance(it, UnifiedPromo) else (it.min_price_cents or 0)
        pid = it.id if isinstance(it, UnifiedPromo) else it.persistent_id
        return (unit_c, total_c or 0, pid)

    sorted_eligible = sorted(eligible, key=sort_key)

    ranked: list[RankedItem] = []
    for idx, (unit_cents, item, expl) in enumerate(sorted_eligible, start=1):
        ranked.append(
            RankedItem(
                rank=idx,
                item=item,
                criteria=RankingCriteria.BEST_UNIT_PRICE,
                score=unit_cents,
                explanation=expl,
            )
        )
    return ranked


def rank_by_discount(items: list[UnifiedPromo | VisualPromoGroup]) -> list[RankedItem]:
    """Ordena ofertas pela maior percentagem de desconto efetivo comprovado.

    Exclui itens sem desconto comprovado ou com dados inconsistentes.
    Explicação: 'X,X% de desconto (Poupança de Y,YY€)'.
    """
    eligible: list[tuple[float, UnifiedPromo | VisualPromoGroup, str]] = []

    for item in items:
        if isinstance(item, UnifiedPromo):
            pct = item.computed_discount_percentage or item.discount_percentage
            savings = item.savings_amount_euros
            if pct is not None and pct > 0:
                savings_txt = f" (Poupança de {savings:.2f}€)".replace(".", ",") if savings else ""
                expl = f"{pct:.1f}% de desconto{savings_txt}".replace(".", ",")
                eligible.append((float(pct), item, expl))
        elif isinstance(item, VisualPromoGroup):
            pct = item.max_discount_percentage
            if pct is not None and pct > 0:
                expl = f"Até {pct:.1f}% de desconto comprovado".replace(".", ",")
                eligible.append((float(pct), item, expl))

    # Ordenação: maior percentagem (decrescente), desempate por menor preço total, depois ID
    def sort_key(entry: tuple[float, Any, str]) -> tuple[float, int, str]:
        pct, it, _ = entry
        total_c = it.price_cents if isinstance(it, UnifiedPromo) else (it.min_price_cents or 0)
        pid = it.id if isinstance(it, UnifiedPromo) else it.persistent_id
        return (-pct, total_c or 0, pid)

    sorted_eligible = sorted(eligible, key=sort_key)

    ranked: list[RankedItem] = []
    for idx, (pct, item, expl) in enumerate(sorted_eligible, start=1):
        ranked.append(
            RankedItem(
                rank=idx,
                item=item,
                criteria=RankingCriteria.HIGHEST_DISCOUNT,
                score=pct,
                explanation=expl,
            )
        )
    return ranked


def rank_by_lowest_price(items: list[UnifiedPromo | VisualPromoGroup]) -> list[RankedItem]:
    """Ordena ofertas pelo menor preço absoluto (desembolso mínimo em cêntimos).

    Explicação: 'Preço total de X,XX€'.
    """
    eligible: list[tuple[int, UnifiedPromo | VisualPromoGroup, str]] = []

    for item in items:
        if isinstance(item, UnifiedPromo):
            if item.price_cents is not None and item.price_euros is not None:
                expl = f"Preço de {item.price_euros:.2f}€".replace(".", ",")
                eligible.append((item.price_cents, item, expl))
        elif isinstance(item, VisualPromoGroup):
            if item.min_price_cents is not None and item.min_price_euros is not None:
                prefix = "Desde " if not item.has_uniform_price else "Preço de "
                expl = f"{prefix}{item.min_price_euros:.2f}€".replace(".", ",")
                eligible.append((item.min_price_cents, item, expl))

    def sort_key(entry: tuple[int, Any, str]) -> tuple[int, str]:
        cents, it, _ = entry
        pid = it.id if isinstance(it, UnifiedPromo) else it.persistent_id
        return (cents, pid)

    sorted_eligible = sorted(eligible, key=sort_key)

    ranked: list[RankedItem] = []
    for idx, (cents, item, expl) in enumerate(sorted_eligible, start=1):
        ranked.append(
            RankedItem(
                rank=idx,
                item=item,
                criteria=RankingCriteria.LOWEST_ABSOLUTE_PRICE,
                score=cents,
                explanation=expl,
            )
        )
    return ranked


def rank_by_recently_observed(items: list[UnifiedPromo | VisualPromoGroup]) -> list[RankedItem]:
    """Ordena ofertas por data de observação mais recente normalizada para UTC."""
    eligible: list[tuple[datetime, UnifiedPromo | VisualPromoGroup, str]] = []

    for item in items:
        dt: datetime | None = None
        if isinstance(item, UnifiedPromo):
            if item.observed_at:
                try:
                    d = datetime.fromisoformat(item.observed_at)
                    dt = d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
        elif isinstance(item, VisualPromoGroup):
            rec = item.most_recent_observed_at
            if rec:
                try:
                    d = datetime.fromisoformat(rec)
                    dt = d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

        if dt is not None:
            expl = f"Observado em {dt.strftime('%Y-%m-%d %H:%M UTC')}"
            eligible.append((dt, item, expl))

    def sort_key(entry: tuple[datetime, Any, str]) -> tuple[float, int, str]:
        dt, it, _ = entry
        total_c = it.price_cents if isinstance(it, UnifiedPromo) else (it.min_price_cents or 0)
        pid = it.id if isinstance(it, UnifiedPromo) else it.persistent_id
        return (-dt.timestamp(), total_c or 0, pid)

    sorted_eligible = sorted(eligible, key=sort_key)

    ranked: list[RankedItem] = []
    for idx, (dt, item, expl) in enumerate(sorted_eligible, start=1):
        ranked.append(
            RankedItem(
                rank=idx,
                item=item,
                criteria=RankingCriteria.RECENTLY_OBSERVED,
                score=int(dt.timestamp()),
                explanation=expl,
            )
        )
    return ranked
