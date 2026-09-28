"""Modelos de dados canónicos para o Pizza Radar PT."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Brand(str, Enum):
    """Marcas de pizzarias suportadas no concelho de Lisboa."""

    DOMINOS = "DOMINOS"
    PIZZA_HUT = "PIZZA_HUT"
    TELEPIZZA = "TELEPIZZA"
    PAPA_JOHNS = "PAPA_JOHNS"


class DispatchMethod(str, Enum):
    """Canais e modalidades de atendimento."""

    DELIVERY = "DELIVERY"
    TAKE_AWAY = "TAKE_AWAY"
    DINE_IN = "DINE_IN"


class DiscountType(str, Enum):
    """Categorias estruturadas de promoção."""

    FIXED_PRICE = "FIXED_PRICE"
    PERCENTAGE = "PERCENTAGE"
    X_FOR_Y = "X_FOR_Y"
    SPECIAL_MENU = "SPECIAL_MENU"
    CUSTOM = "CUSTOM"


class TargetAudience(str, Enum):
    """Público-alvo / dimensão da refeição."""

    INDIVIDUAL = "INDIVIDUAL"
    GROUP_FAMILY = "GROUP_FAMILY"
    ALL = "ALL"


class Weekday(str, Enum):
    """Dias da semana para promoções com dias fixos."""

    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"


@dataclass(slots=True)
class UnifiedPromo:
    """Modelo canónico unificado de promoção de pizza no concelho de Lisboa.

    Todos os adaptadores devem converter os dados brutos de cada vendedor
    para instâncias deste modelo determinístico.
    """

    id: str
    vendor: Brand
    title: str
    description: str
    price: float | None = None
    original_price: float | None = None
    discount_percentage: float | None = None
    discount_type: DiscountType = DiscountType.CUSTOM
    conditions: str = ""
    valid_from: str | None = None
    valid_until: str | None = None
    days_of_week: list[Weekday] = field(default_factory=list)
    dispatch_methods: list[DispatchMethod] = field(
        default_factory=lambda: [DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY]
    )
    target_audience: TargetAudience = TargetAudience.ALL
    image_url: str | None = None
    source_url: str = ""
    scraped_at: str = ""
    location_scope: str = "Lisboa"

    def __post_init__(self) -> None:
        """Assegura tipos corretos de enums caso sejam passados como strings."""
        if isinstance(self.vendor, str) and not isinstance(self.vendor, Brand):
            self.vendor = Brand(self.vendor)
        if isinstance(self.discount_type, str) and not isinstance(self.discount_type, DiscountType):
            self.discount_type = DiscountType(self.discount_type)
        if isinstance(self.target_audience, str) and not isinstance(self.target_audience, TargetAudience):
            self.target_audience = TargetAudience(self.target_audience)

        if self.days_of_week:
            self.days_of_week = [
                Weekday(d) if isinstance(d, str) and not isinstance(d, Weekday) else d
                for d in self.days_of_week
            ]
        if self.dispatch_methods:
            self.dispatch_methods = [
                DispatchMethod(m) if isinstance(m, str) and not isinstance(m, DispatchMethod) else m
                for m in self.dispatch_methods
            ]

    @property
    def savings_amount(self) -> float | None:
        """Calcula o valor nominal poupado quando ambos os preços estão definidos."""
        if self.price is not None and self.original_price is not None:
            if self.original_price >= self.price:
                return round(self.original_price - self.price, 2)
        return None

    @property
    def computed_discount_percentage(self) -> float | None:
        """Calcula a percentagem de desconto efetiva com base nos preços."""
        if self.discount_percentage is not None:
            return round(self.discount_percentage, 1)
        if (
            self.price is not None
            and self.original_price is not None
            and self.original_price > 0
            and self.original_price >= self.price
        ):
            diff = self.original_price - self.price
            return round((diff / self.original_price) * 100.0, 1)
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serializa a promoção para um dicionário com valores primitivos."""
        data = asdict(self)
        data["vendor"] = self.vendor.value
        data["discount_type"] = self.discount_type.value
        data["target_audience"] = self.target_audience.value
        data["days_of_week"] = [d.value for d in self.days_of_week]
        data["dispatch_methods"] = [m.value for m in self.dispatch_methods]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnifiedPromo:
        """Cria uma instância de UnifiedPromo a partir de um dicionário."""
        data_copy = dict(data)
        if "vendor" in data_copy and isinstance(data_copy["vendor"], str):
            data_copy["vendor"] = Brand(data_copy["vendor"])
        if "discount_type" in data_copy and isinstance(data_copy["discount_type"], str):
            data_copy["discount_type"] = DiscountType(data_copy["discount_type"])
        if "target_audience" in data_copy and isinstance(data_copy["target_audience"], str):
            data_copy["target_audience"] = TargetAudience(data_copy["target_audience"])
        if "days_of_week" in data_copy and data_copy["days_of_week"]:
            data_copy["days_of_week"] = [
                Weekday(d) if isinstance(d, str) else d for d in data_copy["days_of_week"]
            ]
        if "dispatch_methods" in data_copy and data_copy["dispatch_methods"]:
            data_copy["dispatch_methods"] = [
                DispatchMethod(m) if isinstance(m, str) else m for m in data_copy["dispatch_methods"]
            ]
        return cls(**data_copy)

    def to_json(self, indent: int | None = None) -> str:
        """Serializa a promoção para string JSON."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> UnifiedPromo:
        """Desserializa uma string JSON para UnifiedPromo."""
        data = json.loads(json_str)
        return cls.from_dict(data)
