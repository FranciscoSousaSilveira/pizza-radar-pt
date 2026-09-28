"""Validador determinístico do esquema canónico de promoções."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pizza_radar.core.models import (
    Brand,
    ComponentCategory,
    DispatchMethod,
    OfferComponent,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
)


class ValidationError(Exception):
    """Exceção levantada quando um registo de promoção viola o contrato canónico."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or [message]


def _parse_iso_date(value: str, field_name: str, require_timezone: bool = False) -> datetime:
    """Valida se uma string segue o formato ISO 8601 e opcionalmente exige fuso horário."""
    try:
        # Substitui 'Z' por '+00:00' para compatibilidade total com fromisoformat em Python < 3.11/3.12
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"O campo '{field_name}' deve ser uma data/hora ISO 8601 válida. Valor recebido: {value!r}"
        ) from exc

    if require_timezone and dt.tzinfo is None:
        raise ValueError(
            f"O campo '{field_name}' deve ser obrigatoriamente timezone-aware (com offset UTC ou fuso horário explícito). Valor recebido: {value!r}"
        )

    return dt


def validate_promo(item: UnifiedPromo | dict[str, Any]) -> UnifiedPromo:
    """Valida exaustivamente um registo promocional face ao contrato canónico.

    Recebe uma instância de `UnifiedPromo` ou um dicionário e devolve a instância validada.
    Lança `ValidationError` se encontrar qualquer incongruência.
    """
    errors: list[str] = []

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

    # 4. Temporalidade e Auditoria (observed_at é estritamente obrigatório e timezone-aware)
    if not promo.observed_at or not isinstance(promo.observed_at, str) or not promo.observed_at.strip():
        errors.append("O campo 'observed_at' é obrigatório e deve registar o instante exato da observação.")
    else:
        try:
            _parse_iso_date(promo.observed_at, "observed_at", require_timezone=True)
        except ValueError as exc:
            errors.append(str(exc))

    if promo.last_seen_at:
        try:
            _parse_iso_date(promo.last_seen_at, "last_seen_at", require_timezone=True)
        except ValueError as exc:
            errors.append(str(exc))

    # 5. Datas de validade anunciadas pela marca
    valid_from_dt: datetime | None = None
    valid_until_dt: datetime | None = None

    if promo.valid_from:
        try:
            valid_from_dt = _parse_iso_date(promo.valid_from, "valid_from", require_timezone=False)
        except ValueError as exc:
            errors.append(str(exc))

    if promo.valid_until:
        try:
            valid_until_dt = _parse_iso_date(promo.valid_until, "valid_until", require_timezone=False)
        except ValueError as exc:
            errors.append(str(exc))

    if valid_from_dt and valid_until_dt and valid_from_dt > valid_until_dt:
        errors.append(
            f"A data 'valid_from' ({promo.valid_from}) não pode ser posterior a 'valid_until' ({promo.valid_until})."
        )

    # 6. Dinheiro Determinístico (integer cents)
    if promo.price_cents is not None:
        if not isinstance(promo.price_cents, int) or isinstance(promo.price_cents, bool):
            errors.append(
                f"O campo 'price_cents' deve ser um número inteiro de cêntimos (int). Tipo recebido: {type(promo.price_cents).__name__}."
            )
        elif promo.price_cents < 0:
            errors.append(f"O campo 'price_cents' não pode ser negativo. Valor: {promo.price_cents}")

    if promo.original_price_cents is not None:
        if not isinstance(promo.original_price_cents, int) or isinstance(promo.original_price_cents, bool):
            errors.append(
                f"O campo 'original_price_cents' deve ser um número inteiro de cêntimos (int). Tipo recebido: {type(promo.original_price_cents).__name__}."
            )
        elif promo.original_price_cents < 0:
            errors.append(f"O campo 'original_price_cents' não pode ser negativo. Valor: {promo.original_price_cents}")

    if (
        promo.price_cents is not None
        and promo.original_price_cents is not None
        and isinstance(promo.price_cents, int)
        and isinstance(promo.original_price_cents, int)
        and not isinstance(promo.price_cents, bool)
        and not isinstance(promo.original_price_cents, bool)
    ):
        if promo.price_cents > promo.original_price_cents:
            errors.append(
                f"O preço promocional ({promo.price_cents} cêntimos) não pode ser superior ao preço original ({promo.original_price_cents} cêntimos)."
            )

    if promo.discount_percentage is not None:
        if not isinstance(promo.discount_percentage, (int, float)) or isinstance(promo.discount_percentage, bool):
            errors.append("O campo 'discount_percentage' deve ser numérico.")
        elif not (0.0 <= float(promo.discount_percentage) <= 100.0):
            errors.append(
                f"O campo 'discount_percentage' deve situar-se entre 0 e 100. Valor: {promo.discount_percentage}"
            )

    # 7. Âmbito Geográfico e Lojas
    if promo.location_scope != "Lisboa":
        errors.append(
            f"O campo 'location_scope' deve ser estritamente 'Lisboa'. Valor recebido: {promo.location_scope!r}"
        )

    if not isinstance(promo.store_scope, StoreScope):
        errors.append(
            f"O campo 'store_scope' deve ser um valor válido de StoreScope: {[s.value for s in StoreScope]}."
        )
    elif promo.store_scope == StoreScope.SPECIFIC_STORES:
        if not promo.store_ids and not promo.store_names:
            errors.append(
                "Ofertas com 'store_scope=SPECIFIC_STORES' devem listar pelo menos um identificador ou nome de loja em 'store_ids' ou 'store_names'."
            )

    # 8. Conteúdo da Oferta e Componentes (sem valores inventados)
    if promo.pizza_count is not None:
        if not isinstance(promo.pizza_count, int) or isinstance(promo.pizza_count, bool):
            errors.append(
                f"O campo 'pizza_count' deve ser um número inteiro positivo (int). Tipo recebido: {type(promo.pizza_count).__name__}."
            )
        elif promo.pizza_count <= 0:
            errors.append(f"O campo 'pizza_count' deve ser estritamente superior a zero. Valor: {promo.pizza_count}")

    if not isinstance(promo.pizza_size, PizzaSize):
        errors.append(
            f"O campo 'pizza_size' deve ser um valor válido de PizzaSize: {[s.value for s in PizzaSize]}."
        )

    if promo.included_items:
        for idx, item_comp in enumerate(promo.included_items):
            if not isinstance(item_comp, OfferComponent):
                errors.append(f"Elemento {idx} de 'included_items' deve ser uma instância de OfferComponent.")
            elif item_comp.quantity < 1:
                errors.append(f"Elemento {idx} de 'included_items' tem quantidade inválida ({item_comp.quantity} < 1).")

    # 9. Modalidades de atendimento (dispatch_methods)
    if not promo.dispatch_methods or not isinstance(promo.dispatch_methods, list):
        errors.append("O campo 'dispatch_methods' deve ser uma lista não vazia.")
    else:
        for method in promo.dispatch_methods:
            if not isinstance(method, DispatchMethod):
                errors.append(
                    f"Método de entrega inválido: {method!r}. Valores permitidos: {[m.value for m in DispatchMethod]}."
                )

    # 10. URLs (fonte e imagem)
    if promo.source_url:
        parsed = urlparse(promo.source_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append(
                f"O campo 'source_url' deve ser um URL válido com esquema http ou https. Valor: {promo.source_url!r}"
            )

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
