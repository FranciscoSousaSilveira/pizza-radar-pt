"""Script para captura determinística de screenshots desktop e mobile via Chrome/Edge headless."""

import http.server
import os
from pathlib import Path
import socketserver
import subprocess
import threading
import time

PORT = 8765
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, format, *args):
        pass  # Silenciar logs do servidor local


def run_server():
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.serve_forever()


def find_browser():
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    raise RuntimeError("Nenhum browser compatível encontrado.")


def capture(browser_bin, url, output_png, width, height):
    cmd = [
        browser_bin,
        "--headless=new",
        "--disable-gpu",
        f"--window-size={width},{height}",
        "--virtual-time-budget=2000",
        "--hide-scrollbars",
        f"--screenshot={output_png}",
        url,
    ]
    print(f"A capturar {output_png.name} ({width}x{height})...")
    subprocess.run(cmd, check=True)
    if output_png.exists():
        print(f"Screenshot gerado: {output_png} ({output_png.stat().st_size} bytes)")
    else:
        raise RuntimeError(f"Falha ao gerar {output_png}")


def main():
    browser = find_browser()
    print(f"Browser selecionado: {browser}")

    # Iniciar servidor HTTP local em thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1.0)  # Aguardar arranque do servidor

    url = f"http://127.0.0.1:{PORT}/index.html"

    # 1. Desktop (1440x1100)
    desktop_png = SCREENSHOTS_DIR / "desktop_view.png"
    capture(browser, url, desktop_png, 1440, 1100)

    # 2. Mobile (390x1300 - iPhone 14/15 viewport com cartões visíveis)
    mobile_png = SCREENSHOTS_DIR / "mobile_view.png"
    capture(browser, url, mobile_png, 390, 1300)

    print("Screenshots capturados com sucesso!")


if __name__ == "__main__":
    main()
