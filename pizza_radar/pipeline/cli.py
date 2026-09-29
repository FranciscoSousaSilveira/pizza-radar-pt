"""Ponto de entrada CLI para execução da pipeline de sincronização.

Uso:
    # Modo agendado/produção contra Turso (padrão):
    TURSO_DATABASE_URL="libsql://..." TURSO_AUTH_TOKEN="..." python -m pizza_radar.pipeline.cli --snapshot-output ./web/data/promotions.json

    # Modo local offline (desenvolvimento/testes):
    python -m pizza_radar.pipeline.cli --local --db-path ./pizza_radar.db
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from pizza_radar.adapters.dominos import DominosAdapter
from pizza_radar.adapters.papa_johns import PapaJohnsAdapter
from pizza_radar.adapters.pizza_hut import PizzaHutAdapter
from pizza_radar.adapters.telepizza import TelepizzaAdapter
from pizza_radar.persistence.repository import (
    PromotionRepository,
    SQLitePromotionRepository,
    TursoPromotionRepository,
)
from pizza_radar.pipeline.runner import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pizza_radar.cli")


def build_repository(args: argparse.Namespace) -> tuple[PromotionRepository, str] | tuple[None, str]:
    """Constrói o repositório adequado segundo o modo de execução.

    Regra arquitetural estrita:
    - Modo local explícito (--local, --mode local, --db-engine sqlite): utiliza SQLitePromotionRepository.
    - Modo agendado/produção (padrão): exige TURSO_DATABASE_URL e TURSO_AUTH_TOKEN e utiliza TursoPromotionRepository.
      Se ausentes ou falhar conexão, NÃO faz fallback para SQLite.
    """
    is_local = args.local or (args.mode == "local") or (args.db_engine == "sqlite")

    if is_local:
        logger.info("Modo LOCAL offline selecionado: a utilizar SQLitePromotionRepository (%s)...", args.db_path)
        return SQLitePromotionRepository(db_path=args.db_path), "demo"

    # Modo agendado / produção contra Turso remoto
    logger.info("Modo SCHEDULED/PRODUÇÃO selecionado: a validar credenciais do Turso...")
    db_url = args.database_url or os.environ.get("TURSO_DATABASE_URL")
    auth_token = args.auth_token or os.environ.get("TURSO_AUTH_TOKEN")

    if not db_url or not auth_token:
        logger.error(
            "ERRO CRÍTICO: Credenciais do Turso ausentes. TURSO_DATABASE_URL e TURSO_AUTH_TOKEN são "
            "obrigatórios em modo agendado/produção. Fallback para SQLite é estritamente proibido."
        )
        return None, ""

    try:
        repo = TursoPromotionRepository(database_url=db_url, auth_token=auth_token)
        return repo, "live"
    except Exception as e:
        logger.error(
            "ERRO CRÍTICO: Falha ao ligar à base de dados Turso (%s): %s. "
            "Operação abortada sem geração de snapshot e sem deploy.",
            db_url,
            e,
        )
        return None, ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executa a pipeline determinística do Pizza Radar PT.")
    parser.add_argument(
        "--mode",
        choices=["scheduled", "local"],
        default="scheduled",
        help="Modo de execução: 'scheduled' (produção via Turso) ou 'local' (offline via SQLite). Padrão: scheduled.",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Atalho para modo local offline utilizando SQLitePromotionRepository.",
    )
    parser.add_argument(
        "--db-engine",
        choices=["turso", "sqlite"],
        default="turso",
        help="Motor de base de dados: 'turso' (padrão) ou 'sqlite' (modo local).",
    )
    parser.add_argument(
        "--db-path",
        default="pizza_radar.db",
        help="Caminho para o ficheiro SQLite (utilizado exclusivamente em modo local). Padrão: pizza_radar.db.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL do endpoint libSQL/Turso (padrão: obtido via variável TURSO_DATABASE_URL).",
    )
    parser.add_argument(
        "--auth-token",
        default=None,
        help="Token de autenticação do Turso (padrão: obtido via variável TURSO_AUTH_TOKEN).",
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
    args = parser.parse_args(argv)

    repo, data_mode = build_repository(args)
    if repo is None:
        return 1

    adapters = [
        PapaJohnsAdapter(),
        DominosAdapter(),
        TelepizzaAdapter(),
        PizzaHutAdapter(),
    ]

    logger.info("A executar pipeline para %d adaptadores (data_mode=%s)...", len(adapters), data_mode)
    result = run_pipeline(
        repo=repo,
        adapters=adapters,
        snapshot_output_path=args.snapshot_output,
        location_scope=args.location_scope,
        data_mode=data_mode,
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
        logger.info("Snapshot exportado para: %s (data_mode=%s)", result.snapshot_path, data_mode)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
