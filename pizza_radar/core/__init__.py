"""Core models, interfaces and validation for Pizza Radar PT."""

from pizza_radar.core.models import (
    Brand,
    DispatchMethod,
    DiscountType,
    TargetAudience,
    Weekday,
    UnifiedPromo,
)
from pizza_radar.core.validator import (
    ValidationError,
    validate_promo,
    validate_promos,
)
from pizza_radar.core.adapter import (
    PromoAdapterInterface,
    AdapterError,
    NetworkError,
    ParseError,
)

__all__ = [
    "Brand",
    "DispatchMethod",
    "DiscountType",
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
]
