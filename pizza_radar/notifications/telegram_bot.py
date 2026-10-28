"""Bot de notificações de alertas e promoções do Pizza Radar PT via Telegram Bot API.

Utiliza a API pública e gratuita do Telegram (https://api.telegram.org/bot<TOKEN>/sendMessage)
para publicar destaques das melhores promoções do dia no concelho de Lisboa:
- Seleção determinística das melhores ofertas (melhor preço absoluto, maior desconto e melhor preço unitário / custo benefício).
- Mensagens formatadas em Markdown com nome da marca, percentagem de desconto, preço atual vs original, validade e link oficial.
- Suporta envio real quando TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID estão configurados.
- Modo simulação (dry-run) automático e seguro quando as credenciais não estão presentes.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Sequence

from pizza_radar.core.models import Brand, OfferType, UnifiedPromo
from pizza_radar.engine.identity import VisualPromoGroup

logger = logging.getLogger("pizza_radar.notifications.telegram")

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

VENDOR_NAMES: dict[Brand | str, str] = {
    Brand.DOMINOS: "Domino's Pizza",
    Brand.PAPA_JOHNS: "Papa John's",
    Brand.PIZZA_HUT: "Pizza Hut",
    Brand.TELEPIZZA: "Telepizza",
    "DOMINOS": "Domino's Pizza",
    "PAPA_JOHNS": "Papa John's",
    "PIZZA_HUT": "Pizza Hut",
    "TELEPIZZA": "Telepizza",
}


@dataclass(frozen=True)
class TelegramDispatchResult:
    """Resultado do envio de notificação via Telegram."""

    success: bool
    mode: str  # "sent" | "simulated" | "failed"
    message_text: str
    chat_id: str | None = None
    response_status: int | None = None
    error_message: str | None = None


def select_daily_highlights(
    promotions: Sequence[UnifiedPromo | VisualPromoGroup | dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Seleciona deterministicamente as melhores ofertas do dia para o boletim de alertas."""
    normalized: list[dict[str, Any]] = []

    for item in promotions:
        if isinstance(item, dict):
            vendor = item.get("vendor", "")
            title = item.get("title", "")
            price_cents = item.get("min_price_cents") or item.get("price_cents")
            discount_pct = item.get("max_discount_percentage") or item.get("discount_percentage") or 0
            unit_price_cents = item.get("min_price_per_pizza_cents") or item.get("price_per_pizza_cents")
            source_url = item.get("source_url") or "https://pizzaradar.pt"
            offer_type = item.get("offer_type", "PIZZA")
            value_metrics = item.get("value_metrics")
        elif isinstance(item, VisualPromoGroup):
            vendor = item.vendor.value if hasattr(item.vendor, "value") else str(item.vendor)
            title = item.title
            price_cents = item.min_price_cents
            discount_pct = item.max_discount_percentage or 0
            unit_price_cents = item.min_price_per_pizza_cents
            source_url = item.source_url
            offer_type = item.offer_type.value if hasattr(item.offer_type, "value") else str(item.offer_type)
            value_metrics = None
        elif isinstance(item, UnifiedPromo):
            vendor = item.vendor.value if hasattr(item.vendor, "value") else str(item.vendor)
            title = item.title
            price_cents = item.price_cents
            discount_pct = item.discount_percentage or 0
            unit_price_cents = item.price_per_pizza_cents
            source_url = item.source_url
            offer_type = item.offer_type.value if hasattr(item.offer_type, "value") else str(item.offer_type)
            value_metrics = None
        else:
            continue

        # Apenas ofertas relevantes de pizza
        if offer_type in ("PIZZA", "BUNDLE_WITH_PIZZA") and price_cents:
            normalized.append({
                "vendor": vendor,
                "title": title,
                "price_cents": price_cents,
                "price_euros": f"{price_cents / 100:.2f}".replace(".", ",") + " €",
                "discount_pct": int(discount_pct) if discount_pct else 0,
                "unit_price_cents": unit_price_cents,
                "unit_price_euros": f"{unit_price_cents / 100:.2f}".replace(".", ",") + " €" if unit_price_cents else None,
                "source_url": source_url,
                "value_metrics": value_metrics,
            })

    if not normalized:
        return []

    # 1. Oferta com maior percentagem de desconto
    sorted_by_discount = sorted(normalized, key=lambda x: (-x["discount_pct"], x["price_cents"]))
    # 2. Oferta mais barata absoluta
    sorted_by_price = sorted(normalized, key=lambda x: x["price_cents"])
    # 3. Oferta com melhor preço unitário
    comparables = [x for x in normalized if x["unit_price_cents"]]
    sorted_by_unit = sorted(comparables, key=lambda x: x["unit_price_cents"]) if comparables else []

    selected: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for candidate_list in (sorted_by_discount, sorted_by_price, sorted_by_unit, normalized):
        for item in candidate_list:
            key = f"{item['vendor']}:{item['title']}"
            if key not in seen_titles:
                seen_titles.add(key)
                selected.append(item)
                if len(selected) >= limit:
                    return selected

    return selected[:limit]


