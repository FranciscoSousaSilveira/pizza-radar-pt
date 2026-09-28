"""Repositório de persistência relacional para promoções do Pizza Radar PT.

Implementa a abstração formal PromotionRepository e as implementações concretas:
- TursoPromotionRepository / LibSqlPromotionRepository: repositório de produção contra Turso / libSQL remoto;
- SQLitePromotionRepository: reservado EXCLUSIVAMENTE para testes e desenvolvimento local offline.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    PizzaSize,
    StoreScope,
    TargetAudience,
    UnifiedPromo,
    Weekday,
)


@dataclass(slots=True)
class SyncStats:
    """Estatísticas de uma operação de sincronização e upsert."""

    created: int = 0
    updated: int = 0
    price_changed: int = 0
    reactivated: int = 0
    unchanged: int = 0
    misses_incremented: int = 0
    deactivated_by_misses: int = 0
    expired_by_date: int = 0


@dataclass(slots=True)
class ObservationEntry:
    """Registo de auditoria de histórico de preços de uma promoção."""

    promotion_id: str
    observed_at: str
    price_cents: int | None
    original_price_cents: int | None
    is_available: bool


class PromotionRepository(ABC):
    """Interface abstrata de repositório para persistência de dados promocionais."""

    @abstractmethod
    def init_schema(self) -> None:
        """Inicializa as tabelas e índices da base de dados."""
        ...

    @abstractmethod
    def upsert_promotions(
        self,
        promos: list[UnifiedPromo],
        vendor: Brand,
        sync_time: datetime | None = None,
        max_consecutive_misses: int = 2,
    ) -> SyncStats:
        """Insere ou atualiza o lote de promoções recolhidas com sucesso de um vendedor."""
        ...

    @abstractmethod
    def get_active_promotions(self, location_scope: str = "Lisboa") -> list[UnifiedPromo]:
        """Recupera todas as promoções atualmente ativas para o concelho indicado."""
        ...

    @abstractmethod
    def get_promotion_by_id(self, promo_id: str) -> UnifiedPromo | None:
        """Recupera uma promoção por ID."""
        ...

    @abstractmethod
    def record_vendor_sync_run(
        self,
        vendor: Brand,
        status: str,
        offers_found: int = 0,
        error_message: str | None = None,
        executed_at: datetime | None = None,
    ) -> int:
        """Regista uma execução de sincronização de um vendedor."""
        ...

    @abstractmethod
    def get_vendor_sync_runs(
        self,
        vendor: Brand | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Recupera o histórico de execuções de sincronização."""
        ...

    @abstractmethod
    def record_history(self, entries: list[ObservationEntry]) -> None:
        """Regista entradas de auditoria no histórico de observações."""
        ...

    @abstractmethod
    def expire_outdated_promotions(
        self,
        reference_time: datetime | None = None,
    ) -> int:
        """Desativa promoções com data `valid_until` ultrapassada."""
        ...

    @abstractmethod
    def upsert_stores(self, stores: list[dict[str, Any]]) -> None:
        """Insere ou atualiza lojas de referência."""
        ...


