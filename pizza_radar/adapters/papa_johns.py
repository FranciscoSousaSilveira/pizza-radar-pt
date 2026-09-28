"""Adaptador de recolha de promoções para a Papa John's Portugal.

Implementa PromoAdapterInterface com separação explícita das camadas:
  - fetch_raw(): HTTP GET ao endpoint público sem autenticação.
  - parse(): extração determinística dos campos relevantes do JSON.
  - adapt(): normalização para o contrato UnifiedPromo.

Regras de engenharia estritamente aplicadas:
  - Zero IA em runtime (sem chamadas a LLMs).
  - Zero segredos (sem API keys ou tokens).
  - Preços em cêntimos inteiros (integer cents).
  - Campos opcionais nunca inventados: pizza_count é None porque o endpoint
    /v1/offers/promotions não expõe offer_groups; image_url, valid_from,
    valid_until e conditions apenas preenchidos quando a fonte os fornece.
  - observed_at obrigatoriamente timezone-aware.
  - Erros de rede isolados em NetworkError; erros de parsing em ParseError.

Nota de implementação (confirmada via source-researcher, 2026-09-28):
  - O endpoint /v1/offers/promotions responde com um array JSON direto (sem wrapper).
  - Campos: id, dispatch_method, name, name_delivery, description,
    description_delivery, price, original_price, start_datetime, end_datetime,
    availability, pictures, offer_type, position, hidden, promoted, etc.
  - NÃO existe offer_groups neste endpoint; pizza_count fica sempre None.
  - dispatch_method no payload pode ser "in_store", "pj_delivery" ou "both".
  - price e original_price são Decimal (float); convertidos para int cents.
  - pictures é array de objetos com url, key, thumbnails e category
    (valores: "photo", "delivery_photo", "photo_app", "delivery_photo_app").
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pizza_radar.core.adapter import NetworkError, ParseError, PromoAdapterInterface
from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
)

# ---------------------------------------------------------------------------
# Configuração pública (sem segredos)
# ---------------------------------------------------------------------------

# Endpoint público utilizado pelo frontend oficial da marca.
# Sem garantia de estabilidade contratual — monitorizar alterações.
_API_BASE = "https://api.papajohns.pt/v1"

# Três lojas confirmadas no concelho de Lisboa (source-feasibility.md, 2026-09-28)
LISBON_STORES: dict[str, str] = {
    "2": "Amoreiras",
    "13": "Areeiro",
    "3": "Benfica",
}

# Modalidades de serviço a recolher
_DISPATCH_METHODS = ("in_store", "pj_delivery")

# Mapeamento dos dispatch_method da API para DispatchMethod do contrato
_DISPATCH_MAP: dict[str, DispatchMethod] = {
    "in_store": DispatchMethod.TAKE_AWAY,
    "pj_delivery": DispatchMethod.DELIVERY,
}

# Categorias de imagem preferidas por modalidade (ordem decrescente de preferência)
_IMAGE_CATEGORY_PREFERENCE: dict[str, list[str]] = {
    "pj_delivery": ["delivery_photo", "delivery_photo_app", "photo", "photo_app"],
    "in_store": ["photo", "photo_app", "delivery_photo", "delivery_photo_app"],
}

# Headers que replicam o tráfego normal do frontend oficial (sem contornar proteções)
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
# Funções auxiliares
# ---------------------------------------------------------------------------

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
    """Seleciona o URL de imagem mais apropriado para a modalidade de serviço.

    Prefere a categoria de imagem adequada ao canal (delivery/in_store).
    Devolve None se não houver imagens válidas.
    """
    if not pictures:
        return None

    preference = _IMAGE_CATEGORY_PREFERENCE.get(dispatch_method, ["photo"])

    # Indexa as imagens por categoria
    by_category: dict[str, str] = {}
    for pic in pictures:
        if not isinstance(pic, dict):
            continue
        url = pic.get("url")
        category = pic.get("category", "")
        if url and isinstance(url, str) and url.startswith(("http://", "https://")):
            if category not in by_category:
                by_category[category] = url

    # Seleciona pela ordem de preferência
    for cat in preference:
        if cat in by_category:
            return by_category[cat]

    # Fallback: qualquer URL válida disponível
    return next(iter(by_category.values()), None)


def _parse_availability(availability: Any) -> list:
    """Normaliza o campo availability para lista de Weekday."""
    from pizza_radar.core.models import Weekday  # local import para evitar ciclos circulares

    _API_DAYS: dict[str, Weekday] = {
        "monday": Weekday.MONDAY,
        "tuesday": Weekday.TUESDAY,
        "wednesday": Weekday.WEDNESDAY,
        "thursday": Weekday.THURSDAY,
        "friday": Weekday.FRIDAY,
        "saturday": Weekday.SATURDAY,
        "sunday": Weekday.SUNDAY,
        # Português possível
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


# ---------------------------------------------------------------------------
# Adaptador principal
# ---------------------------------------------------------------------------

class PapaJohnsAdapter(PromoAdapterInterface):
    """Adaptador para a Papa John's Portugal (concelho de Lisboa).

    Recolhe promoções das 3 lojas de Lisboa (Amoreiras, Areeiro, Benfica)
    para ambas as modalidades de serviço (in_store e pj_delivery).
    Devolve a união desduplicada das promoções, uma entrada por oferta×modalidade.

    Nota: pizza_count é sempre None neste adaptador porque o endpoint
    /v1/offers/promotions não expõe a composição interna dos combos
    (offer_groups). Futura evolução pode usar /v1/offers/{id} para enriquecer.
    """

    # Timeout por defeito: 15 segundos conforme especificado no Issue #8
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
        """Faz um GET ao endpoint de promoções e devolve o array JSON bruto.

        Args:
            store_id: Identificador da loja (ex.: "2" para Amoreiras).
            dispatch_method: "in_store" ou "pj_delivery".
            timeout: Timeout em segundos.

        Returns:
            Lista de dicionários brutos (resposta JSON da API).

        Raises:
            NetworkError: Em caso de falha HTTP, timeout ou rede.
            ParseError: Se a resposta não for JSON válido ou não for uma lista.
        """
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
            data = json.loads(body)
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

        Aplica verificações de presença e tipo sem modificar valores.
        Emite ParseError se a estrutura do payload tiver mudado de forma
        que impeça a extração dos campos mínimos obrigatórios.

        Nota sobre dispatch_method no payload vs. no pedido:
        O campo dispatch_method de cada item pode ser "in_store", "pj_delivery"
        ou "both". O pedido HTTP usa "in_store" ou "pj_delivery" para filtrar,
        mas itens com dispatch_method="both" aparecem nos dois pedidos.
        O campo `request_dispatch_method` preserva a modalidade do pedido HTTP.

        Args:
            raw: Lista bruta devolvida por fetch_raw().
            store_id: ID da loja (para compor o ID canónico).
            dispatch_method: Modalidade de serviço do pedido HTTP.

        Returns:
            Lista de dicionários com os campos normalizados extraídos.

        Raises:
            ParseError: Se o payload tiver estrutura inesperada.
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

            # Campos mínimos obrigatórios
            offer_id = item.get("id")
            name = item.get("name")

            if offer_id is None:
                raise ParseError(
                    f"Elemento {idx} sem campo 'id' — payload alterado inesperadamente",
                    vendor=self.vendor,
                )
            if not name:
                raise ParseError(
                    f"Elemento {idx} (id={offer_id!r}) sem campo 'name' — payload alterado",
                    vendor=self.vendor,
                )

            # Para itens com dispatch_method="both", usa nome/descrição de delivery
            # quando a modalidade solicitada é pj_delivery
            item_dispatch = str(item.get("dispatch_method", ""))
            if dispatch_method == "pj_delivery" and item_dispatch == "both":
                effective_name = item.get("name_delivery") or name
                effective_description = item.get("description_delivery") or item.get("description") or ""
            else:
                effective_name = str(name)
                effective_description = str(item.get("description") or "")

            parsed.append({
                "id": str(offer_id),
                "name": str(effective_name),
                "description": effective_description,
                "price": item.get("price"),            # Decimal (float) ou None
                "original_price": item.get("original_price"),  # Decimal (float) ou None
                "request_dispatch_method": dispatch_method,
                "item_dispatch_method": item_dispatch,
                "store_id": store_id,
                "availability": item.get("availability"),      # lista de dias em inglês ou None
                "start_datetime": item.get("start_datetime"),  # str ISO com Z ou None
                "end_datetime": item.get("end_datetime"),      # str ISO com Z ou None
                "pictures": item.get("pictures"),              # lista de dicts ou None
                "position": item.get("position"),              # int — ordem de exibição
                "hidden": item.get("hidden", False),           # bool — se oculto
                "promoted": item.get("promoted", False),       # bool — se destacado
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
    ) -> UnifiedPromo:
        """Normaliza um item parseado para o contrato UnifiedPromo.

        Regras estritas:
        - Preços convertidos de euros Decimal (float) para cêntimos inteiros.
        - Nunca inventa pizza_count (não disponível neste endpoint).
        - valid_from e valid_until preenchidos a partir de start/end_datetime.
        - image_url: URL preferida por modalidade (delivery_photo / photo).
        - observed_at obrigatoriamente timezone-aware.
        - store_scope = SPECIFIC_STORES com IDs e nomes das lojas de Lisboa.
        - original_price inconsistente (original < promo) é ignorado.

        Args:
            parsed_item: Dicionário devolvido por parse().
            observed_at: Momento de observação timezone-aware.

        Returns:
            UnifiedPromo validável pelo contrato canónico.
        """
        if observed_at.tzinfo is None:
            raise ValueError(
                f"observed_at deve ser timezone-aware, recebido: {observed_at!r}"
            )

        store_id = parsed_item["store_id"]
        dispatch_method_raw = parsed_item["request_dispatch_method"]
        dispatch_method = _DISPATCH_MAP.get(dispatch_method_raw, DispatchMethod.DELIVERY)

        # --- Preços em cêntimos inteiros ---
        price_cents: int | None = None
        raw_price = parsed_item.get("price")
        if raw_price is not None:
            try:
                price_cents = int(round(float(raw_price) * 100))
            except (TypeError, ValueError):
                price_cents = None

        original_price_cents: int | None = None
        raw_original = parsed_item.get("original_price")
        if raw_original is not None:
            try:
                original_price_cents = int(round(float(raw_original) * 100))
            except (TypeError, ValueError):
                original_price_cents = None

        # Garante que o preço original não é inferior ao promocional (anomalia conhecida, ex: ID 218)
        if (
            price_cents is not None
            and original_price_cents is not None
            and original_price_cents < price_cents
        ):
            original_price_cents = None  # Ignora original inconsistente — nunca fabricar

        # --- Tipo de desconto ---
        if original_price_cents is not None and price_cents is not None:
            discount_type = DiscountType.FIXED_PRICE
        else:
            discount_type = DiscountType.SPECIAL_MENU

        # --- Dias da semana ---
        days_of_week = _parse_availability(parsed_item.get("availability"))

        # --- Datas de validade anunciadas pela marca ---
        # A API devolve ISO 8601 com milissegundos e 'Z' (ex: "2028-12-31T00:00:00.000Z")
        valid_from: str | None = None
        valid_until: str | None = None
        raw_start = parsed_item.get("start_datetime")
        raw_end = parsed_item.get("end_datetime")
        if raw_start and isinstance(raw_start, str):
            valid_from = raw_start
        if raw_end and isinstance(raw_end, str):
            valid_until = raw_end

        # --- Imagem (preferência por categoria de canal) ---
        image_url = _select_image_url(
            parsed_item.get("pictures"), dispatch_method_raw
        )

        # --- pizza_count e pizza_size: não disponíveis neste endpoint ---
        # O endpoint /v1/offers/promotions não expõe offer_groups.
        # pizza_count fica None — nunca inventado a partir da descrição.

        # --- ID canónico (vendedor+id da oferta+loja+modalidade do pedido) ---
        canonical_id = f"pj_{parsed_item['id']}_{store_id}_{dispatch_method_raw}"

        # --- Âmbito geográfico: lojas específicas de Lisboa ---
        store_name = LISBON_STORES.get(store_id, f"Loja {store_id}")

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
            store_ids=[store_id],
            store_names=[store_name],
            pizza_count=None,       # Não disponível em /v1/offers/promotions
            pizza_size=PizzaSize.UNKNOWN,
            included_items=[],      # Não disponível em /v1/offers/promotions
            image_url=image_url,
            source_url="https://www.papajohns.pt/promocoes/",
            location_scope="Lisboa",
        )

    # ------------------------------------------------------------------
    # 4. Ponto de entrada principal
    # ------------------------------------------------------------------

    def fetch_promotions(self, timeout: float = DEFAULT_TIMEOUT) -> list[UnifiedPromo]:
        """Recolhe e normaliza todas as promoções das 3 lojas de Lisboa.

        Itera sobre as 3 lojas e as 2 modalidades (in_store, pj_delivery).
        Uma falha numa loja/modalidade específica propaga NetworkError ou
        ParseError sem suprimir a exceção — o caller (orquestrador) decide
        se continua ou aborta. Não incrementa consecutive_misses: esse
        controlo fica na camada de pipeline (ver ADR-002).

        Returns:
            Lista de UnifiedPromo únicos (uma entrada por oferta×modalidade×loja),
            validados pelo contrato canónico.
        """
        observed_at = datetime.now(tz=timezone.utc)
        promos: list[UnifiedPromo] = []
        seen_ids: set[str] = set()

        for store_id in LISBON_STORES:
            for dispatch_method in _DISPATCH_METHODS:
                raw = self.fetch_raw(store_id, dispatch_method, timeout)
                parsed = self.parse(raw, store_id, dispatch_method)
                for item in parsed:
                    promo = self.adapt(item, observed_at)
                    if promo.id not in seen_ids:
                        seen_ids.add(promo.id)
                        promos.append(promo)

        return self.validate_and_filter(promos)
