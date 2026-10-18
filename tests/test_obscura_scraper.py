"""Testes unitários para o módulo ObscuraScraper e integração com adaptadores."""

from __future__ import annotations

import os
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from pizza_radar.adapters.obscura_scraper import (
    ObscuraExecutionError,
    ObscuraFetchResult,
    ObscuraNotFoundError,
    ObscuraScraper,
)


class TestObscuraScraper(unittest.TestCase):
    """Testes unitários determinísticos para o wrapper ObscuraScraper."""

    def test_resolve_binary_not_found(self):
        """Quando o binário não existe no PATH nem em OBSCURA_PATH, lança ObscuraNotFoundError."""
        with patch("shutil.which", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                scraper = ObscuraScraper(binary_path=None)
                self.assertFalse(scraper.is_available())
                with self.assertRaises(ObscuraNotFoundError):
                    scraper.resolve_binary()

    def test_resolve_binary_from_custom_path(self):
        """Quando binary_path é passado e existe, é resolvido corretamente."""
        with patch("os.path.isfile", return_value=True):
            scraper = ObscuraScraper(binary_path="/custom/bin/obscura")
            self.assertEqual(scraper.resolve_binary(), "/custom/bin/obscura")
            self.assertTrue(scraper.is_available())

    def test_resolve_binary_from_env_var(self):
        """Quando OBSCURA_PATH está definido e o ficheiro existe, resolve-o."""
        with patch.dict(os.environ, {"OBSCURA_PATH": "/opt/obscura/obscura"}):
            with patch("os.path.isfile", return_value=True):
                scraper = ObscuraScraper()
                self.assertEqual(scraper.resolve_binary(), "/opt/obscura/obscura")
                self.assertTrue(scraper.is_available())

    @patch("subprocess.run")
    def test_fetch_html_success(self, mock_run):
        """Testa execução bem-sucedida de 'obscura fetch <url> --dump html'."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="<html><body><div combo-id='123'>Pizza Test</div></body></html>",
            stderr="",
        )
        with patch.object(ObscuraScraper, "resolve_binary", return_value="/usr/local/bin/obscura"):
            scraper = ObscuraScraper()
            result = scraper.fetch_html("https://www.dominospizza.pt/")

            self.assertIsInstance(result, ObscuraFetchResult)
            self.assertEqual(result.url, "https://www.dominospizza.pt/")
            self.assertEqual(result.exit_code, 0)
            self.assertIn("combo-id='123'", result.html)
            self.assertGreaterEqual(result.duration_seconds, 0.0)

            # Valida comando executado
            mock_run.assert_called_once_with(
                ["/usr/local/bin/obscura", "fetch", "https://www.dominospizza.pt/", "--dump", "html"],
                capture_output=True,
                text=True,
                timeout=30.0,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

    @patch("subprocess.run")
    def test_fetch_html_non_zero_exit_raises_error(self, mock_run):
        """Quando o processo termina com erro, lança ObscuraExecutionError."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Failed to load page: Connection refused",
        )
        with patch.object(ObscuraScraper, "resolve_binary", return_value="/usr/local/bin/obscura"):
            scraper = ObscuraScraper()
            with self.assertRaises(ObscuraExecutionError) as ctx:
                scraper.fetch_html("https://example.com")
            self.assertEqual(ctx.exception.exit_code, 1)
            self.assertIn("Connection refused", ctx.exception.stderr)

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="obscura", timeout=10.0))
    def test_fetch_html_timeout_raises_timeout_error(self, mock_run):
        """Quando o subprocesso excede o timeout configurado, lança TimeoutError."""
        with patch.object(ObscuraScraper, "resolve_binary", return_value="/usr/local/bin/obscura"):
            scraper = ObscuraScraper(default_timeout=10.0)
            with self.assertRaises(TimeoutError):
                scraper.fetch_html("https://example.com")


if __name__ == "__main__":
    unittest.main()
