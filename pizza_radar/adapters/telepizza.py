"""Adaptador de recolha de promoções para a Telepizza Portugal (Lisboa).

Implementa PromoAdapterInterface com integração primária via Salesforce B2C Commerce API (SCAPI):
  - Autenticação SLAS guest com fluxo PKCE legítimo (sem credenciais privadas).
  - Consulta de promoções oficiais via getPromotions da Shopper Promotions API.
  - Extração determinística de metadados oficiais: c_tpz_promoFixedPrice, dias da semana, canais.
  - Normalização para UnifiedPromo com preços em Decimal e cêntimos inteiros.
  - Classificação determinística de OfferType (bebidas, gelados, burgers e frango -> NON_PIZZA).
  - Transparência de cobertura: coverage_level = "FEATURED".
  - Mantém suporte retrocompatível a parsing de HTML para fixtures e testes estáticos.

Regras estritas:
  - Zero IA em runtime.
  - Zero segredos comitados (SLAS client_id é o identificador público da storefront oficial).
  - StoreScope.UNKNOWN (promoções a nível de site sem associação de lojas específicas de Lisboa).
  - Falhas isoladas em NetworkError e ParseError.
"""

from __future__ import annotations

import base64
import hashlib
import html
import http.client
import json
import logging
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
from typing import Any

logger = logging.getLogger(__name__)

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

_URL = "https://www.telepizza.pt/promocoes"

_SHORT_CODE = "e6dubte9"
_ORG_ID = "f_ecom_bktv_prd"
_SITE_ID = "TelepizzaPT"
_CLIENT_ID = "33caf917-7f3d-4a33-b78e-75424c3e4985"
_REDIRECT_URI = "http://localhost:3000/callback"

_BASE_SCAPI_URL = f"https://{_SHORT_CODE}.api.commercecloud.salesforce.com"
_AUTH_URL = f"{_BASE_SCAPI_URL}/shopper/auth/v1/organizations/{_ORG_ID}/oauth2/authorize"
_TOKEN_URL = f"{_BASE_SCAPI_URL}/shopper/auth/v1/organizations/{_ORG_ID}/oauth2/token"
_PROMOTIONS_URL = f"{_BASE_SCAPI_URL}/pricing/shopper-promotions/v1/organizations/{_ORG_ID}/promotions"
_SEARCH_URL = f"{_BASE_SCAPI_URL}/search/shopper-search/v1/organizations/{_ORG_ID}/product-search"

# Lista canónica das 20 campanhas oficiais ativas da Telepizza Portugal comprovadas via SCAPI
DEFAULT_PROMOTION_IDS: list[str] = [
    "2x1_MedFam",
    "MMINDTSTK",
    "MMINDDSTK",
    "MMBRGTSTK",
    "MMMEDTSTK",
    "MMMEDDSTK",
    "MMBRGDSTK",
    "3PMENOSTK",
    "3porMenos",
    "2porMenos",
    "1PMENOSTK",
    "1porMenos",
    "Med595_TK",
    "8PIZZOLINO",
    "2BEBGARX",
    "2BEB33K",
    "2x1_Gel",
    "D30_NC",
    "55_NC",
    "BUCKETSLK",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "close",
}

_PRICE_REGEX = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|&euro;|euros)", re.IGNORECASE)
_DISCOUNT_REGEX = re.compile(r"-?\s*(\d+(?:[.,]\d+)?)\s*%(?:\s*(?:de\s+)?desconto)?", re.IGNORECASE)
_PIZZA_COUNT_REGEX = re.compile(r"(\d+)\s*pizzas?", re.IGNORECASE)


