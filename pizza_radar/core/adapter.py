"""Interface e exceções padronizadas para adaptadores de vendedores."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pizza_radar.core.models import Brand, UnifiedPromo
from pizza_radar.core.validator import validate_promos


class AdapterError(Exception):
    """Exceção base para erros durante a execução de um adaptador."""

    def __init__(self, message: str, vendor: Brand | None = None) -> None:
        super().__init__(message)
        self.vendor = vendor


class NetworkError(AdapterError):
    """Erro de comunicação HTTP, timeout ou indisponibilidade de rede."""


class ParseError(AdapterError):
    """Erro de parsing da resposta recebida (estrutura HTML ou JSON inesperada)."""


class RateLimitError(AdapterError):
    """Sinalização de rate limit ou throttling no endpoint público."""


class PromoAdapterInterface(ABC):
    """Contrato base abstrato para todos os adaptadores de recolha promocional.

    Cada vendedor suportado (Domino's, Pizza Hut, Telepizza, Papa John's)
    deve implementar esta interface, assegurando que o método `fetch_promotions`
    produz dados estritamente normalizados no formato `UnifiedPromo`.
    """

    @property
    @abstractmethod
    def vendor(self) -> Brand:
        """Identificador da marca correspondente a este adaptador."""

    @abstractmethod
    def fetch_promotions(self, timeout: float = 10.0) -> list[UnifiedPromo]:
        """Obtém e normaliza as promoções em vigor no concelho de Lisboa.

        Args:
            timeout: Tempo limite em segundos para requisições de rede.

        Returns:
            Lista de promoções conformes ao contrato UnifiedPromo.

        Raises:
            NetworkError: Em caso de falha de conexão ou timeout.
            ParseError: Em caso de resposta corrompida ou alteração drástica de layout.
            AdapterError: Para outros erros genéricos de execução.
        """

    def validate_and_filter(self, promos: list[UnifiedPromo]) -> list[UnifiedPromo]:
        """Valida e garante a conformidade determinística da lista de promoções recolhidas."""
        return validate_promos(promos)
