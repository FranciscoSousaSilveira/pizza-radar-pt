"""Algoritmo determinístico de normalização de valor: Pizza Value Index.

Calcula a área útil e o valor real por unidade de área e por dose para comparar
pizzas individuais, médias e familiares sem ilusões de marketing.

Modelagem de diâmetros canónicos em Portugal (em centímetros):
- INDIVIDUAL: ~20 cm
- MEDIUM: ~30 cm
- LARGE: ~35 cm
- FAMILY: ~38 cm

Métricas calculadas:
- Área útil em cm²: Área = π * (diâmetro / 2)² * quantidade de pizzas
- Preço por 100 cm² (em cêntimos e euros formatados)
- Doses / Pessoas estimadas com base na área total (~450 cm² por pessoa)
- Preço estimado por pessoa / dose
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from pizza_radar.core.models import PizzaSize

# Diâmetros médios canónicos em Portugal (cm)
DIAMETER_BY_SIZE_CM: dict[PizzaSize, float] = {
    PizzaSize.INDIVIDUAL: 20.0,
    PizzaSize.MEDIUM: 30.0,
    PizzaSize.LARGE: 35.0,
    PizzaSize.FAMILY: 38.0,
}

# Área média de referência consumida por pessoa adulta numa refeição (~450 cm², aprox. meia pizza média de 30cm que tem ~706 cm²)
CM2_PER_PORTION: float = 450.0


@dataclass(frozen=True)
class PizzaValueMetrics:
    """Métricas de valor e rendimento de uma oferta de pizza."""

    pizza_size: PizzaSize
    pizza_count: int
    single_diameter_cm: float
    single_area_cm2: float
    total_area_cm2: float
    price_cents: int
    price_per_100_cm2_cents: int
    price_per_100_cm2_euros: float
    estimated_portions: int
    price_per_portion_cents: int
    price_per_portion_euros: float
    value_badge_label: str
    portion_badge_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pizza_size": self.pizza_size.value,
            "pizza_count": self.pizza_count,
            "single_diameter_cm": round(self.single_diameter_cm, 1),
            "single_area_cm2": round(self.single_area_cm2, 1),
            "total_area_cm2": round(self.total_area_cm2, 1),
            "price_cents": self.price_cents,
            "price_per_100_cm2_cents": self.price_per_100_cm2_cents,
            "price_per_100_cm2_euros": round(self.price_per_100_cm2_euros, 2),
            "estimated_portions": self.estimated_portions,
            "price_per_portion_cents": self.price_per_portion_cents,
            "price_per_portion_euros": round(self.price_per_portion_euros, 2),
            "value_badge_label": self.value_badge_label,
            "portion_badge_label": self.portion_badge_label,
        }


def compute_pizza_area_cm2(diameter_cm: float) -> float:
    """Calcula a área de uma pizza em centímetros quadrados: Area = π * (d / 2)^2."""
    radius = diameter_cm / 2.0
    return math.pi * (radius ** 2)


def calculate_pizza_area_cm2(pizza_size: PizzaSize | str | None, count: int = 1) -> float:
    """Calcula a área total de pizzas em cm² a partir do tamanho e quantidade."""
    if not pizza_size or count <= 0:
        return 0.0
    if isinstance(pizza_size, str):
        try:
            p_size = PizzaSize(pizza_size)
        except ValueError:
            return 0.0
    else:
        p_size = pizza_size
    diameter = DIAMETER_BY_SIZE_CM.get(p_size)
    if not diameter:
        return 0.0
    return compute_pizza_area_cm2(diameter) * count


def estimate_portions(total_area_cm2: float) -> int:
    """Estima o número de pessoas/doses a partir da área total em cm² (~450 cm² por pessoa)."""
    if total_area_cm2 <= 0:
        return 1
    return max(1, round(total_area_cm2 / CM2_PER_PORTION))


def compute_value_metrics(
    price_cents: int | None,
    pizza_size: PizzaSize | str | None,
    pizza_count: int | None = 1,
) -> PizzaValueMetrics | None:
    """Calcula as métricas determinísticas do Pizza Value Index.

    Devolve None se o preço ou o tamanho não permitirem cálculo objetivo.
    """
    if price_cents is None or price_cents <= 0:
        return None

    # Normalizar tamanho
    if isinstance(pizza_size, str):
        try:
            p_size = PizzaSize(pizza_size)
        except ValueError:
            p_size = PizzaSize.UNKNOWN
    elif isinstance(pizza_size, PizzaSize):
        p_size = pizza_size
    else:
        p_size = PizzaSize.UNKNOWN

    if p_size == PizzaSize.UNKNOWN or p_size not in DIAMETER_BY_SIZE_CM:
        return None

    count = max(1, pizza_count or 1)
    diameter = DIAMETER_BY_SIZE_CM[p_size]
    single_area = compute_pizza_area_cm2(diameter)
    total_area = single_area * count

    if total_area <= 0:
        return None

    # Preço por 100 cm² em cêntimos inteiros (via Decimal para precisão absoluta)
    d_price = Decimal(price_cents)
    d_area_hundreds = Decimal(str(total_area / 100.0))
    price_per_100_cents = int((d_price / d_area_hundreds).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    price_per_100_euros = float(price_per_100_cents) / 100.0

    # Estimativa de doses / pessoas
    raw_portions = total_area / CM2_PER_PORTION
    estimated_portions = max(1, round(raw_portions))

    d_portions = Decimal(estimated_portions)
    price_per_portion_cents = int((d_price / d_portions).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    price_per_portion_euros = float(price_per_portion_cents) / 100.0

    # Selos e labels descritivos
    euro_100 = f"{price_per_100_euros:.2f}".replace(".", ",")
    value_badge = f"{euro_100} € / 100 cm²"

    if estimated_portions == 1:
        portion_badge = "Ideal para 1 pessoa"
    else:
        portion_badge = f"Ideal para {estimated_portions} pessoas"

    return PizzaValueMetrics(
        pizza_size=p_size,
        pizza_count=count,
        single_diameter_cm=diameter,
        single_area_cm2=single_area,
        total_area_cm2=total_area,
        price_cents=price_cents,
        price_per_100_cm2_cents=price_per_100_cents,
        price_per_100_cm2_euros=price_per_100_euros,
        estimated_portions=estimated_portions,
        price_per_portion_cents=price_per_portion_cents,
        price_per_portion_euros=price_per_portion_euros,
        value_badge_label=value_badge,
        portion_badge_label=portion_badge,
    )
