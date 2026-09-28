"""Orquestrador determinístico de sincronização e exportação de dados.

Garante:
1. Isolamento estrito de falhas por operador: a falha de um adaptador NUNCA
   remove nem desativa as suas promoções pré-existentes.
2. Atualização condicional de ausências: `consecutive_misses` só é incrementado
   após uma sincronização comprovadamente bem-sucedida do respetivo vendedor.
3. Exportação atómica e determinística do snapshot `promotions.json`.
4. Abortamento seguro: em caso de falha da base de dados, a publicação é abortada,
   preservando o snapshot íntegro anterior na CDN.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pizza_radar.core.adapter import PromoAdapterInterface
from pizza_radar.core.models import Brand
from pizza_radar.persistence.exporter import export_snapshot
from pizza_radar.persistence.repository import PromotionRepository, SyncStats

logger = logging.getLogger("pizza_radar.pipeline")


@dataclass(slots=True)
class VendorSyncStatus:
    """Resultado da execução de um adaptador específico."""

    vendor: Brand
    status: str  # "SUCCESS" | "FAILED"
    offers_found: int = 0
    error_message: str | None = None
    stats: SyncStats | None = None


@dataclass(slots=True)
class PipelineResult:
    """Resultado consolidado da execução da pipeline."""

    success: bool
    sync_time: str
    vendor_results: dict[str, VendorSyncStatus] = field(default_factory=dict)
    expired_by_date: int = 0
    total_active_promotions: int = 0
    snapshot_exported: bool = False
    snapshot_path: str | None = None
    error_message: str | None = None


def run_pipeline(
    repo: PromotionRepository,
    adapters: Sequence[PromoAdapterInterface],
    snapshot_output_path: str | Path | None = None,
    sync_time: datetime | None = None,
    max_consecutive_misses: int = 2,
    location_scope: str = "Lisboa",
    data_mode: str = "live",
) -> PipelineResult:
    """Executa a sincronização coordenada dos adaptadores e gera o snapshot.

    Args:
        repo: Instância de PromotionRepository (ex.: TursoPromotionRepository ou SQLitePromotionRepository).
        adapters: Lista de adaptadores a executar (um por marca).
        snapshot_output_path: Caminho de destino para promotions.json (opcional).
        sync_time: Instante da sincronização (timezone-aware).
        max_consecutive_misses: Limiar de ausências para desativação (padrão: 2).
        location_scope: Âmbito geográfico (padrão: "Lisboa").
        data_mode: Modo de dados do snapshot ("live" em produção, "demo" em local).

    Returns:
        PipelineResult estruturado com detalhes por vendedor e estado do snapshot.
    """
    now = sync_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_iso = now.isoformat()

    vendor_results: dict[str, VendorSyncStatus] = {}
    any_success = False

    for adapter in adapters:
        vendor_name = adapter.vendor.value
        try:
            logger.info("A iniciar recolha para o vendedor %s...", vendor_name)
            promos = adapter.fetch_promotions()
            offers_count = len(promos)

            # Persistir lote na base de dados
            stats = repo.upsert_promotions(
                promos=promos,
                vendor=adapter.vendor,
                sync_time=now,
                max_consecutive_misses=max_consecutive_misses,
            )

            # Registar execução com sucesso
            repo.record_vendor_sync_run(
                vendor=adapter.vendor,
                status="SUCCESS",
                offers_found=offers_count,
                executed_at=now,
            )

            vendor_results[vendor_name] = VendorSyncStatus(
                vendor=adapter.vendor,
                status="SUCCESS",
                offers_found=offers_count,
                stats=stats,
            )
            any_success = True
            logger.info(
                "Vendedor %s concluído: %d ofertas recolhidas (%d criadas, %d atualizadas).",
                vendor_name,
                offers_count,
                stats.created,
                stats.updated,
            )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error("Falha na sincronização do vendedor %s: %s", vendor_name, error_msg)

            # Tentar registar a falha na auditoria da BD (se acessível)
            try:
                repo.record_vendor_sync_run(
                    vendor=adapter.vendor,
                    status="FAILED",
                    error_message=error_msg,
                    executed_at=now,
                )
            except Exception as db_err:
                logger.warning("Não foi possível registar falha de sync na BD: %s", db_err)

            # Importante: o estado existente deste operador NÃO é modificado
            vendor_results[vendor_name] = VendorSyncStatus(
                vendor=adapter.vendor,
                status="FAILED",
                offers_found=0,
                error_message=error_msg,
            )

    # Desativar ofertas com valid_until ultrapassada
    expired_by_date = 0
    try:
        expired_by_date = repo.expire_outdated_promotions(reference_time=now)
    except Exception as e:
        logger.warning("Falha ao expirar promoções por data: %s", e)

    # Obter total de promoções ativas consolidadas
    try:
        active_promos = repo.get_active_promotions(location_scope=location_scope)
        total_active = len(active_promos)
    except Exception as e:
        logger.error("Erro crítico ao consultar promoções ativas na base de dados: %s", e)
        return PipelineResult(
            success=False,
            sync_time=now_iso,
            vendor_results=vendor_results,
            expired_by_date=expired_by_date,
            total_active_promotions=0,
            snapshot_exported=False,
            error_message=f"Falha na base de dados ao consultar ativas: {e}",
        )

    # Exportar snapshot JSON se o caminho de destino for fornecido
    snapshot_exported = False
    snapshot_path_str: str | None = None
    if snapshot_output_path is not None:
        try:
            export_snapshot(
                repo=repo,
                output_path=snapshot_output_path,
                location_scope=location_scope,
                generated_at=now,
                data_mode=data_mode,
            )
            snapshot_exported = True
            snapshot_path_str = str(snapshot_output_path)
            logger.info("Snapshot canónico exportado com sucesso para %s", snapshot_output_path)
        except Exception as e:
            logger.error("Falha ao exportar snapshot JSON: %s", e)
            return PipelineResult(
                success=False,
                sync_time=now_iso,
                vendor_results=vendor_results,
                expired_by_date=expired_by_date,
                total_active_promotions=total_active,
                snapshot_exported=False,
                error_message=f"Falha ao exportar snapshot: {e}",
            )

    return PipelineResult(
        success=True,
        sync_time=now_iso,
        vendor_results=vendor_results,
        expired_by_date=expired_by_date,
        total_active_promotions=total_active,
        snapshot_exported=snapshot_exported,
        snapshot_path=snapshot_path_str,
    )
