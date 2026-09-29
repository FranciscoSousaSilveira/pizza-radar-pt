"""Modelos de dados canónicos para o Pizza Radar PT.

Implementa um contrato tipado, determinístico e auditável:
- Preços em cêntimos inteiros (integer cents), prevenindo erros de arredondamento IEEE-754.
- Aplicabilidade geográfica explícita (StoreScope, IDs/nomes de lojas, sem presunções universais).
- Composição detalhada da oferta (pizzas, tamanhos, itens incluídos, flag de comparabilidade estrita).
- Temporalidade timezone-aware (observed_at obrigatório, distinção de validade da marca, suporte a expiração).
"""

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


class StoreScope(str, Enum):
    """Âmbito de aplicabilidade geográfica da oferta."""

    NATIONAL = "NATIONAL"
    SPECIFIC_STORES = "SPECIFIC_STORES"
    UNKNOWN = "UNKNOWN"


class PizzaSize(str, Enum):
    """Tamanhos padronizados de pizza."""

    INDIVIDUAL = "INDIVIDUAL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"
    FAMILY = "FAMILY"
    UNKNOWN = "UNKNOWN"


class ComponentCategory(str, Enum):
    """Categorias de itens integrados numa oferta promocional."""

    PIZZA = "PIZZA"
    DRINK = "DRINK"
    SIDE = "SIDE"
    DESSERT = "DESSERT"
    OTHER = "OTHER"


class OfferType(str, Enum):
    """Classificação determinística da natureza do produto na oferta."""

    PIZZA = "PIZZA"
    BUNDLE_WITH_PIZZA = "BUNDLE_WITH_PIZZA"
    NON_PIZZA = "NON_PIZZA"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class OfferComponent:
    """Componente individual incluído numa oferta ou menu."""

    category: ComponentCategory = ComponentCategory.OTHER
    quantity: int = 1
    description: str = ""
    size: PizzaSize = PizzaSize.UNKNOWN

    def __post_init__(self) -> None:
        if isinstance(self.category, str) and not isinstance(self.category, ComponentCategory):
            self.category = ComponentCategory(self.category)
        if isinstance(self.size, str) and not isinstance(self.size, PizzaSize):
            self.size = PizzaSize(self.size)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "quantity": self.quantity,
            "description": self.description,
            "size": self.size.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OfferComponent:
        return cls(
            category=ComponentCategory(data.get("category", ComponentCategory.OTHER.value)),
            quantity=int(data.get("quantity", 1)),
            description=str(data.get("description", "")),
            size=PizzaSize(data.get("size", PizzaSize.UNKNOWN.value)),
        )


