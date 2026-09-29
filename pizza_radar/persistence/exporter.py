"""Exportação determinística do snapshot canónico promotions.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pizza_radar.core.models import Brand, OfferType
from pizza_radar.engine.identity import VisualPromoGroup, group_promos_for_visual_presentation
from pizza_radar.persistence.repository import PromotionRepository


def serialize_visual_group(group: VisualPromoGroup) -> dict[str, Any]:
    """Serializa um VisualPromoGroup para dicionário primitivo conforme contrato canónico."""
    group_offer_type = group.offer_type.value if hasattr(group.offer_type, "value") else str(group.offer_type)
    return {
        "persistent_id": group.persistent_id,
        "vendor": group.vendor.value,
        "title": group.title,
        "description": group.description,
        "offer_type": group_offer_type,
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
                "offer_type": v.offer_type.value if hasattr(v.offer_type, "value") else str(v.offer_type),
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
    """Gera a estrutura de dados do snapshot a partir da base de dados com transparência de estado e isolamento pizza-only."""
    now_dt = generated_at or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    active_promos = repo.get_active_promotions(location_scope=location_scope)
    groups = group_promos_for_visual_presentation(active_promos)

    serialized_groups = [serialize_visual_group(g) for g in groups]

    # Calcular estatísticas isoladas de pizza (exclui categoricamente NON_PIZZA e UNKNOWN)
    pizza_groups = [
        g for g in groups
        if getattr(g, "offer_type", None) in (OfferType.PIZZA, OfferType.BUNDLE_WITH_PIZZA)
    ]
    comparable_pizza_groups = [g for g in pizza_groups if g.is_comparable_for_unit_price]
    pizza_min_prices = [g.min_price_cents for g in pizza_groups if g.min_price_cents is not None]
    pizza_unit_prices = [
        g.min_price_per_pizza_cents for g in pizza_groups
        if g.min_price_per_pizza_cents is not None
    ]

    stats = {
        "total_groups": len(groups),
        "total_offers": len(active_promos),
        "total_pizza_groups": len(pizza_groups),
        "total_non_pizza_groups": len([g for g in groups if getattr(g, "offer_type", None) == OfferType.NON_PIZZA]),
        "comparable_groups": len(comparable_pizza_groups),
        "min_price_cents": min(pizza_min_prices) if pizza_min_prices else None,
        "cheapest_pizza_cents": min(pizza_unit_prices) if pizza_unit_prices else None,
    }

    active_vendors = sorted({g.vendor.value for g in groups})

    # Construir estado transparente por vendedor
    vendor_status: dict[str, dict[str, Any]] = {}
    known_brands = (Brand.DOMINOS, Brand.PAPA_JOHNS, Brand.PIZZA_HUT, Brand.TELEPIZZA)

    for brand in known_brands:
        runs = repo.get_vendor_sync_runs(vendor=brand, limit=1)
        brand_active = [p for p in active_promos if p.vendor == brand]
        count = len(brand_active)

        if runs:
            latest_run = runs[0]
            run_status = latest_run.get("status")
            last_attempt = latest_run.get("executed_at")

            if run_status == "SUCCESS":
                status = "SUCCESS"
                message = f"Atualizado ({count} ofertas ativas)"
                last_success = last_attempt
            else:
                if count > 0:
                    status = "STALE"
                    message = f"Recolha recente falhou; a exibir {count} ofertas anteriores preservadas"
                else:
                    status = "FAILED"
                    message = "Temporariamente indisponível — sem ofertas registadas"
                # Procurar última execução bem sucedida
                recent_runs = repo.get_vendor_sync_runs(vendor=brand, limit=10)
                success_runs = [r for r in recent_runs if r.get("status") == "SUCCESS"]
                last_success = success_runs[0].get("executed_at") if success_runs else None
        else:
            if count > 0:
                status = "STALE"
                message = f"{count} ofertas registadas"
            else:
                status = "PENDING"
                message = "A aguardar primeira recolha"
            last_success = None
            last_attempt = None

        vendor_status[brand.value] = {
            "vendor": brand.value,
            "status": status,
            "message": message,
            "active_offers_count": count,
            "last_success_at": last_success,
            "last_attempt_at": last_attempt,
        }

    successful_vendors_count = sum(1 for v in vendor_status.values() if v["status"] == "SUCCESS")

    return {
        "schema_version": "1.0.0",
        "data_mode": data_mode,
        "generated_at": now_dt.isoformat(),
        "location_scope": location_scope,
        "vendors_active": active_vendors,
        "vendors_updated_count": successful_vendors_count,
        "total_vendors_configured": len(known_brands),
        "vendor_status": vendor_status,
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
