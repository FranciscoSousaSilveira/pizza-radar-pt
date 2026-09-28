"""Ponto de entrada CLI para execução da pipeline de sincronização.

Uso:
    python -m pizza_radar.pipeline.cli [--db-path CAMINHO] [--snapshot-output CAMINHO]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pizza_radar.adapters.dominos import DominosAdapter
from pizza_radar.adapters.papa_johns import PapaJohnsAdapter
from pizza_radar.adapters.pizza_hut import PizzaHutAdapter
from pizza_radar.adapters.telepizza import TelepizzaAdapter
from pizza_radar.persistence.repository import SQLitePromotionRepository
from pizza_radar.pipeline.runner import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pizza_radar.cli")


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa a pipeline determinística do Pizza Radar PT.")
    parser.add_argument(
        "--db-path",
        default="pizza_radar.db",
        help="Caminho para o ficheiro SQLite/libSQL (padrão: pizza_radar.db).",
    )
    parser.add_argument(
        "--snapshot-output",
        default=None,
        help="Caminho para onde exportar o snapshot promotions.json (opcional).",
    )
    parser.add_argument(
        "--location-scope",
        default="Lisboa",
        help="Concelho de cobertura (padrão: Lisboa).",
    )
    args = parser.parse_args()

    logger.info("A inicializar repositório em %s...", args.db_path)
    repo = SQLitePromotionRepository(db_path=args.db_path)

    adapters = [
        PapaJohnsAdapter(),
        DominosAdapter(),
        TelepizzaAdapter(),
        PizzaHutAdapter(),
    ]

    logger.info("A executar pipeline para %d adaptadores...", len(adapters))
    result = run_pipeline(
        repo=repo,
        adapters=adapters,
        snapshot_output_path=args.snapshot_output,
        location_scope=args.location_scope,
    )

    logger.info("Resultado da pipeline: success=%s", result.success)
    for vendor, status in result.vendor_results.items():
        logger.info(
            " - %s: status=%s, ofertas=%d, erro=%s",
            vendor,
            status.status,
            status.offers_found,
            status.error_message,
        )

    logger.info("Total de promoções ativas na base de dados: %d", result.total_active_promotions)
    if result.snapshot_exported:
        logger.info("Snapshot exportado para: %s", result.snapshot_path)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