@dataclass(slots=True)
class UnifiedPromo:
    """Modelo canónico unificado de promoção de pizza no concelho de Lisboa.

    Invariantes e Princípios de Engenharia:
    1. Preços em cêntimos inteiros (integer cents): price_cents e original_price_cents.
    2. Sem presunção de disponibilidade universal: store_scope define se é nacional, de lojas específicas ou desconhecida.
    3. Conteúdo sem dados inventados: pizza_count e pizza_size apenas presentes quando explicitados pela marca.
    4. Temporalidade timezone-aware: observed_at é obrigatório com indicação explícita de fuso horário.
    """

    id: str
    vendor: Brand
    title: str
    description: str
    observed_at: str  # ISO 8601 com timezone (ex.: '2026-09-28T16:00:00+01:00')
    price_cents: int | None = None
    original_price_cents: int | None = None
    discount_percentage: float | None = None
    discount_type: DiscountType = DiscountType.CUSTOM
    conditions: str = ""
    valid_from: str | None = None  # Validade anunciada pela marca
    valid_until: str | None = None  # Validade anunciada pela marca
    last_seen_at: str | None = None  # Última observação confirmada
    is_active: bool = True  # Suporte para expiração determinística
    days_of_week: list[Weekday] = field(default_factory=list)
    dispatch_methods: list[DispatchMethod] = field(
        default_factory=lambda: [DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY]
    )
    target_audience: TargetAudience = TargetAudience.ALL
    store_scope: StoreScope = StoreScope.UNKNOWN
    store_ids: list[str] = field(default_factory=list)
    store_names: list[str] = field(default_factory=list)
    pizza_count: int | None = None  # Apenas preenchido quando fornecido explicitamente pela fonte
    pizza_size: PizzaSize = PizzaSize.UNKNOWN
    included_items: list[OfferComponent] = field(default_factory=list)
    image_url: str | None = None
    source_url: str = ""
    location_scope: str = "Lisboa"
    offer_type: OfferType = OfferType.UNKNOWN

    def __post_init__(self) -> None:
        """Assegura conversão de strings para enums tipados e normalização."""
        if isinstance(self.vendor, str) and not isinstance(self.vendor, Brand):
            self.vendor = Brand(self.vendor)
        if isinstance(self.offer_type, str) and not isinstance(self.offer_type, OfferType):
            self.offer_type = OfferType(self.offer_type)
        if self.offer_type == OfferType.UNKNOWN:
            from pizza_radar.core.classifier import classify_offer_type
            self.offer_type = classify_offer_type(
                title=self.title,
                description=self.description,
                included_items=self.included_items,
                pizza_count=self.pizza_count,
            )
        if isinstance(self.discount_type, str) and not isinstance(self.discount_type, DiscountType):
            self.discount_type = DiscountType(self.discount_type)
        if isinstance(self.target_audience, str) and not isinstance(self.target_audience, TargetAudience):
            self.target_audience = TargetAudience(self.target_audience)
        if isinstance(self.store_scope, str) and not isinstance(self.store_scope, StoreScope):
            self.store_scope = StoreScope(self.store_scope)
        if isinstance(self.pizza_size, str) and not isinstance(self.pizza_size, PizzaSize):
            self.pizza_size = PizzaSize(self.pizza_size)

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
        if self.included_items:
            self.included_items = [
                OfferComponent.from_dict(item) if isinstance(item, dict) else item
                for item in self.included_items
            ]

    # --- Propriedades Monetárias Determinísticas ---

    @property
    def price_euros(self) -> float | None:
        """Valor promocional em euros para apresentação."""
        return round(self.price_cents / 100.0, 2) if self.price_cents is not None else None

    @property
    def original_price_euros(self) -> float | None:
        """Valor original de referência em euros para apresentação."""
        return round(self.original_price_cents / 100.0, 2) if self.original_price_cents is not None else None

    @property
    def savings_amount_cents(self) -> int | None:
        """Diferença nominal poupada em cêntimos inteiros."""
        if self.price_cents is not None and self.original_price_cents is not None:
            if self.original_price_cents >= self.price_cents:
                return self.original_price_cents - self.price_cents
        return None

    @property
    def savings_amount_euros(self) -> float | None:
        """Diferença nominal poupada em euros."""
        cents = self.savings_amount_cents
        return round(cents / 100.0, 2) if cents is not None else None

    @property
    def computed_discount_percentage(self) -> float | None:
        """Calcula a percentagem de desconto efetiva."""
        if self.discount_percentage is not None:
            return round(self.discount_percentage, 1)
        if (
            self.price_cents is not None
            and self.original_price_cents is not None
            and self.original_price_cents > 0
            and self.original_price_cents >= self.price_cents
        ):
            diff = self.original_price_cents - self.price_cents
            return round((diff / self.original_price_cents) * 100.0, 1)
        return None

    # --- Propriedades de Comparabilidade e Conteúdo ---

    @property
    def is_comparable_for_unit_price(self) -> bool:
        """Indica se a oferta possui dados suficientes para cálculo de preço por pizza.

        Nunca inventa nem estima pizzas: devolve True estritamente quando
        o preço e a contagem de pizzas estão explicitados na fonte.
        """
        return self.price_cents is not None and self.pizza_count is not None and self.pizza_count > 0

    @property
    def price_per_pizza_cents(self) -> int | None:
        """Calcula o preço inteiro em cêntimos por pizza (arredondado)."""
        if self.is_comparable_for_unit_price and self.price_cents is not None and self.pizza_count:
            return round(self.price_cents / self.pizza_count)
        return None

    @property
    def price_per_pizza_euros(self) -> float | None:
        """Preço em euros por pizza quando comparável."""
        cents = self.price_per_pizza_cents
        return round(cents / 100.0, 2) if cents is not None else None

    # --- Verificação de Elegibilidade de Loja ---

    def is_store_eligible(self, store_id: str) -> bool | None:
        """Verifica se uma loja de Lisboa é elegível para a oferta.

        Returns:
            True se garantidamente elegível (campanha nacional ou loja na lista).
            False se garantidamente não elegível (loja ausente na lista de lojas específicas).
            None se a aplicabilidade for desconhecida (não deve presumir elegibilidade).
        """
        if self.store_scope == StoreScope.NATIONAL:
            return True
        if self.store_scope == StoreScope.SPECIFIC_STORES:
            return str(store_id) in self.store_ids
        return None

    # --- Serialização Determinística ---

    def to_dict(self) -> dict[str, Any]:
        """Serializa a promoção para dicionário com tipos primitivos."""
        data = asdict(self)
        data["vendor"] = self.vendor.value
        data["discount_type"] = self.discount_type.value
        data["target_audience"] = self.target_audience.value
        data["store_scope"] = self.store_scope.value
        data["pizza_size"] = self.pizza_size.value
        data["offer_type"] = self.offer_type.value
        data["days_of_week"] = [d.value for d in self.days_of_week]
        data["dispatch_methods"] = [m.value for m in self.dispatch_methods]
        data["included_items"] = [item.to_dict() for item in self.included_items]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnifiedPromo:
        """Desserializa um dicionário para UnifiedPromo com validação de tipos."""
        data_copy = dict(data)
        if "vendor" in data_copy and isinstance(data_copy["vendor"], str):
            data_copy["vendor"] = Brand(data_copy["vendor"])
        if "offer_type" in data_copy and isinstance(data_copy["offer_type"], str):
            data_copy["offer_type"] = OfferType(data_copy["offer_type"])
        if "discount_type" in data_copy and isinstance(data_copy["discount_type"], str):
            data_copy["discount_type"] = DiscountType(data_copy["discount_type"])
        if "target_audience" in data_copy and isinstance(data_copy["target_audience"], str):
            data_copy["target_audience"] = TargetAudience(data_copy["target_audience"])
        if "store_scope" in data_copy and isinstance(data_copy["store_scope"], str):
            data_copy["store_scope"] = StoreScope(data_copy["store_scope"])
        if "pizza_size" in data_copy and isinstance(data_copy["pizza_size"], str):
            data_copy["pizza_size"] = PizzaSize(data_copy["pizza_size"])
        if "days_of_week" in data_copy and data_copy["days_of_week"]:
            data_copy["days_of_week"] = [
                Weekday(d) if isinstance(d, str) else d for d in data_copy["days_of_week"]
            ]
        if "dispatch_methods" in data_copy and data_copy["dispatch_methods"]:
            data_copy["dispatch_methods"] = [
                DispatchMethod(m) if isinstance(m, str) else m for m in data_copy["dispatch_methods"]
            ]
        if "included_items" in data_copy and data_copy["included_items"]:
            data_copy["included_items"] = [
                OfferComponent.from_dict(item) if isinstance(item, dict) else item
                for item in data_copy["included_items"]
            ]
        return cls(**data_copy)

    def to_json(self, indent: int | None = None) -> str:
        """Serializa para JSON de forma determinística."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> UnifiedPromo:
        """Desserializa de JSON para UnifiedPromo."""
        return cls.from_dict(json.loads(json_str))
