"""Adaptador de recolha de promoções para a Papa John's Portugal.

Implementa PromoAdapterInterface com separação explícita das camadas:
  - fetch_raw(): HTTP GET ao endpoint público sem autenticação.
  - parse(): extração e validação determinística dos campos relevantes do JSON.
  - adapt(): normalização para o contrato UnifiedPromo com agregação de lojas.

Regras de engenharia estritamente aplicadas:
  - Zero IA em runtime (sem chamadas a LLMs).
  - Zero segredos (sem API keys ou tokens).
  - Preços em cêntimos inteiros (integer cents), calculados via Decimal
    com ROUND_HALF_UP (zero conversão ou aritmética através de float).
  - Se um preço estiver presente mas for inválido, emite ParseError explicitamente.
  - Não publica itens com hidden=true.
  - Desduplicação determinística entre lojas: ofertas com preço, condições e
    validade idênticos produzem um único UnifiedPromo agregando store_ids e store_names.
  - Ofertas com variações reais entre lojas mantêm variantes separadas.
  - Canais delivery e takeaway mantêm resultados separados.
  - observed_at obrigatoriamente timezone-aware.
  - Erros de rede isolados em NetworkError; erros de parsing em ParseError.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from pizza_radar.core.adapter import NetworkError, ParseError, PromoAdapterInterface
from pizza_radar.core.classifier import classify_offer_type
from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
    Weekday,
)

# ---------------------------------------------------------------------------
# Configuração pública (sem segredos)
# ---------------------------------------------------------------------------

_API_BASE = "https://api.papajohns.pt/v1"

# Três lojas confirmadas no concelho de Lisboa (source-feasibility.md, 2026-09-28)
LISBON_STORES: dict[str, str] = {
    "2": "Amoreiras",
    "13": "Areeiro",
    "3": "Benfica",
}

# Modalidades de serviço a recolher
_DISPATCH_METHODS = ("in_store", "pj_delivery")

# Mapeamento dos dispatch_method da API para DispatchMethod do contrato canónico
_DISPATCH_MAP: dict[str, DispatchMethod] = {
    "in_store": DispatchMethod.TAKE_AWAY,
    "pj_delivery": DispatchMethod.DELIVERY,
}

# Categorias de imagem preferidas por modalidade
_IMAGE_CATEGORY_PREFERENCE: dict[str, list[str]] = {
    "pj_delivery": ["delivery_photo", "delivery_photo_app", "photo", "photo_app"],
    "in_store": ["photo", "photo_app", "delivery_photo", "delivery_photo_app"],
}

# Headers padrão de navegador moderno
_REQUEST_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-PLATFORM": "web",
    "Accept": "application/json",
}

# ---------------------------------------------------------------------------
# Funções auxiliares determinísticas
# ---------------------------------------------------------------------------

def parse_price_to_cents(
    value: Any,
    field_name: str = "price",
    offer_id: Any = None,
) -> int | None:
    """Converte um valor monetário em euros para cêntimos inteiros sem float.

    Usa Decimal e arredondamento determinístico ROUND_HALF_UP.
    Se o valor for None, devolve None.
    Se estiver presente mas for inválido, emite ParseError explicitamente.
    """
    if value is None:
        return None

    if isinstance(value, bool):
        raise ParseError(
            f"Valor booleano inválido no campo '{field_name}' da oferta {offer_id!r}: {value!r}",
            vendor=Brand.PAPA_JOHNS,
        )

    try:
        if isinstance(value, Decimal):
            d = value
        elif isinstance(value, int):
            d = Decimal(value)
        elif isinstance(value, str):
            cleaned = value.strip().replace(",", ".")
            if not cleaned:
                raise ParseError(
                    f"String vazia no campo monetário '{field_name}' da oferta {offer_id!r}",
                    vendor=Brand.PAPA_JOHNS,
                )
            d = Decimal(cleaned)
        elif isinstance(value, float):
            d = Decimal(str(value))
        else:
            raise ParseError(
                f"Tipo inválido para campo monetário '{field_name}' na oferta {offer_id!r}: {type(value).__name__}",
                vendor=Brand.PAPA_JOHNS,
            )

        if not d.is_finite():
            raise ParseError(
                f"Valor monetário não-finito no campo '{field_name}' da oferta {offer_id!r}: {value!r}",
                vendor=Brand.PAPA_JOHNS,
            )

        cents = (d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        cents_int = int(cents)

        if cents_int < 0:
            raise ParseError(
                f"Valor monetário negativo no campo '{field_name}' da oferta {offer_id!r}: {cents_int}",
                vendor=Brand.PAPA_JOHNS,
            )

        return cents_int

    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ParseError(
            f"Valor monetário inválido no campo '{field_name}' da oferta {offer_id!r}: {value!r}",
            vendor=Brand.PAPA_JOHNS,
        ) from exc


def _parse_pizza_size(raw_size: str | None) -> PizzaSize:
    """Normaliza uma string de tamanho para PizzaSize sem inventar valores."""
    if not raw_size:
        return PizzaSize.UNKNOWN
    size_lower = raw_size.lower().strip()
    if size_lower in ("individual", "personal", "small"):
        return PizzaSize.INDIVIDUAL
    if size_lower in ("media", "médio", "médias", "medium", "med"):
        return PizzaSize.MEDIUM
    if size_lower in ("large", "grande", "grandes"):
        return PizzaSize.LARGE
    if size_lower in ("family", "familiar", "king"):
        return PizzaSize.FAMILY
    return PizzaSize.UNKNOWN


def _select_image_url(pictures: list[dict[str, Any]] | None, dispatch_method: str) -> str | None:
    """Seleciona o URL de imagem mais apropriado para a modalidade de serviço."""
    if not pictures:
        return None

    preference = _IMAGE_CATEGORY_PREFERENCE.get(dispatch_method, ["photo"])

    by_category: dict[str, str] = {}
    for pic in pictures:
        if not isinstance(pic, dict):
            continue
        url = pic.get("url")
        category = pic.get("category", "")
        if url and isinstance(url, str) and url.startswith(("http://", "https://")):
            if category not in by_category:
                by_category[category] = url

    for cat in preference:
        if cat in by_category:
            return by_category[cat]

    return next(iter(by_category.values()), None)


def _parse_availability(availability: Any) -> list[Weekday]:
    """Normaliza o campo availability para lista ordenada de Weekday."""
    _API_DAYS: dict[str, Weekday] = {
        "monday": Weekday.MONDAY,
        "tuesday": Weekday.TUESDAY,
        "wednesday": Weekday.WEDNESDAY,
        "thursday": Weekday.THURSDAY,
        "friday": Weekday.FRIDAY,
        "saturday": Weekday.SATURDAY,
        "sunday": Weekday.SUNDAY,
        "segunda": Weekday.MONDAY,
        "terça": Weekday.TUESDAY,
        "quarta": Weekday.WEDNESDAY,
        "quinta": Weekday.THURSDAY,
        "sexta": Weekday.FRIDAY,
        "sábado": Weekday.SATURDAY,
        "domingo": Weekday.SUNDAY,
    }

    days: list[Weekday] = []
    if isinstance(availability, list):
        for day in availability:
            if isinstance(day, str):
                mapped = _API_DAYS.get(day.lower().strip())
                if mapped and mapped not in days:
                    days.append(mapped)
    elif isinstance(availability, dict):
        for day, active in availability.items():
            if active:
                mapped = _API_DAYS.get(day.lower().strip())
                if mapped and mapped not in days:
                    days.append(mapped)
    return days


def _sort_store_ids(store_ids: list[str] | set[str]) -> list[str]:
    """Ordena store_ids deterministicamente (ordem numérica quando aplicável)."""
    return sorted(set(store_ids), key=lambda s: (0, int(s)) if s.isdigit() else (1, s))


# ---------------------------------------------------------------------------
# Adaptador principal
# ---------------------------------------------------------------------------

class PapaJohnsAdapter(PromoAdapterInterface):
    """Adaptador para a Papa John's Portugal (concelho de Lisboa).

    Recolhe e normaliza promoções das 3 lojas de Lisboa (Amoreiras, Areeiro, Benfica)
    para ambas as modalidades de serviço (in_store e pj_delivery).
    """

    DEFAULT_TIMEOUT: float = 15.0

    @property
    def vendor(self) -> Brand:
        return Brand.PAPA_JOHNS

    # ------------------------------------------------------------------
    # 1. Camada de obtenção HTTP (isolada para testes)
    # ------------------------------------------------------------------

    def fetch_raw(
        self,
        store_id: str,
        dispatch_method: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> list[dict[str, Any]]:
        """Faz um GET ao endpoint de promoções com parsing Decimal nativo."""
        url = (
            f"{_API_BASE}/offers/promotions"
            f"?store_id={store_id}&dispatch_method={dispatch_method}"
        )

        req = urllib.request.Request(url, headers=_REQUEST_HEADERS, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise NetworkError(
                f"HTTP {exc.code} ao aceder a {url}: {exc.reason}",
                vendor=self.vendor,
            ) from exc
        except urllib.error.URLError as exc:
            raise NetworkError(
                f"Erro de rede ao aceder a {url}: {exc.reason}",
                vendor=self.vendor,
            ) from exc
        except TimeoutError as exc:
            raise NetworkError(
                f"Timeout ({timeout}s) ao aceder a {url}",
                vendor=self.vendor,
            ) from exc
        except OSError as exc:
            raise NetworkError(
                f"Erro de I/O ao aceder a {url}: {exc}",
                vendor=self.vendor,
            ) from exc

        try:
            data = json.loads(body, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise ParseError(
                f"Resposta de {url} não é JSON válido: {exc}",
                vendor=self.vendor,
            ) from exc

        if not isinstance(data, list):
            raise ParseError(
                f"Estrutura inesperada em {url}: esperada lista no raiz, recebido {type(data).__name__}",
                vendor=self.vendor,
            )

        return data

    # ------------------------------------------------------------------
    # 2. Camada de parsing (sem I/O — testável com fixtures)
    # ------------------------------------------------------------------

    def parse(
        self,
        raw: list[dict[str, Any]],
        store_id: str,
        dispatch_method: str,
    ) -> list[dict[str, Any]]:
        """Extrai e valida os campos relevantes do payload bruto.

        Regras estritas:
        - Não publica itens com hidden=true.
        - Campos obrigatórios ausentes ou inválidos emitem ParseError.
        - Preços são convertidos para cêntimos inteiros via parse_price_to_cents (sem float).
        - Preço inválido emite ParseError explicitamente.
        """
        if not isinstance(raw, list):
            raise ParseError(
                f"Payload de parsing inválido: esperado list, recebido {type(raw).__name__}",
                vendor=self.vendor,
            )

        parsed: list[dict[str, Any]] = []

        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ParseError(
                    f"Elemento {idx} do payload não é um dicionário: {type(item).__name__}",
                    vendor=self.vendor,
                )

            # 1. Filtro de ofertas ocultas: não publicar itens com hidden=true
            is_hidden = item.get("hidden", False)
            if is_hidden is not None and not isinstance(is_hidden, bool):
                raise ParseError(
                    f"Elemento {idx}: campo 'hidden' deve ser booleano, recebido {type(is_hidden).__name__}",
                    vendor=self.vendor,
                )
            if is_hidden is True:
                continue

            # 2. Campos mínimos obrigatórios
            offer_id = item.get("id")
            if offer_id is None or (isinstance(offer_id, str) and not offer_id.strip()):
                raise ParseError(
                    f"Elemento {idx} sem campo 'id' válido — payload alterado",
                    vendor=self.vendor,
                )

            name = item.get("name")
            if name is None or not isinstance(name, str) or not name.strip():
                raise ParseError(
                    f"Elemento {idx} (id={offer_id!r}) sem campo 'name' válido — payload alterado",
                    vendor=self.vendor,
                )

            # 3. Validação estrita de preços sem float
            # Se presente mas inválido, emite ParseError explicitamente
            price_cents = parse_price_to_cents(item.get("price"), "price", offer_id)
            original_price_cents = parse_price_to_cents(
                item.get("original_price"), "original_price", offer_id
            )

            # Se o original_price for menor que o promotional price (anomalia de catálogo),
            # descarta original_price_cents deterministicamente (nunca inventa PVP)
            if (
                price_cents is not None
                and original_price_cents is not None
                and original_price_cents < price_cents
            ):
                original_price_cents = None

            # 4. Contexto de canal (delivery vs in_store)
            item_dispatch = str(item.get("dispatch_method", ""))
            if dispatch_method == "pj_delivery" and item_dispatch == "both":
                effective_name = item.get("name_delivery") or name
                effective_description = item.get("description_delivery") or item.get("description") or ""
            else:
                effective_name = str(name)
                effective_description = str(item.get("description") or "")

            # 5. Validação de tipos de campos secundários
            pictures = item.get("pictures")
            if pictures is not None and not isinstance(pictures, list):
                raise ParseError(
                    f"Elemento {idx} (id={offer_id!r}): campo 'pictures' deve ser lista",
                    vendor=self.vendor,
                )

            availability = item.get("availability")
            if availability is not None and not isinstance(availability, (list, dict)):
                raise ParseError(
                    f"Elemento {idx} (id={offer_id!r}): campo 'availability' inválido",
                    vendor=self.vendor,
                )

            parsed.append({
                "id": str(offer_id),
                "name": str(effective_name),
                "description": str(effective_description),
                "price_cents": price_cents,
                "original_price_cents": original_price_cents,
                "request_dispatch_method": dispatch_method,
                "item_dispatch_method": item_dispatch,
                "store_id": str(store_id),
                "availability": availability,
                "start_datetime": item.get("start_datetime"),
                "end_datetime": item.get("end_datetime"),
                "pictures": pictures,
                "position": item.get("position"),
                "promoted": item.get("promoted", False),
                "conditions": item.get("conditions") or item.get("terms") or "",
            })

        return parsed

    # ------------------------------------------------------------------
    # 3. Camada de normalização (sem I/O — testável unitariamente)
    # ------------------------------------------------------------------

    def adapt(
        self,
        parsed_item: dict[str, Any],
        observed_at: datetime,
        store_ids: list[str] | None = None,
        variant_id: str | None = None,
    ) -> UnifiedPromo:
        """Normaliza um item parseado para o contrato UnifiedPromo.

        Suporta agregação de lojas: quando uma oferta é idêntica em várias
        lojas, store_ids e store_names contêm a lista agregada.
        """
        if observed_at.tzinfo is None:
            raise ValueError(
                f"observed_at deve ser timezone-aware, recebido: {observed_at!r}"
            )

        dispatch_method_raw = parsed_item["request_dispatch_method"]
        dispatch_method = _DISPATCH_MAP.get(dispatch_method_raw, DispatchMethod.DELIVERY)

        price_cents = parsed_item.get("price_cents")
        original_price_cents = parsed_item.get("original_price_cents")

        # Tipo de desconto
        if original_price_cents is not None and price_cents is not None:
            discount_type = DiscountType.FIXED_PRICE
        else:
            discount_type = DiscountType.SPECIAL_MENU

        # Dias da semana
        days_of_week = _parse_availability(parsed_item.get("availability"))

        # Validade anunciada pela marca
        valid_from: str | None = None
        valid_until: str | None = None
        raw_start = parsed_item.get("start_datetime")
        raw_end = parsed_item.get("end_datetime")
        if raw_start and isinstance(raw_start, str):
            valid_from = raw_start
        if raw_end and isinstance(raw_end, str):
            valid_until = raw_end

        # Imagem contextual
        image_url = _select_image_url(
            parsed_item.get("pictures"), dispatch_method_raw
        )

        # Lojas agregadas
        if store_ids:
            effective_store_ids = _sort_store_ids(store_ids)
        else:
            effective_store_ids = [parsed_item["store_id"]]

        store_names = [
            LISBON_STORES.get(sid, f"Loja {sid}")
            for sid in effective_store_ids
        ]

        # ID canónico determinístico
        if variant_id:
            canonical_id = variant_id
        else:
            canonical_id = f"pj_{parsed_item['id']}_{dispatch_method_raw}"

        # Classificação determinística da oferta
        offer_type = classify_offer_type(
            title=parsed_item["name"],
            description=parsed_item["description"],
            included_items=[],
            pizza_count=None,
        )

        return UnifiedPromo(
            id=canonical_id,
            vendor=Brand.PAPA_JOHNS,
            title=parsed_item["name"],
            description=parsed_item["description"],
            observed_at=observed_at.isoformat(),
            price_cents=price_cents,
            original_price_cents=original_price_cents,
            discount_type=discount_type,
            conditions=parsed_item.get("conditions", ""),
            valid_from=valid_from,
            valid_until=valid_until,
            days_of_week=days_of_week,
            dispatch_methods=[dispatch_method],
            store_scope=StoreScope.SPECIFIC_STORES,
            store_ids=effective_store_ids,
            store_names=store_names,
            pizza_count=None,
            pizza_size=PizzaSize.UNKNOWN,
            included_items=[],
            image_url=image_url,
            source_url="https://www.papajohns.pt/promocoes/",
            location_scope="Lisboa",
            offer_type=offer_type,
        )

    # ------------------------------------------------------------------
    # 4. Ponto de entrada principal com agregação determinística entre lojas
    # ------------------------------------------------------------------

    def _variant_signature(self, item: dict[str, Any]) -> tuple:
        """Assinatura determinística para agrupamento de variantes idênticas."""
        days = tuple(sorted(d.value for d in _parse_availability(item.get("availability"))))
        image = _select_image_url(item.get("pictures"), item["request_dispatch_method"])
        return (
            item.get("price_cents"),
            item.get("original_price_cents"),
            item.get("name"),
            item.get("description"),
            item.get("conditions"),
            item.get("start_datetime"),
            item.get("end_datetime"),
            days,
            image,
        )

    def fetch_promotions(self, timeout: float = DEFAULT_TIMEOUT) -> list[UnifiedPromo]:
        """Recolhe, agrega e normaliza as promoções das lojas de Lisboa.

        Agrupamento determinístico:
        - Para cada par (offer_id, canal):
          - Se a oferta for idêntica em várias lojas, produz um único UnifiedPromo
            com store_ids e store_names agregados e ID canónico 'pj_{id}_{canal}'.
          - Se houver variações reais de preço/condições entre lojas, mantém
            variantes separadas com IDs diferenciados 'pj_{id}_{canal}_{lojas}'.
          - Delivery e takeaway mantêm resultados separados.
        """
        observed_at = datetime.now(tz=timezone.utc)

        # 1. Recolhe dados de todas as lojas e canais
        collected: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}

        for store_id in LISBON_STORES:
            for dispatch_method in _DISPATCH_METHODS:
                raw = self.fetch_raw(store_id, dispatch_method, timeout)
                parsed = self.parse(raw, store_id, dispatch_method)
                for item in parsed:
                    key = (item["id"], dispatch_method)
                    collected.setdefault(key, []).append((store_id, item))

        # 2. Agregação determinística de variantes
        promos: list[UnifiedPromo] = []

        sorted_keys = sorted(
            collected.keys(),
            key=lambda k: (k[1], int(k[0]) if k[0].isdigit() else k[0])
        )

        for offer_id, dispatch_method in sorted_keys:
            store_items = collected[(offer_id, dispatch_method)]

            # Agrupar por assinatura de conteúdo da oferta
            variants: dict[tuple, tuple[dict[str, Any], set[str]]] = {}
            for store_id, item in store_items:
                sig = self._variant_signature(item)
                if sig not in variants:
                    variants[sig] = (item, {store_id})
                else:
                    variants[sig][1].add(store_id)

            has_multiple_variants = len(variants) > 1

            # Ordenar variantes deterministicamente por preço e lojas
            sorted_variants = sorted(
                variants.values(),
                key=lambda v: (
                    v[0].get("price_cents") or 0,
                    _sort_store_ids(v[1])
                )
            )

            for item, store_ids_set in sorted_variants:
                sorted_store_ids = _sort_store_ids(store_ids_set)
                if has_multiple_variants:
                    variant_id = f"pj_{offer_id}_{dispatch_method}_{'_'.join(sorted_store_ids)}"
                else:
                    variant_id = f"pj_{offer_id}_{dispatch_method}"

                promo = self.adapt(
                    item,
                    observed_at=observed_at,
                    store_ids=sorted_store_ids,
                    variant_id=variant_id,
                )
                promos.append(promo)

        return self.validate_and_filter(promos)