def format_telegram_alert_message(highlights: list[dict[str, Any]]) -> str:
    """Formata a mensagem Markdown para o canal ou bot do Telegram."""
    lines = [
        "🍕 *PIZZA RADAR LISBOA — DESTAQUES DO DIA*",
        "As melhores ofertas confirmadas hoje em Lisboa:\n",
    ]

    for idx, item in enumerate(highlights, start=1):
        brand_name = VENDOR_NAMES.get(item["vendor"], item["vendor"])
        title = item["title"]
        price = item["price_euros"]
        disc_text = f" (-{item['discount_pct']}%)" if item["discount_pct"] > 0 else ""
        unit_text = f" • *{item['unit_price_euros']} / pizza*" if item.get("unit_price_euros") else ""
        url = item.get("source_url") or "https://pizzaradar.pt"

        lines.append(f"{idx}. *{brand_name}* — {title}")
        lines.append(f"   💰 Preço: *{price}*{disc_text}{unit_text}")
        if item.get("value_metrics") and item["value_metrics"].get("value_badge_label"):
            lines.append(f"   📏 Índice: _{item['value_metrics']['value_badge_label']}_")
        lines.append(f"   🔗 [Ver oferta]({url})\n")

    lines.append("⚡ _Atualizado deterministicamente pelo Pizza Radar PT_")
    lines.append("🌐 Consulta o radar completo e lojas abertas em: https://pizzaradar.pt")
    return "\n".join(lines)


def dispatch_daily_highlights(
    promotions: Sequence[UnifiedPromo | VisualPromoGroup | dict[str, Any]],
    bot_token: str | None = None,
    chat_id: str | None = None,
    limit: int = 3,
    timeout: float = 10.0,
) -> TelegramDispatchResult:
    """Envia o alerta diário de promoções para o Telegram se as credenciais estiverem disponíveis.

    Se as credenciais não estiverem definidas, executa em modo simulação sem falhar a pipeline.
    """
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    target_chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    highlights = select_daily_highlights(promotions, limit=limit)
    if not highlights:
        logger.warning("Nenhuma promoção elegível encontrada para envio no Telegram.")
        return TelegramDispatchResult(
            success=True,
            mode="simulated",
            message_text="Sem promoções ativas para o boletim.",
        )

    message_text = format_telegram_alert_message(highlights)

    if not token or not target_chat:
        logger.info(
            "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados. Boletim gerado em modo simulação:\n%s",
            message_text,
        )
        return TelegramDispatchResult(
            success=True,
            mode="simulated",
            message_text=message_text,
            chat_id=target_chat or None,
        )

    # Disparo real via API do Telegram
    api_url = TELEGRAM_API_URL.format(token=token)
    payload = {
        "chat_id": target_chat,
        "text": message_text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }

    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            body = resp.read().decode("utf-8")
        logger.info("Alerta de promoções enviado com sucesso para o Telegram (chat_id: %s)", target_chat)
        return TelegramDispatchResult(
            success=True,
            mode="sent",
            message_text=message_text,
            chat_id=target_chat,
            response_status=status_code,
        )
    except urllib.error.HTTPError as exc:
        err_msg = f"HTTP {exc.code}: {exc.reason}"
        logger.error("Falha ao enviar alerta para Telegram: %s", err_msg)
        return TelegramDispatchResult(
            success=False,
            mode="failed",
            message_text=message_text,
            chat_id=target_chat,
            response_status=exc.code,
            error_message=err_msg,
        )
    except Exception as exc:
        err_msg = str(exc)
        logger.error("Erro inesperado ao enviar alerta para Telegram: %s", err_msg)
        return TelegramDispatchResult(
            success=False,
            mode="failed",
            message_text=message_text,
            chat_id=target_chat,
            error_message=err_msg,
        )