class SQLitePromotionRepository(PromotionRepository):
    """Implementação concreta de PromotionRepository para uso EXCLUSIVO em testes e desenvolvimento local offline."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._connection: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            # Conexão persistente para base de dados em memória
            self._connection = sqlite3.connect(":memory:")
            self._connection.row_factory = sqlite3.Row
            self._enable_foreign_keys(self._connection)
        self.init_schema()

    def _enable_foreign_keys(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA foreign_keys = ON;")

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is not None:
            return self._connection
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self._enable_foreign_keys(conn)
        return conn

    def init_schema(self) -> None:
        conn = self._get_connection()
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            ddl = schema_path.read_text(encoding="utf-8")
        else:
            raise FileNotFoundError(f"Esquema SQL não encontrado em {schema_path}")

        with conn:
            conn.executescript(ddl)

    def upsert_stores(self, stores: list[dict[str, Any]]) -> None:
        if not stores:
            return
        conn = self._get_connection()
        sql = """
        INSERT INTO stores (store_id, vendor, name, postal_code, address, is_lisbon_municipality)
        VALUES (:store_id, :vendor, :name, :postal_code, :address, :is_lisbon_municipality)
        ON CONFLICT(store_id) DO UPDATE SET
            name = excluded.name,
            postal_code = excluded.postal_code,
            address = excluded.address,
            is_lisbon_municipality = excluded.is_lisbon_municipality;
        """
        with conn:
            for s in stores:
                conn.execute(sql, {
                    "store_id": str(s["store_id"]),
                    "vendor": s["vendor"].value if isinstance(s["vendor"], Brand) else str(s["vendor"]),
                    "name": str(s["name"]),
                    "postal_code": s.get("postal_code"),
                    "address": s.get("address"),
                    "is_lisbon_municipality": 1 if s.get("is_lisbon_municipality", True) else 0,
                })

    def record_vendor_sync_run(
        self,
        vendor: Brand,
        status: str,
        offers_found: int = 0,
        error_message: str | None = None,
        executed_at: datetime | None = None,
    ) -> int:
        conn = self._get_connection()
        ts = (executed_at or datetime.now(timezone.utc)).isoformat()
        vendor_str = vendor.value if isinstance(vendor, Brand) else str(vendor)
        sql = """
        INSERT INTO vendor_sync_runs (vendor, status, offers_found, error_message, executed_at)
        VALUES (?, ?, ?, ?, ?);
        """
        with conn:
            cursor = conn.execute(sql, (vendor_str, status, offers_found, error_message, ts))
            return cursor.lastrowid or 0

    def get_vendor_sync_runs(
        self,
        vendor: Brand | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        conn = self._get_connection()
        if vendor is not None:
            vendor_str = vendor.value if isinstance(vendor, Brand) else str(vendor)
            sql = "SELECT * FROM vendor_sync_runs WHERE vendor = ? ORDER BY id DESC LIMIT ?"
            rows = conn.execute(sql, (vendor_str, limit)).fetchall()
        else:
            sql = "SELECT * FROM vendor_sync_runs ORDER BY id DESC LIMIT ?"
            rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def record_history(self, entries: list[ObservationEntry]) -> None:
        if not entries:
            return
        conn = self._get_connection()
        sql = """
        INSERT INTO observation_history (promotion_id, observed_at, price_cents, original_price_cents, is_available)
        VALUES (?, ?, ?, ?, ?);
        """
        with conn:
            conn.executemany(sql, [
                (e.promotion_id, e.observed_at, e.price_cents, e.original_price_cents, 1 if e.is_available else 0)
                for e in entries
            ])

    def upsert_promotions(
        self,
        promos: list[UnifiedPromo],
        vendor: Brand,
        sync_time: datetime | None = None,
        max_consecutive_misses: int = 2,
    ) -> SyncStats:
        conn = self._get_connection()
        now_dt = sync_time or datetime.now(timezone.utc)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        now_iso = now_dt.isoformat()
        vendor_str = vendor.value if isinstance(vendor, Brand) else str(vendor)

        stats = SyncStats()

        with conn:
            # 1. Obter estado atual de todas as promoções deste vendedor na BD
            existing_rows = conn.execute(
                "SELECT id, price_cents, original_price_cents, is_active, consecutive_misses, observed_at FROM promotions WHERE vendor = ?",
                (vendor_str,),
            ).fetchall()
            existing_by_id = {row["id"]: row for row in existing_rows}

            seen_ids = set()
            history_entries: list[ObservationEntry] = []

            for promo in promos:
                pid = promo.id
                seen_ids.add(pid)
                payload_json = promo.to_json()

                if pid not in existing_by_id:
                    # Nova promoção
                    conn.execute(
                        """
                        INSERT INTO promotions (
                            id, vendor, title, description, price_cents, original_price_cents,
                            discount_percentage, discount_type, store_scope, pizza_count,
                            pizza_size, conditions, valid_from, valid_until, observed_at,
                            last_seen_at, consecutive_misses, is_active, location_scope,
                            source_url, image_url, raw_payload_json
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?, ?
                        );
                        """,
                        (
                            pid,
                            vendor_str,
                            promo.title,
                            promo.description,
                            promo.price_cents,
                            promo.original_price_cents,
                            promo.discount_percentage,
                            promo.discount_type.value,
                            promo.store_scope.value,
                            promo.pizza_count,
                            promo.pizza_size.value,
                            promo.conditions,
                            promo.valid_from,
                            promo.valid_until,
                            promo.observed_at or now_iso,
                            now_iso,
                            promo.location_scope,
                            promo.source_url,
                            promo.image_url,
                            payload_json,
                        ),
                    )
                    # Registar lojas associadas
                    for idx, sid in enumerate(promo.store_ids):
                        sname = promo.store_names[idx] if idx < len(promo.store_names) else f"Loja {sid}"
                        conn.execute(
                            "INSERT OR IGNORE INTO stores (store_id, vendor, name) VALUES (?, ?, ?);",
                            (str(sid), vendor_str, sname),
                        )
                        conn.execute(
                            "INSERT OR IGNORE INTO promotion_stores (promotion_id, store_id) VALUES (?, ?);",
                            (pid, str(sid)),
                        )
                    history_entries.append(
                        ObservationEntry(
                            promotion_id=pid,
                            observed_at=promo.observed_at or now_iso,
                            price_cents=promo.price_cents,
                            original_price_cents=promo.original_price_cents,
                            is_available=True,
                        )
                    )
                    stats.created += 1
                else:
                    # Promoção existente
                    old = existing_by_id[pid]
                    was_active = bool(old["is_active"])
                    old_price = old["price_cents"]
                    old_orig = old["original_price_cents"]
                    price_changed = (old_price != promo.price_cents) or (old_orig != promo.original_price_cents)

                    if price_changed:
                        stats.price_changed += 1
                        history_entries.append(
                            ObservationEntry(
                                promotion_id=pid,
                                observed_at=now_iso,
                                price_cents=promo.price_cents,
                                original_price_cents=promo.original_price_cents,
                                is_available=True,
                            )
                        )

                    if not was_active:
                        stats.reactivated += 1
                    elif not price_changed:
                        stats.unchanged += 1

                    stats.updated += 1

                    # Atualizar promoção preservando o carimbo observed_at original
                    conn.execute(
                        """
                        UPDATE promotions SET
                            title = ?,
                            description = ?,
                            price_cents = ?,
                            original_price_cents = ?,
                            discount_percentage = ?,
                            discount_type = ?,
                            store_scope = ?,
                            pizza_count = ?,
                            pizza_size = ?,
                            conditions = ?,
                            valid_from = ?,
                            valid_until = ?,
                            last_seen_at = ?,
                            consecutive_misses = 0,
                            is_active = 1,
                            location_scope = ?,
                            source_url = ?,
                            image_url = ?,
                            raw_payload_json = ?
                        WHERE id = ?;
                        """,
                        (
                            promo.title,
                            promo.description,
                            promo.price_cents,
                            promo.original_price_cents,
                            promo.discount_percentage,
                            promo.discount_type.value,
                            promo.store_scope.value,
                            promo.pizza_count,
                            promo.pizza_size.value,
                            promo.conditions,
                            promo.valid_from,
                            promo.valid_until,
                            now_iso,
                            promo.location_scope,
                            promo.source_url,
                            promo.image_url,
                            payload_json,
                            pid,
                        ),
                    )
                    # Sincronizar lojas
                    conn.execute("DELETE FROM promotion_stores WHERE promotion_id = ?;", (pid,))
                    for idx, sid in enumerate(promo.store_ids):
                        sname = promo.store_names[idx] if idx < len(promo.store_names) else f"Loja {sid}"
                        conn.execute(
                            "INSERT OR IGNORE INTO stores (store_id, vendor, name) VALUES (?, ?, ?);",
                            (str(sid), vendor_str, sname),
                        )
                        conn.execute(
                            "INSERT OR IGNORE INTO promotion_stores (promotion_id, store_id) VALUES (?, ?);",
                            (pid, str(sid)),
                        )

            # 2. Promoções deste vendedor que NÃO constavam do lote recolhido
            missing_promos = [
                row for pid, row in existing_by_id.items()
                if pid not in seen_ids and bool(row["is_active"])
            ]
            for row in missing_promos:
                pid = row["id"]
                new_misses = row["consecutive_misses"] + 1
                stats.misses_incremented += 1

                if new_misses >= max_consecutive_misses:
                    conn.execute(
                        "UPDATE promotions SET consecutive_misses = ?, is_active = 0, last_seen_at = ? WHERE id = ?;",
                        (new_misses, now_iso, pid),
                    )
                    stats.deactivated_by_misses += 1
                    history_entries.append(
                        ObservationEntry(
                            promotion_id=pid,
                            observed_at=now_iso,
                            price_cents=row["price_cents"],
                            original_price_cents=row["original_price_cents"],
                            is_available=False,
                        )
                    )
                else:
                    conn.execute(
                        "UPDATE promotions SET consecutive_misses = ? WHERE id = ?;",
                        (new_misses, pid),
                    )

            # 3. Gravar histórico em lote
            if history_entries:
                conn.executemany(
                    """
                    INSERT INTO observation_history (promotion_id, observed_at, price_cents, original_price_cents, is_available)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    [
                        (e.promotion_id, e.observed_at, e.price_cents, e.original_price_cents, 1 if e.is_available else 0)
                        for e in history_entries
                    ],
                )

        return stats

    def expire_outdated_promotions(
        self,
        reference_time: datetime | None = None,
    ) -> int:
        conn = self._get_connection()
        now_dt = reference_time or datetime.now(timezone.utc)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        now_iso = now_dt.isoformat()

        with conn:
            rows = conn.execute(
                "SELECT id, price_cents, original_price_cents FROM promotions WHERE is_active = 1 AND valid_until IS NOT NULL AND valid_until < ?;",
                (now_iso,),
            ).fetchall()
            if not rows:
                return 0

            expired_count = len(rows)
            conn.execute(
                "UPDATE promotions SET is_active = 0 WHERE is_active = 1 AND valid_until IS NOT NULL AND valid_until < ?;",
                (now_iso,),
            )
            conn.executemany(
                """
                INSERT INTO observation_history (promotion_id, observed_at, price_cents, original_price_cents, is_available)
                VALUES (?, ?, ?, ?, 0);
                """,
                [(r["id"], now_iso, r["price_cents"], r["original_price_cents"]) for r in rows],
            )
            return expired_count

    def get_promotion_by_id(self, promo_id: str) -> UnifiedPromo | None:
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM promotions WHERE id = ?;", (promo_id,)).fetchone()
        if not row:
            return None
        return self._row_to_unified_promo(row)

    def get_active_promotions(self, location_scope: str = "Lisboa") -> list[UnifiedPromo]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM promotions WHERE is_active = 1 AND location_scope = ? ORDER BY vendor, price_cents ASC;",
            (location_scope,),
        ).fetchall()
        return [self._row_to_unified_promo(r) for r in rows]

    def _row_to_unified_promo(self, row: sqlite3.Row) -> UnifiedPromo:
        return _dict_or_row_to_unified_promo(row)


