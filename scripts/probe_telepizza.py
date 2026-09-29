"""Script de diagnóstico e sonda de rede para Telepizza (Issue #29) e Domino's (Issue #28).

Testa acessibilidade de rotas públicas oficiais a partir do ambiente de execução
utilizando estritamente HTTP padrão, sem contorno de WAF, sem proxies e sem logins.
"""

from __future__ import annotations

import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

_HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

_HEADERS_JSON = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
}


def probe_url(url: str, headers: dict[str, str], timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    result = {"url": url, "status": None, "length": 0, "error": None, "snippet": ""}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result["status"] = resp.status
            content = resp.read()
            result["length"] = len(content)
            result["snippet"] = content[:300].decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        result["error"] = f"HTTPError: {exc.code} - {exc.reason}"
        try:
            body = exc.read()
            result["snippet"] = body[:200].decode("utf-8", errors="replace")
        except Exception:
            pass
    except urllib.error.URLError as exc:
        result["error"] = f"URLError: {exc.reason}"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def main():
    print("=" * 60)
    print("SONDA DE SUPERFÍCIES PÚBLICAS OFICIAIS — TELEPIZZA E DOMINO'S")
    print("=" * 60)

    urls_to_test = [
        # Telepizza - Subdomínio app e rotas Demandware
        ("Telepizza - app.telepizza.pt/promocoes", "https://app.telepizza.pt/promocoes", _HEADERS_BROWSER),
        ("Telepizza - app.telepizza.pt/ (homepage)", "https://app.telepizza.pt/", _HEADERS_BROWSER),
        ("Telepizza - app Demandware Search-UpdateGrid", "https://app.telepizza.pt/on/demandware.store/Sites-TelepizzaPT-Site/pt_PT/Search-UpdateGrid?cgid=promocoes-pt", _HEADERS_BROWSER),
        ("Telepizza - www Demandware Search-UpdateGrid", "https://www.telepizza.pt/on/demandware.store/Sites-TelepizzaPT-Site/pt_PT/Search-UpdateGrid?cgid=promocoes-pt", _HEADERS_BROWSER),
        ("Telepizza - www.telepizza.pt/promocoes", "https://www.telepizza.pt/promocoes", _HEADERS_BROWSER),
        ("Telepizza - www sitemap_index.xml", "https://www.telepizza.pt/sitemap_index.xml", _HEADERS_BROWSER),
        ("Telepizza - app sitemap_index.xml", "https://app.telepizza.pt/sitemap_index.xml", _HEADERS_BROWSER),

        # Domino's - Subdomínios e rotas públicas alternativas
        ("Domino's - www.dominospizza.pt/ (homepage)", "https://www.dominospizza.pt/", _HEADERS_BROWSER),
        ("Domino's - m.dominospizza.pt/", "https://m.dominospizza.pt/", _HEADERS_BROWSER),
        ("Domino's - api.dominospizza.pt/", "https://api.dominospizza.pt/", _HEADERS_BROWSER),
        ("Domino's - www.dominospizza.pt/promocoes", "https://www.dominospizza.pt/promocoes", _HEADERS_BROWSER),
    ]

    for label, url, headers in urls_to_test:
        print(f"\n[PROBE] {label} -> {url}")
        res = probe_url(url, headers)
        if res["status"] == 200:
            print(f"  --> SUCESSO: HTTP 200 | Tamanho: {res['length']} bytes")
            print(f"  --> Snippet: {res['snippet'][:100].strip()}...")
        else:
            print(f"  --> FALHA / STATUS: {res['status']} | Erro: {res['error']}")
            if res["snippet"]:
                print(f"  --> Resposta: {res['snippet'][:150].strip()}...")

    print("\n" + "=" * 60)
    print("FIM DA EXECUÇÃO DA SONDA")
    print("=" * 60)


if __name__ == "__main__":
    main()
