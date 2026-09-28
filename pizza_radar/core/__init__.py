"""Core models, interfaces and validation for Pizza Radar PT."""

from pizza_radar.core.models import (
    Brand,
    ComponentCategory,
    DispatchMethod,
    DiscountType,
    OfferComponent,
    PizzaSize,
    StoreScope,
    TargetAudience,
    UnifiedPromo,
    Weekday,
)
from pizza_radar.core.validator import (
    ValidationError,
    validate_promo,
    validate_promos,
)
from pizza_radar.core.adapter import (
    AdapterError,
    NetworkError,
    ParseError,
    PromoAdapterInterface,
    RateLimitError,
)

__all__ = [
    "Brand",
    "ComponentCategory",
    "DispatchMethod",
    "DiscountType",
    "OfferComponent",
    "PizzaSize",
    "StoreScope",
    "TargetAudience",
    "Weekday",
    "UnifiedPromo",
    "ValidationError",
    "validate_promo",
    "validate_promos",
    "PromoAdapterInterface",
    "AdapterError",
    "NetworkError",
    "ParseError",
    "RateLimitError",
]
