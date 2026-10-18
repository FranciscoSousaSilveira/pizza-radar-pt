"""Wrapper e coletor em Python para integração com o motor headless Obscura.

Obscura (https://github.com/h4ckf0r0day/obscura) é um motor headless ultra-leve em Rust
que executa JavaScript com V8, stealth nativo anti-deteção e consome apenas ~30MB de RAM.

Este módulo providencia:
- Execução determinística do binário (`obscura fetch <url> --dump html`).
- Deteção e resolução do executável (via PATH ou variável de ambiente OBSCURA_PATH).
- Modo estrito e modo gracioso de fallback (caso o binário não esteja instalado no host).
- Sanitização de timeout e tratamento transparente de erros de subprocesso.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class ObscuraNotFoundError(FileNotFoundError):
    """Lançado quando o binário executável do Obscura não se encontra disponível."""
    pass


class ObscuraExecutionError(RuntimeError):
    """Lançado quando a execução do Obscura retorna código de erro diferente de zero."""
    def __init__(self, message: str, exit_code: int, stderr: str = "") -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


@dataclass(frozen=True)
class ObscuraFetchResult:
    """Resultado estruturado de uma extração realizada pelo Obscura."""
    url: str
    html: str
    exit_code: int
    duration_seconds: float


class ObscuraScraper:
    """Cliente para extração de páginas web usando o binário CLI do Obscura."""

    DEFAULT_TIMEOUT: float = 30.0

    def __init__(
        self,
        binary_path: str | None = None,
        default_timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.binary_path = binary_path or os.environ.get("OBSCURA_PATH")
        self.default_timeout = default_timeout

    def resolve_binary(self) -> str:
        """Resolve e valida o caminho para o executável do Obscura."""
        if self.binary_path:
            resolved = shutil.which(self.binary_path) or self.binary_path
            if os.path.isfile(resolved) or shutil.which(self.binary_path):
                return resolved
            raise ObscuraNotFoundError(f"Binário Obscura configurado em '{self.binary_path}' não foi encontrado.")

        # Pesquisa no PATH do sistema operacional
        found = shutil.which("obscura") or shutil.which("obscura.exe")
        if found:
            return found

        raise ObscuraNotFoundError(
            "Binário 'obscura' não foi encontrado no PATH nem na variável OBSCURA_PATH. "
            "Instala o binário a partir de https://github.com/h4ckf0r0day/obscura/releases"
        )

    def is_available(self) -> bool:
        """Verifica se o motor Obscura está instalado e acessível no ambiente atual."""
        try:
            self.resolve_binary()
            return True
        except ObscuraNotFoundError:
            return False

    def fetch_html(
        self,
        url: str,
        timeout: float | None = None,
        extra_args: list[str] | None = None,
    ) -> ObscuraFetchResult:
        """Executa 'obscura fetch <url> --dump html' e devolve o HTML renderizado."""
        binary = self.resolve_binary()
        effective_timeout = timeout or self.default_timeout

        cmd = [binary, "fetch", url, "--dump", "html"]
        if extra_args:
            cmd.extend(extra_args)

        logger.info("A executar Obscura fetch para %s...", url)
        import time
        start_time = time.time()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.time() - start_time
            logger.error("Obscura excedeu timeout de %.1fs ao recolher %s", effective_timeout, url)
            raise TimeoutError(f"Obscura fetch timeout ({effective_timeout}s) para {url}") from exc
        except OSError as exc:
            logger.error("Falha de subprocesso ao invocar Obscura (%s): %s", binary, exc)
            raise ObscuraExecutionError(f"Erro ao iniciar Obscura: {exc}", exit_code=-1) from exc

        duration = time.time() - start_time

        if proc.returncode != 0:
            err_msg = (proc.stderr or "").strip()
            logger.warning(
                "Obscura terminou com código %d para %s. Erro: %s",
                proc.returncode,
                url,
                err_msg,
            )
            raise ObscuraExecutionError(
                f"Obscura falhou com código {proc.returncode}: {err_msg}",
                exit_code=proc.returncode,
                stderr=err_msg,
            )

        return ObscuraFetchResult(
            url=url,
            html=proc.stdout,
            exit_code=proc.returncode,
            duration_seconds=duration,
        )