def _to_hrana_val(v: Any) -> dict[str, Any]:
    """Converte valores primitivos de Python para tipos Hrana 2 / libSQL."""
    if v is None:
        return {"type": "null"}
    elif isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    elif isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    elif isinstance(v, float):
        return {"type": "float", "value": v}
    elif isinstance(v, (str, bytes)):
        return {"type": "text", "value": str(v)}
    return {"type": "text", "value": str(v)}


def _from_hrana_val(col: Any) -> Any:
    """Converte tipos Hrana 2 / libSQL para valores primitivos de Python."""
    if isinstance(col, dict):
        t = col.get("type")
        if t == "null":
            return None
        elif t == "integer":
            val_str = col.get("value", 0)
            return int(val_str)
        elif t == "float":
            return float(col.get("value", 0.0))
        elif t == "text":
            return col.get("value", "")
        elif t == "blob":
            return col.get("base64", "")
        return col.get("value")
    return col


def _dict_or_row_to_unified_promo(row: Any) -> UnifiedPromo:
    """Reconstrói um UnifiedPromo a partir de sqlite3.Row ou dicionário deserializado do Turso."""
    raw_json = row["raw_payload_json"]
    if raw_json:
        try:
            data = json.loads(raw_json)
            data["observed_at"] = row["observed_at"]
            data["last_seen_at"] = row["last_seen_at"]
            data["is_active"] = bool(row["is_active"])
            return UnifiedPromo.from_dict(data)
        except Exception:
            pass

    # Fallback reconstrução a partir das colunas relacionais
    return UnifiedPromo(
        id=row["id"],
        vendor=Brand(row["vendor"]),
        title=row["title"],
        description=row["description"] or "",
        observed_at=row["observed_at"],
        price_cents=row["price_cents"],
        original_price_cents=row["original_price_cents"],
        discount_percentage=row["discount_percentage"],
        discount_type=DiscountType(row["discount_type"]),
        store_scope=StoreScope(row["store_scope"]),
        pizza_count=row["pizza_count"],
        pizza_size=PizzaSize(row["pizza_size"]) if row["pizza_size"] else PizzaSize.UNKNOWN,
        conditions=row["conditions"] or "",
        valid_from=row["valid_from"],
        valid_until=row["valid_until"],
        last_seen_at=row["last_seen_at"],
        is_active=bool(row["is_active"]),
        source_url=row["source_url"] or "",
        image_url=row["image_url"],
        location_scope=row["location_scope"],
    )


