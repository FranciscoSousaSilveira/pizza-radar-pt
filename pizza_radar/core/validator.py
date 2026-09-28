"""Validador determinístico do esquema unificado de promoções."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pizza_radar.core.models import (
    Brand,
    DispatchMethod,
    DiscountType,
    TargetAudience,
    UnifiedPromo,
    Weekday,
)


class ValidationError(Exception):
    """Exceção levantada quando um registo de promoção viola o contrato canónico."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or [message]


def _parse_iso_date(value: str, field_name: str) -> datetime:
    """Valida se uma string segue o formato ISO 8601."""
    try:
        # datetime.fromisoformat aceita formatos como 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SS', etc.
        return datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"O campo '{field_name}' deve ser uma data/hora ISO 8601 válida. Valor recebido: {value!r}"
        ) from exc


def validate_promo(item: UnifiedPromo | dict[str, Any]) -> UnifiedPromo:
    """Valida exaustivamente um registo promocional face ao contrato canónico.

    Recebe uma instância de `UnifiedPromo` ou um dicionário e devolve a instância validada.
    Lança `ValidationError` se encontrar qualquer incongruência.
    """
    errors: list[str] = []

    # Se for dicionário, tenta instanciar para apanhar conversões elementares
    if isinstance(item, dict):
        try:
            promo = UnifiedPromo.from_dict(item)
        except Exception as exc:
            raise ValidationError(
                f"Falha ao desserializar dicionário para UnifiedPromo: {exc}",
                errors=[str(exc)],
            ) from exc
    elif isinstance(item, UnifiedPromo):
        promo = item
    else:
        raise ValidationError(
            f"Tipo de objeto inválido para validação: esperado UnifiedPromo ou dict, recebido {type(item).__name__}",
            errors=[f"Tipo inválido: {type(item).__name__}"],
        )

    # 1. Identificador único
    if not promo.id or not isinstance(promo.id, str) or not promo.id.strip():
        errors.append("O campo 'id' é obrigatório e deve ser uma string não vazia.")

    # 2. Marca / Vendedor
    if not isinstance(promo.vendor, Brand):
        errors.append(f"O campo 'vendor' deve ser um dos valores válidos de Brand: {[b.value for b in Brand]}.")

    # 3. Título
    if not promo.title or not isinstance(promo.title, str) or not promo.title.strip():
        errors.append("O campo 'title' é obrigatório e deve ser uma string não vazia.")

    # 4. Âmbito Geográfico (estrito ao concelho de Lisboa no MVP)
    if promo.location_scope != "Lisboa":
        errors.append(
            f"O campo 'location_scope' deve ser estritamente 'Lisboa'. Valor recebido: {promo.location_scope!r}"
        )

    # 5. Preços e Descontos
    if promo.price is not None:
        if not isinstance(promo.price, (int, float)):
            errors.append("O campo 'price' deve ser numérico.")
        elif promo.price < 0:
            errors.append(f"O campo 'price' não pode ser negativo. Valor: {promo.price}")

    if promo.original_price is not None:
        if not isinstance(promo.original_price, (int, float)):
            errors.append("O campo 'original_price' deve ser numérico.")
        elif promo.original_price < 0:
            errors.append(f"O campo 'original_price' não pode ser negativo. Valor: {promo.original_price}")

    if (
        promo.price is not None
        and promo.original_price is not None
        and isinstance(promo.price, (int, float))
        and isinstance(promo.original_price, (int, float))
    ):
        if promo.price > promo.original_price:
            errors.append(
                f"O preço promocional ({promo.price}€) não pode ser superior ao preço original ({promo.original_price}€)."
            )

    if promo.discount_percentage is not None:
        if not isinstance(promo.discount_percentage, (int, float)):
            errors.append("O campo 'discount_percentage' deve ser numérico.")
        elif not (0.0 <= float(promo.discount_percentage) <= 100.0):
            errors.append(
                f"O campo 'discount_percentage' deve situar-se entre 0 e 100. Valor: {promo.discount_percentage}"
            )

    # 6. Modalidades de atendimento (dispatch_methods)
    if not promo.dispatch_methods or not isinstance(promo.dispatch_methods, list):
        errors.append("O campo 'dispatch_methods' deve ser uma lista não vazia.")
    else:
        for method in promo.dispatch_methods:
            if not isinstance(method, DispatchMethod):
                errors.append(
                    f"Método de entrega inválido: {method!r}. Valores permitidos: {[m.value for m in DispatchMethod]}."
                )

    # 7. Datas de validade
    valid_from_dt: datetime | None = None
    valid_until_dt: datetime | None = None

    if promo.valid_from:
        try:
            valid_from_dt = _parse_iso_date(promo.valid_from, "valid_from")
        except ValueError as exc:
            errors.append(str(exc))

    if promo.valid_until:
        try:
            valid_until_dt = _parse_iso_date(promo.valid_until, "valid_until")
        except ValueError as exc:
            errors.append(str(exc))

    if valid_from_dt and valid_until_dt and valid_from_dt > valid_until_dt:
        errors.append(
            f"A data 'valid_from' ({promo.valid_from}) não pode ser posterior a 'valid_until' ({promo.valid_until})."
        )

    # 8. Carimbo de recolha (scraped_at)
    if promo.scraped_at:
        try:
            _parse_iso_date(promo.scraped_at, "scraped_at")
        except ValueError as exc:
            errors.append(str(exc))

    # 9. URL da fonte
    if promo.source_url:
        parsed = urlparse(promo.source_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append(
                f"O campo 'source_url' deve ser um URL válido com esquema http ou https. Valor: {promo.source_url!r}"
            )

    # 10. URL de imagem (se fornecido)
    if promo.image_url:
        parsed_img = urlparse(promo.image_url)
        if parsed_img.scheme not in ("http", "https") or not parsed_img.netloc:
            errors.append(
                f"O campo 'image_url' deve ser um URL válido com esquema http ou https. Valor: {promo.image_url!r}"
            )

    if errors:
        raise ValidationError(
            f"Falha na validação de UnifiedPromo (id={promo.id!r}): {len(errors)} erro(s) detetado(s).",
            errors=errors,
        )

    return promo


def validate_promos(items: list[UnifiedPromo | dict[str, Any]]) -> list[UnifiedPromo]:
    """Valida uma lista de promoções de forma determinística."""
    validated: list[UnifiedPromo] = []
    all_errors: list[str] = []

    for index, item in enumerate(items):
        try:
            validated.append(validate_promo(item))
        except ValidationError as exc:
            for err in exc.errors:
                all_errors.append(f"[Item {index}] {err}")

    if all_errors:
        raise ValidationError(
            f"Falha na validação em lote ({len(all_errors)} erros em {len(items)} itens).",
            errors=all_errors,
        )

    return validated