def _extract_cents_from_text(text: str) -> int | None:
    match = _PRICE_REGEX.search(text)
    if not match:
        return None
    raw_str = match.group(1).replace(",", ".")
    try:
        d = Decimal(raw_str)
        return int((d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def _extract_discount_percentage(text: str) -> float | None:
    match = _DISCOUNT_REGEX.search(text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


class TelepizzaHTMLParser(HTMLParser):
    """Parser HTML tolerante para extrair cartões promocionais da Telepizza.

    Imune a permutações na ordem dos atributos HTML (ex.: data-id antes ou depois de data-name).
    """

    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict[str, Any]] = []
        self._current_tab_content: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        classes = attr_dict.get("class", "").split()

        if "offer-tile__wrap" in classes:
            self._current_tab_content = attr_dict.get("data-tab-content", "")

        if "data-id" in attr_dict:
            card_id = attr_dict.get("data-id", "").strip()
            name = attr_dict.get("data-name", "")
            detail = attr_dict.get("data-detail", "")
            img_url = attr_dict.get("data-img-url", "")
            self.cards.append({
                "id": card_id,
                "name": name,
                "detail": detail,
                "img_url": img_url,
                "tab_content": self._current_tab_content,
            })


class TelepizzaAdapter(PromoAdapterInterface):
    """Adaptador para a Telepizza Portugal com suporte a SCAPI e fallback HTML."""

    DEFAULT_TIMEOUT: float = 20.0

    def __init__(self) -> None:
        self.coverage_level: str = "FEATURED"
        self.coverage_note: str | None = (
            "Campanhas principais sincronizadas via API oficial Salesforce (amostra de 20 campanhas ativas)"
        )

    @property
    def vendor(self) -> Brand:
        return Brand.TELEPIZZA

    def fetch_slas_token(self, timeout: float = DEFAULT_TIMEOUT) -> str:
        """Obtém token SLAS guest através do fluxo PKCE suportado pela storefront oficial."""
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
            .decode("utf-8")
            .rstrip("=")
        )

        params = urllib.parse.urlencode({
            "client_id": _CLIENT_ID,
            "channel_id": _SITE_ID,
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "redirect_uri": _REDIRECT_URI,
            "hint": "guest",
        })
        auth_url = f"{_AUTH_URL}?{params}"

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(_NoRedirect)
        try:
            resp = opener.open(auth_url, timeout=timeout)
            loc = resp.headers.get("Location")
        except urllib.error.HTTPError as exc:
            loc = exc.headers.get("Location")
            if not loc:
                raise NetworkError(
                    f"Falha na autorização SLAS Telepizza (HTTP {exc.code}): {exc.reason}",
                    vendor=self.vendor,
                ) from exc
        except urllib.error.URLError as exc:
            raise NetworkError(f"Erro de rede ao autorizar SLAS Telepizza: {exc.reason}", vendor=self.vendor) from exc
        except TimeoutError as exc:
            raise NetworkError(f"Timeout ({timeout}s) ao autorizar SLAS Telepizza", vendor=self.vendor) from exc
        except OSError as exc:
            raise NetworkError(f"Erro de I/O ao autorizar SLAS Telepizza: {exc}", vendor=self.vendor) from exc

        if not loc:
            raise NetworkError("Resposta de autorização SLAS sem cabeçalho Location", vendor=self.vendor)

        parsed_loc = urllib.parse.urlparse(loc)
        query_params = urllib.parse.parse_qs(parsed_loc.query)
        auth_code_list = query_params.get("code")
        if not auth_code_list:
            raise NetworkError("Código de autorização ausente no redirecionamento SLAS", vendor=self.vendor)
        auth_code = auth_code_list[0]

        token_data = urllib.parse.urlencode({
            "grant_type": "authorization_code_pkce",
            "client_id": _CLIENT_ID,
            "code": auth_code,
            "code_verifier": code_verifier,
            "redirect_uri": _REDIRECT_URI,
            "channel_id": _SITE_ID,
        }).encode("utf-8")

        req = urllib.request.Request(
            _TOKEN_URL,
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as token_resp:
                token_body = token_resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise NetworkError(f"Falha ao obter token SLAS Telepizza (HTTP {exc.code}): {exc.reason}", vendor=self.vendor) from exc
        except urllib.error.URLError as exc:
            raise NetworkError(f"Erro de rede ao obter token SLAS Telepizza: {exc.reason}", vendor=self.vendor) from exc
        except TimeoutError as exc:
            raise NetworkError(f"Timeout ({timeout}s) ao obter token SLAS Telepizza", vendor=self.vendor) from exc
        except OSError as exc:
            raise NetworkError(f"Erro de I/O ao obter token SLAS Telepizza: {exc}", vendor=self.vendor) from exc

        try:
            token_json = json.loads(token_body)
            access_token = token_json.get("access_token")
            if not access_token:
                raise ParseError("Chave 'access_token' ausente na resposta SLAS", vendor=self.vendor)
            return access_token
        except json.JSONDecodeError as exc:
            raise ParseError(f"Resposta de token SLAS não é JSON válido: {exc}", vendor=self.vendor) from exc

    def discover_promotion_ids(
        self,
        token: str,
        timeout: float = DEFAULT_TIMEOUT,
        page_limit: int = 50,
        max_pages: int = 10,
    ) -> list[str]:
        """Tenta descobrir IDs de promoção dinamicamente através da Shopper Search API.

        Percorre o catálogo com expand=promotions e paginação. Se o catálogo não devolver
        productPromotions (uma vez que na Telepizza as ofertas operam como regras de cesto/campanha
        e não descontos estáticos de produto), utiliza deterministicamente a lista canónica
        DEFAULT_PROMOTION_IDS como bootstrap/fallback.
        """
        discovered_ids: set[str] = set()
        offset = 0

        for _ in range(max_pages):
            query = urllib.parse.urlencode({
                "siteId": _SITE_ID,
                "refine": "cgid=promocoes-pt",
                "expand": "promotions",
                "allVariationProperties": "true",
                "limit": page_limit,
                "offset": offset,
            })
            url = f"{_SEARCH_URL}?{query}"
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except Exception as exc:
                logger.warning("Falha na pesquisa Shopper Search da Telepizza (offset %d): %s", offset, exc)
                break

            hits = data.get("hits", [])
            for h in hits:
                if not isinstance(h, dict):
                    continue
                for key in ("productPromotions", "promotions", "representedProductPromotions"):
                    promos_field = h.get(key)
                    if isinstance(promos_field, list):
                        for p_obj in promos_field:
                            if isinstance(p_obj, dict):
                                p_id = p_obj.get("promotionId") or p_obj.get("id")
                                if p_id and str(p_id).strip():
                                    discovered_ids.add(str(p_id).strip())

            total = data.get("total", 0)
            offset += page_limit
            if offset >= total or not hits:
                break

        if discovered_ids:
            logger.info("Shopper Search descobriu %d promoção(ões) dinamicamente.", len(discovered_ids))
            return sorted(discovered_ids)

        logger.info(
            "Shopper Search não retornou productPromotions (as promoções Telepizza operam a nível de cesto/campanha na SCAPI). "
            "A utilizar lista canónica de campanhas oficiais (%d IDs).",
            len(DEFAULT_PROMOTION_IDS),
        )
        return list(DEFAULT_PROMOTION_IDS)

    def fetch_scapi_promotions(
        self,
        token: str,
        promo_ids: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        """Consulta as promoções ativas na Salesforce Shopper Promotions API em lotes de até 50 IDs."""
        ids = promo_ids if promo_ids is not None else self.discover_promotion_ids(token, timeout=timeout)
        if not ids:
            return {"limit": 0, "total": 0, "data": []}

        all_data: list[dict[str, Any]] = []
        chunk_size = 50

        for i in range(0, len(ids), chunk_size):
            chunk = ids[i : i + chunk_size]
            promo_ids_str = ",".join(chunk)
            query = urllib.parse.urlencode({"siteId": _SITE_ID, "ids": promo_ids_str})
            url = f"{_PROMOTIONS_URL}?{query}"

            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                raise NetworkError(
                    f"HTTP {exc.code} ao consultar promoções SCAPI Telepizza: {exc.reason}",
                    vendor=self.vendor,
                ) from exc
            except urllib.error.URLError as exc:
                raise NetworkError(f"Erro de rede ao consultar promoções SCAPI Telepizza: {exc.reason}", vendor=self.vendor) from exc
            except TimeoutError as exc:
                raise NetworkError(f"Timeout ({timeout}s) ao consultar promoções SCAPI Telepizza", vendor=self.vendor) from exc
            except OSError as exc:
                raise NetworkError(f"Erro de I/O ao consultar promoções SCAPI Telepizza: {exc}", vendor=self.vendor) from exc

            try:
                parsed_chunk = json.loads(body, parse_float=Decimal)
            except json.JSONDecodeError as exc:
                raise ParseError(f"Resposta de promoções SCAPI Telepizza não é JSON válido: {exc}", vendor=self.vendor) from exc

            chunk_items = parsed_chunk.get("data", [])
            if isinstance(chunk_items, list):
                all_data.extend(chunk_items)

        return {"limit": len(all_data), "total": len(all_data), "data": all_data}

    def fetch_raw(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
    ) -> str:
        """Efetua pedido GET HTTP para a página oficial da Telepizza (suporte legado / fallback)."""
        req = urllib.request.Request(_URL, headers=_HEADERS, method="GET")
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw_bytes = resp.read()
                return raw_bytes.decode("utf-8", errors="replace")
            except (http.client.RemoteDisconnected, ConnectionResetError) as exc:
                last_exc = exc
                logger.warning("Tentativa %d/%d de recolha da Telepizza falhou: %s", attempt, max_retries, exc)
                if attempt < max_retries:
                    time.sleep(attempt * 1.5)
            except urllib.error.HTTPError as exc:
                raise NetworkError(f"HTTP {exc.code} ao aceder a {_URL}: {exc.reason}", vendor=self.vendor) from exc
            except urllib.error.URLError as exc:
                last_exc = exc
                logger.warning("Tentativa %d/%d de recolha da Telepizza falhou: %s", attempt, max_retries, exc.reason)
                if attempt < max_retries:
                    time.sleep(attempt * 1.5)
            except TimeoutError as exc:
                raise NetworkError(f"Timeout ({timeout}s) ao aceder a {_URL}", vendor=self.vendor) from exc
            except OSError as exc:
                last_exc = exc
                logger.warning("Tentativa %d/%d de recolha da Telepizza falhou: %s", attempt, max_retries, exc)
                if attempt < max_retries:
                    time.sleep(attempt * 1.5)

        raise NetworkError(
            f"Falha após {max_retries} tentativas ao aceder a {_URL}: {last_exc}",
            vendor=self.vendor,
        ) from last_exc

    def parse_scapi(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Extrai as promoções estruturadas da resposta SCAPI com tolerância por item."""
        data_list = raw.get("data", [])
        if not isinstance(data_list, list):
            raise ParseError("Chave 'data' de promoções SCAPI não é uma lista", vendor=self.vendor)

        parsed: list[dict[str, Any]] = []
        for idx, item in enumerate(data_list):
            if not isinstance(item, dict):
                logger.warning("Item %d de data SCAPI da Telepizza não é um dicionário", idx)
                continue
            promo_id = item.get("id")
            name = item.get("name")
            if not promo_id or not name:
                logger.warning("Item %d da Telepizza com id ou name ausentes: %r", idx, item)
                continue

            clean_name = html.unescape(str(name)).strip()
            callout = item.get("callout_msg") or item.get("calloutMsg") or ""
            clean_callout = html.unescape(str(callout)).strip()
            details = item.get("details") or ""
            clean_details = html.unescape(str(details)).strip()

            price_cents = None
            if "c_tpz_promoFixedPrice" in item and item["c_tpz_promoFixedPrice"] is not None:
                try:
                    d_price = Decimal(str(item["c_tpz_promoFixedPrice"]))
                    price_cents = int((d_price * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                except (InvalidOperation, ValueError):
                    price_cents = None

            if price_cents is None:
                price_cents = _extract_cents_from_text(clean_name) or _extract_cents_from_text(clean_callout)

            discount_pct = _extract_discount_percentage(clean_name) or _extract_discount_percentage(clean_callout)

            is_del = bool(item.get("c_tpz_isDelivery", False))
            is_tk = bool(item.get("c_tpz_isTakeAway", False))
            channels: list[str] = []
            if is_del:
                channels.append("delivery")
            if is_tk:
                channels.append("takeaway")

            if not channels:
                lower_text = f"{clean_name} {clean_callout}".lower()
                if "takeaway" in lower_text or "take away" in lower_text or "loja" in lower_text:
                    channels.append("takeaway")
                if "domicilio" in lower_text or "domicílio" in lower_text or "entrega" in lower_text:
                    channels.append("delivery")

            if not channels:
                # Se ainda sem canal comprovado, atribuir ambos como padrão de oferta nacional
                channels = ["delivery", "takeaway"]

            days_raw = item.get("c_tpz_daysOfWeek", [])
            days_of_week: list[Weekday] = []
            if isinstance(days_raw, list) and 0 < len(days_raw) < 7:
                _DAY_MAP = {
                    "0": Weekday.SUNDAY,
                    "1": Weekday.MONDAY,
                    "2": Weekday.TUESDAY,
                    "3": Weekday.WEDNESDAY,
                    "4": Weekday.THURSDAY,
                    "5": Weekday.FRIDAY,
                    "6": Weekday.SATURDAY,
                }
                for d_code in days_raw:
                    w_day = _DAY_MAP.get(str(d_code).strip())
                    if w_day and w_day not in days_of_week:
                        days_of_week.append(w_day)

            pizza_count = None
            if "2x1" in clean_name.lower() and ("pizza" in clean_name.lower() or "médias" in clean_name.lower() or "medias" in clean_name.lower()):
                pizza_count = 2
            else:
                m_count = _PIZZA_COUNT_REGEX.search(f"{clean_name} {clean_callout}")
                if m_count:
                    try:
                        pizza_count = int(m_count.group(1))
                    except ValueError:
                        pizza_count = None

            image_url = (
                item.get("c_tpz_mobileImage")
                or item.get("image")
                or item.get("c_tpz_promoMinicartImage")
            )
            if image_url and not str(image_url).startswith(("http://", "https://")):
                image_url = None

            parsed.append({
                "id": str(promo_id).strip(),
                "title": clean_name,
                "description": clean_callout,
                "conditions": clean_details or clean_callout,
                "price_cents": price_cents,
                "discount_percentage": discount_pct,
                "channels": channels,
                "days_of_week": days_of_week,
                "pizza_count": pizza_count,
                "image_url": str(image_url) if image_url else None,
                "store_scope": StoreScope.UNKNOWN,
                "store_ids": [],
                "store_names": [],
                "valid_from": item.get("startDate"),
                "valid_until": item.get("endDate"),
            })

        if data_list and not parsed:
            raise ParseError("Nenhuma promoção válida pôde ser extraída da SCAPI da Telepizza", vendor=self.vendor)

        return parsed

    def parse_html(self, raw_html: str) -> list[dict[str, Any]]:
        """Extrai os cartões promocionais do HTML usando TelepizzaHTMLParser (suporte legado / fixtures)."""
        if not isinstance(raw_html, str):
            raise ParseError("Payload bruto de Telepizza não é texto HTML", vendor=self.vendor)

        parser = TelepizzaHTMLParser()
        try:
            parser.feed(raw_html)
        except Exception as exc:
            raise ParseError(f"Falha de parsing HTML na Telepizza: {exc}", vendor=self.vendor) from exc

        if not parser.cards:
            raise ParseError("Nenhum cartão promocional encontrado no HTML da Telepizza", vendor=self.vendor)

        parsed: list[dict[str, Any]] = []
        for card in parser.cards:
            card_id = card.get("id")
            raw_name = card.get("name") or ""
            raw_detail = card.get("detail") or ""
            img_url = card.get("img_url")
            tab_content = card.get("tab_content") or ""

            if not card_id or not raw_name.strip():
                logger.warning("Cartão da Telepizza ignorado: id ou nome ausentes (id=%r)", card_id)
                continue

            clean_name = html.unescape(raw_name).strip()
            clean_detail = html.unescape(raw_detail).strip()

            tab_lower = tab_content.lower()
            text_lower = f"{clean_name} {clean_detail}".lower()
            channels: list[str] = []

            has_delivery = "delivery" in tab_lower or "entrega" in text_lower or "domicílio" in text_lower or "domicilio" in text_lower
            has_takeaway = "takeaway" in tab_lower or "take_away" in tab_lower or "balcão" in text_lower or "balcao" in text_lower or "levantamento" in text_lower

            if has_delivery:
                channels.append("delivery")
            if has_takeaway:
                channels.append("takeaway")

            if not channels:
                logger.warning("Oferta %s da Telepizza ignorada: sem canal comprovado", card_id)
                continue

            price_cents = _extract_cents_from_text(clean_name) or _extract_cents_from_text(clean_detail)

            parsed.append({
                "id": str(card_id),
                "title": clean_name,
                "description": clean_detail,
                "conditions": clean_detail,
                "price_cents": price_cents,
                "discount_percentage": _extract_discount_percentage(clean_name) or _extract_discount_percentage(clean_detail),
                "channels": channels,
                "days_of_week": [],
                "pizza_count": 2 if "2x1" in clean_name.lower() else None,
                "image_url": img_url,
                "store_scope": StoreScope.UNKNOWN,
                "store_ids": [],
                "store_names": [],
            })

        if parser.cards and not parsed:
            raise ParseError("Nenhum cartão válido da Telepizza pôde ser extraído do HTML", vendor=self.vendor)

        return parsed

    def parse(self, raw: str | dict[str, Any]) -> list[dict[str, Any]]:
        """Polimorfismo para parsear tanto resposta SCAPI (dict) como HTML legado (str)."""
        if isinstance(raw, dict):
            return self.parse_scapi(raw)
        elif isinstance(raw, str):
            return self.parse_html(raw)
        raise ParseError(f"Tipo inesperado para payload da Telepizza: {type(raw).__name__}", vendor=self.vendor)

    def adapt(
        self,
        item: dict[str, Any],
        observed_at: datetime,
        channel: str | None = None,
    ) -> UnifiedPromo | list[UnifiedPromo]:
        """Normaliza item para UnifiedPromo com respeito estrito aos canais e tipagem."""
        if observed_at.tzinfo is None:
            raise ValueError(f"observed_at deve ser timezone-aware, recebido: {observed_at!r}")

        title = item["title"]
        description = item["description"]
        price_cents = item["price_cents"]
        discount_pct = item.get("discount_percentage")

        title_lower = title.lower()
        desc_lower = description.lower()

        if discount_pct:
            discount_type = DiscountType.PERCENTAGE
        elif "2x1" in title_lower or "2x1" in desc_lower or "2 por 1" in title_lower:
            discount_type = DiscountType.X_FOR_Y
        else:
            discount_type = DiscountType.SPECIAL_MENU

        # Deteção de dias temáticos
        days_of_week: list[Weekday] = list(item.get("days_of_week") or [])
        if not days_of_week:
            if "terça" in title_lower or "terca" in title_lower:
                days_of_week = [Weekday.TUESDAY]
            elif "quinta" in title_lower:
                days_of_week = [Weekday.THURSDAY]

        image_url = item.get("image_url")
        if image_url and not str(image_url).startswith(("http://", "https://")):
            image_url = None

        offer_type = classify_offer_type(
            title=title,
            description=description,
            included_items=[],
            pizza_count=item.get("pizza_count"),
        )

        channels_to_create = [channel] if channel is not None else item.get("channels", ["delivery"])

        promos: list[UnifiedPromo] = []
        for ch in channels_to_create:
            dispatch_method = DispatchMethod.DELIVERY if ch == "delivery" else DispatchMethod.TAKE_AWAY
            canonical_id = f"tp_{item['id']}_{ch}"

            promos.append(
                UnifiedPromo(
                    id=canonical_id,
                    vendor=Brand.TELEPIZZA,
                    title=title,
                    description=description,
                    observed_at=observed_at.isoformat(),
                    price_cents=price_cents,
                    discount_type=discount_type,
                    discount_percentage=discount_pct,
                    conditions=item.get("conditions", description),
                    days_of_week=days_of_week,
                    dispatch_methods=[dispatch_method],
                    store_scope=StoreScope.UNKNOWN,
                    store_ids=[],
                    store_names=[],
                    pizza_count=item.get("pizza_count"),
                    pizza_size=PizzaSize.UNKNOWN,
                    included_items=[],
                    image_url=image_url,
                    source_url=_URL,
                    location_scope="Lisboa",
                    offer_type=offer_type,
                    valid_from=item.get("valid_from"),
                    valid_until=item.get("valid_until"),
                )
            )

        if channel is not None:
            return promos[0]
        return promos

    def fetch_promotions(self, timeout: float = DEFAULT_TIMEOUT) -> list[UnifiedPromo]:
        """Recolhe promoções oficiais da Telepizza através da Salesforce SCAPI."""
        observed_at = datetime.now(tz=timezone.utc)
        token = self.fetch_slas_token(timeout=timeout)
        raw_scapi = self.fetch_scapi_promotions(token=token, timeout=timeout)
        parsed = self.parse_scapi(raw_scapi)

        promos: list[UnifiedPromo] = []
        seen_ids: set[str] = set()

        for it in parsed:
            adapted = self.adapt(it, observed_at)
            items_list = adapted if isinstance(adapted, list) else [adapted]
            for promo in items_list:
                if promo.id not in seen_ids:
                    seen_ids.add(promo.id)
                    promos.append(promo)

        self.coverage_level = "FEATURED"
        self.coverage_note = (
            "Campanhas principais sincronizadas via API oficial Salesforce (amostra de 20 campanhas ativas)"
        )
        return self.validate_and_filter(promos)
