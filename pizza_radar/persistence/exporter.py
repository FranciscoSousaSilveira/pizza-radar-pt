"""Exportação determinística do snapshot canónico promotions.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pizza_radar.engine.identity import VisualPromoGroup, group_promos_for_visual_presentation
from pizza_radar.persistence.repository import PromotionRepository


def serialize_visual_group(group: VisualPromoGroup) -> dict[str, Any]:
    """Serializa um VisualPromoGroup para dicionário primitivo conforme contrato canónico."""
    return {
        "persistent_id": group.persistent_id,
        "vendor": group.vendor.value,
        "title": group.title,
        "description": group.description,
        "dispatch_methods": [m.value for m in group.dispatch_methods],
        "store_scope": group.store_scope.value,
        "all_store_ids": sorted(group.all_store_ids),
        "all_store_names": group.all_store_names,
        "display_price_label": group.display_price_label,
        "min_price_cents": group.min_price_cents,
        "max_price_cents": group.max_price_cents,
        "min_price_euros": group.min_price_euros,
        "max_price_euros": group.max_price_euros,
        "min_price_per_pizza_cents": group.min_price_per_pizza_cents,
        "min_price_per_pizza_euros": group.min_price_per_pizza_euros,
        "max_discount_percentage": group.max_discount_percentage,
        "pizza_count": group.pizza_count,
        "pizza_size": group.pizza_size.value,
        "is_comparable_for_unit_price": group.is_comparable_for_unit_price,
        "has_uniform_price": group.has_uniform_price,
        "image_url": group.image_url,
        "source_url": group.source_url,
        "days_of_week": [d.value for d in group.days_of_week],
        "location_scope": group.location_scope,
        "most_recent_observed_at": group.most_recent_observed_at,
        "variants": [
            {
                "variant_id": v.variant_id,
                "persistent_id": v.persistent_id,
                "store_ids": sorted(v.store_ids),
                "store_names": v.store_names,
                "price_cents": v.price_cents,
                "price_euros": v.price_euros,
                "original_price_cents": v.original_price_cents,
                "original_price_euros": v.original_price_euros,
                "computed_discount_percentage": v.computed_discount_percentage,
                "pizza_count": v.pizza_count,
                "pizza_size": v.pizza_size.value,
                "is_comparable_for_unit_price": v.is_comparable_for_unit_price,
                "price_per_pizza_cents": v.price_per_pizza_cents,
                "conditions": v.conditions,
                "valid_from": v.valid_from,
                "valid_until": v.valid_until,
                "observed_at": v.observed_at,
            }
            for v in group.variants
        ],
    }


def generate_snapshot_dict(
    repo: PromotionRepository,
    location_scope: str = "Lisboa",
    generated_at: datetime | None = None,
    data_mode: str = "live",
) -> dict[str, Any]:
    """Gera a estrutura de dados do snapshot a partir da base de dados."""
    now_dt = generated_at or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    active_promos = repo.get_active_promotions(location_scope=location_scope)
    groups = group_promos_for_visual_presentation(active_promos)

    serialized_groups = [serialize_visual_group(g) for g in groups]

    # Calcular estatísticas globais
    comparable_groups = [g for g in groups if g.is_comparable_for_unit_price]
    all_min_prices = [g.min_price_cents for g in groups if g.min_price_cents is not None]
    all_unit_prices = [
        g.min_price_per_pizza_cents for g in groups
        if g.min_price_per_pizza_cents is not None
    ]

    stats = {
        "total_groups": len(groups),
        "total_offers": len(active_promos),
        "comparable_groups": len(comparable_groups),
        "min_price_cents": min(all_min_prices) if all_min_prices else None,
        "cheapest_pizza_cents": min(all_unit_prices) if all_unit_prices else None,
    }

    active_vendors = sorted({g.vendor.value for g in groups})

    return {
        "schema_version": "1.0.0",
        "data_mode": data_mode,
        "generated_at": now_dt.isoformat(),
        "location_scope": location_scope,
        "vendors_active": active_vendors,
        "stats": stats,
        "groups": serialized_groups,
    }


def export_snapshot(
    repo: PromotionRepository,
    output_path: str | Path,
    location_scope: str = "Lisboa",
    generated_at: datetime | None = None,
    data_mode: str = "live",
) -> dict[str, Any]:
    """Exporta o snapshot determinístico para ficheiro JSON."""
    snapshot = generate_snapshot_dict(
        repo,
        location_scope=location_scope,
        generated_at=generated_at,
        data_mode=data_mode,
    )
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    return snapshot