class TursoPromotionRepository(PromotionRepository):
    """Implementação concreta de PromotionRepository para Turso / libSQL Serverless remoto.

    Executa operações transacionais via API de pipeline HTTP (/v2/pipeline) do libSQL,
    autenticadas por Bearer Token.
    """

    def __init__(self, database_url: str, auth_token: str, timeout: float = 30.0) -> None:
        if not database_url or not str(database_url).strip():
            raise ValueError("database_url é obrigatório para TursoPromotionRepository")
        if not auth_token or not str(auth_token).strip():
            raise ValueError("auth_token é obrigatório para TursoPromotionRepository")

        self.database_url = str(database_url).strip()
        self.auth_token = str(auth_token).strip()
        self.timeout = timeout

        url = self.database_url
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        elif not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        if not url.endswith("/v2/pipeline"):
            url = url.rstrip("/") + "/v2/pipeline"
        self.pipeline_url = url

        self.init_schema()

    def _execute_pipeline(
        self,
        stmts: list[tuple[str, list[Any] | None]],
    ) -> list[dict[str, Any]]:
        """Executa um lote de instruções SQL atomicamente através da pipeline HTTP do libSQL."""
        if not stmts:
            return []

        requests_payload: list[dict[str, Any]] = []
        for sql, args in stmts:
            req: dict[str, Any] = {"type": "execute"}
            stmt_obj: dict[str, Any] = {"sql": sql}
            if args is not None:
                stmt_obj["args"] = [_to_hrana_val(a) for a in args]
            req["stmt"] = stmt_obj
            requests_payload.append(req)

        requests_payload.append({"type": "close"})
        payload = json.dumps({"requests": requests_payload}).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
            "User-Agent": "pizza-radar-pt/1.0",
        }

        req = urllib.request.Request(
            self.pipeline_url,
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                data = json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            raise ConnectionError(
                f"Erro HTTP {e.code} ao comunicar com Turso ({self.pipeline_url}): {e.reason}. Detalhe: {err_body}"
            ) from e
        except Exception as e:
            raise ConnectionError(f"Falha de rede ao contactar Turso ({self.pipeline_url}): {e}") from e

        results = data.get("results", [])
        parsed_results: list[dict[str, Any]] = []

        for idx, res in enumerate(results):
            if res.get("type") == "error":
                err_msg = res.get("error", {}).get("message", "Erro desconhecido do libSQL")
                raise RuntimeError(f"Erro na execução da instrução SQL [{idx}]: {err_msg}")
            elif res.get("type") == "ok":
                resp_obj = res.get("response", {})
                if resp_obj.get("type") == "execute":
                    result = resp_obj.get("result", {})
                    cols = [c["name"] for c in result.get("cols", [])]
                    rows_raw = result.get("rows", [])
                    parsed_rows = []
                    for r in rows_raw:
                        row_dict = {}
                        for c_idx, col_name in enumerate(cols):
                            row_dict[col_name] = _from_hrana_val(r[c_idx])
                        parsed_rows.append(row_dict)
                    parsed_results.append({
                        "rows": parsed_rows,
                        "affected_row_count": result.get("affected_row_count", 0),
                        "last_insert_rowid": result.get("last_insert_rowid"),
                    })

        return parsed_results

    def init_schema(self) -> None:
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Esquema SQL não encontrado em {schema_path}")
        raw_sql = schema_path.read_text(encoding="utf-8")
        statements: list[tuple[str, list[Any] | None]] = []
        for stmt in raw_sql.split(";"):
            cleaned = stmt.strip()
            if cleaned and not cleaned.startswith("--"):
                statements.append((cleaned, None))
        if statements:
            self._execute_pipeline(statements)

    def upsert_stores(self, stores: list[dict[str, Any]]) -> None:
        if not stores:
            return
        sql = """
        INSERT INTO stores (store_id, vendor, name, postal_code, address, is_lisbon_municipality)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(store_id) DO UPDATE SET
            name = excluded.name,
            postal_code = excluded.postal_code,
            address = excluded.address,
            is_lisbon_municipality = excluded.is_lisbon_municipality;
        """
        stmts = [
            (
                sql,
                [
                    str(s["store_id"]),
                    s["vendor"].value if isinstance(s["vendor"], Brand) else str(s["vendor"]),
                    str(s["name"]),
                    s.get("postal_code"),
                    s.get("address"),
                    1 if s.get("is_lisbon_municipality", True) else 0,
                ],
            )
            for s in stores
        ]
        self._execute_pipeline(stmts)

    def record_vendor_sync_run(
        self,
        vendor: Brand,
        status: str,
        offers_found: int = 0,
        error_message: str | None = None,
        executed_at: datetime | None = None,
    ) -> int:
        ts = (executed_at or datetime.now(timezone.utc)).isoformat()
        vendor_str = vendor.value if isinstance(vendor, Brand) else str(vendor)
        sql = """
        INSERT INTO vendor_sync_runs (vendor, status, offers_found, error_message, executed_at)
        VALUES (?, ?, ?, ?, ?);
        """
        results = self._execute_pipeline([(sql, [vendor_str, status, offers_found, error_message, ts])])
        return results[0].get("last_insert_rowid") or 0

    def get_vendor_sync_runs(
        self,
        vendor: Brand | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if vendor is not None:
            vendor_str = vendor.value if isinstance(vendor, Brand) else str(vendor)
            sql = "SELECT * FROM vendor_sync_runs WHERE vendor = ? ORDER BY id DESC LIMIT ?;"
            results = self._execute_pipeline([(sql, [vendor_str, limit])])
        else:
            sql = "SELECT * FROM vendor_sync_runs ORDER BY id DESC LIMIT ?;"
            results = self._execute_pipeline([(sql, [limit])])
        return results[0]["rows"]

    def record_history(self, entries: list[ObservationEntry]) -> None:
        if not entries:
            return
        sql = """
        INSERT INTO observation_history (promotion_id, observed_at, price_cents, original_price_cents, is_available)
        VALUES (?, ?, ?, ?, ?);
        """
        stmts = [
            (
                sql,
                [
                    e.promotion_id,
                    e.observed_at,
                    e.price_cents,
                    e.original_price_cents,
                    1 if e.is_available else 0,
                ],
            )
            for e in entries
        ]
        self._execute_pipeline(stmts)

    def upsert_promotions(
        self,
        promos: list[UnifiedPromo],
        vendor: Brand,
        sync_time: datetime | None = None,
        max_consecutive_misses: int = 2,
    ) -> SyncStats:
        now_dt = sync_time or datetime.now(timezone.utc)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        now_iso = now_dt.isoformat()
        vendor_str = vendor.value if isinstance(vendor, Brand) else str(vendor)

        stats = SyncStats()

        # 1. Obter estado atual das ofertas deste operador
        sel_sql = "SELECT id, price_cents, original_price_cents, is_active, consecutive_misses, observed_at FROM promotions WHERE vendor = ?;"
        res = self._execute_pipeline([(sel_sql, [vendor_str])])
        existing_rows = res[0]["rows"]
        existing_by_id = {row["id"]: row for row in existing_rows}

        seen_ids = set()
        history_entries: list[ObservationEntry] = []
        batch_stmts: list[tuple[str, list[Any] | None]] = []

        for promo in promos:
            pid = promo.id
            seen_ids.add(pid)
            payload_json = promo.to_json()

            if pid not in existing_by_id:
                # Nova promoção
                insert_promo_sql = """
                INSERT INTO promotions (
                    id, vendor, title, description, price_cents, original_price_cents,
                    discount_percentage, discount_type, store_scope, pizza_count,
                    pizza_size, conditions, valid_from, valid_until, observed_at,
                    last_seen_at, consecutive_misses, is_active, location_scope,
                    source_url, image_url, raw_payload_json
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?, ?
                );
                """
                batch_stmts.append((
                    insert_promo_sql,
                    [
                        pid,
                        vendor_str,
                        promo.title,
                        promo.description,
                        promo.price_cents,
                        promo.original_price_cents,
                        promo.discount_percentage,
                        promo.discount_type.value,
                        promo.store_scope.value,
                        promo.pizza_count,
                        promo.pizza_size.value,
                        promo.conditions,
                        promo.valid_from,
                        promo.valid_until,
                        promo.observed_at or now_iso,
                        now_iso,
                        promo.location_scope,
                        promo.source_url,
                        promo.image_url,
                        payload_json,
                    ],
                ))

                for idx, sid in enumerate(promo.store_ids):
                    sname = promo.store_names[idx] if idx < len(promo.store_names) else f"Loja {sid}"
                    batch_stmts.append((
                        "INSERT OR IGNORE INTO stores (store_id, vendor, name) VALUES (?, ?, ?);",
                        [str(sid), vendor_str, sname],
                    ))
                    batch_stmts.append((
                        "INSERT OR IGNORE INTO promotion_stores (promotion_id, store_id) VALUES (?, ?);",
                        [pid, str(sid)],
                    ))

                history_entries.append(
                    ObservationEntry(
                        promotion_id=pid,
                        observed_at=promo.observed_at or now_iso,
                        price_cents=promo.price_cents,
                        original_price_cents=promo.original_price_cents,
                        is_available=True,
                    )
                )
                stats.created += 1
            else:
                old = existing_by_id[pid]
                was_active = bool(old["is_active"])
                old_price = old["price_cents"]
                old_orig = old["original_price_cents"]
                price_changed = (old_price != promo.price_cents) or (old_orig != promo.original_price_cents)

                if price_changed:
                    stats.price_changed += 1
                    history_entries.append(
                        ObservationEntry(
                            promotion_id=pid,
                            observed_at=now_iso,
                            price_cents=promo.price_cents,
                            original_price_cents=promo.original_price_cents,
                            is_available=True,
                        )
                    )

                if not was_active:
                    stats.reactivated += 1
                elif not price_changed:
                    stats.unchanged += 1

                stats.updated += 1

                update_promo_sql = """
                UPDATE promotions SET
                    title = ?,
                    description = ?,
                    price_cents = ?,
                    original_price_cents = ?,
                    discount_percentage = ?,
                    discount_type = ?,
                    store_scope = ?,
                    pizza_count = ?,
                    pizza_size = ?,
                    conditions = ?,
                    valid_from = ?,
                    valid_until = ?,
                    last_seen_at = ?,
                    consecutive_misses = 0,
                    is_active = 1,
                    location_scope = ?,
                    source_url = ?,
                    image_url = ?,
                    raw_payload_json = ?
                WHERE id = ?;
                """
                batch_stmts.append((
                    update_promo_sql,
                    [
                        promo.title,
                        promo.description,
                        promo.price_cents,
                        promo.original_price_cents,
                        promo.discount_percentage,
                        promo.discount_type.value,
                        promo.store_scope.value,
                        promo.pizza_count,
                        promo.pizza_size.value,
                        promo.conditions,
                        promo.valid_from,
                        promo.valid_until,
                        now_iso,
                        promo.location_scope,
                        promo.source_url,
                        promo.image_url,
                        payload_json,
                        pid,
                    ],
                ))

                batch_stmts.append((
                    "DELETE FROM promotion_stores WHERE promotion_id = ?;",
                    [pid],
                ))
                for idx, sid in enumerate(promo.store_ids):
                    sname = promo.store_names[idx] if idx < len(promo.store_names) else f"Loja {sid}"
                    batch_stmts.append((
                        "INSERT OR IGNORE INTO stores (store_id, vendor, name) VALUES (?, ?, ?);",
                        [str(sid), vendor_str, sname],
                    ))
                    batch_stmts.append((
                        "INSERT OR IGNORE INTO promotion_stores (promotion_id, store_id) VALUES (?, ?);",
                        [pid, str(sid)],
                    ))

        # 2. Promoções que não constavam do lote recolhido
        missing_promos = [
            row for pid, row in existing_by_id.items()
            if pid not in seen_ids and bool(row["is_active"])
        ]
        for row in missing_promos:
            pid = row["id"]
            new_misses = row["consecutive_misses"] + 1
            stats.misses_incremented += 1

            if new_misses >= max_consecutive_misses:
                batch_stmts.append((
                    "UPDATE promotions SET consecutive_misses = ?, is_active = 0, last_seen_at = ? WHERE id = ?;",
                    [new_misses, now_iso, pid],
                ))
                stats.deactivated_by_misses += 1
                history_entries.append(
                    ObservationEntry(
                        promotion_id=pid,
                        observed_at=now_iso,
                        price_cents=row["price_cents"],
                        original_price_cents=row["original_price_cents"],
                        is_available=False,
                    )
                )
            else:
                batch_stmts.append((
                    "UPDATE promotions SET consecutive_misses = ? WHERE id = ?;",
                    [new_misses, pid],
                ))

        # 3. Adicionar entradas de histórico
        for e in history_entries:
            batch_stmts.append((
                "INSERT INTO observation_history (promotion_id, observed_at, price_cents, original_price_cents, is_available) VALUES (?, ?, ?, ?, ?);",
                [e.promotion_id, e.observed_at, e.price_cents, e.original_price_cents, 1 if e.is_available else 0],
            ))

        if batch_stmts:
            self._execute_pipeline(batch_stmts)

        return stats

    def expire_outdated_promotions(
        self,
        reference_time: datetime | None = None,
    ) -> int:
        now_dt = reference_time or datetime.now(timezone.utc)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        now_iso = now_dt.isoformat()

        sel_sql = "SELECT id, price_cents, original_price_cents FROM promotions WHERE is_active = 1 AND valid_until IS NOT NULL AND valid_until < ?;"
        res = self._execute_pipeline([(sel_sql, [now_iso])])
        rows = res[0]["rows"]
        if not rows:
            return 0

        expired_count = len(rows)
        stmts: list[tuple[str, list[Any] | None]] = [
            (
                "UPDATE promotions SET is_active = 0 WHERE is_active = 1 AND valid_until IS NOT NULL AND valid_until < ?;",
                [now_iso],
            )
        ]
        for r in rows:
            stmts.append((
                "INSERT INTO observation_history (promotion_id, observed_at, price_cents, original_price_cents, is_available) VALUES (?, ?, ?, ?, 0);",
                [r["id"], now_iso, r["price_cents"], r["original_price_cents"]],
            ))
        self._execute_pipeline(stmts)
        return expired_count

    def get_promotion_by_id(self, promo_id: str) -> UnifiedPromo | None:
        sql = "SELECT * FROM promotions WHERE id = ?;"
        res = self._execute_pipeline([(sql, [promo_id])])
        rows = res[0]["rows"]
        if not rows:
            return None
        return _dict_or_row_to_unified_promo(rows[0])

    def get_active_promotions(self, location_scope: str = "Lisboa") -> list[UnifiedPromo]:
        sql = "SELECT * FROM promotions WHERE is_active = 1 AND location_scope = ? ORDER BY vendor, price_cents ASC;"
        res = self._execute_pipeline([(sql, [location_scope])])
        rows = res[0]["rows"]
        return [_dict_or_row_to_unified_promo(r) for r in rows]


LibSqlPromotionRepository = TursoPromotionRepository
