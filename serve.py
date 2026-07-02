#!/usr/bin/env python3
"""
serve.py
--------
Servidor estático mínimo (só biblioteca padrão) para a Railway.
Entrega APENAS o dashboard.html já gerado — NÃO roda o scraper, não fala com
a Sofascore, não tem dependências. Você gera o HTML na sua máquina
(`python sofascore_stats.py`), commita e dá push; a Railway serve o arquivo.

A Railway injeta a porta em $PORT; escutamos em 0.0.0.0:$PORT.
"""

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))
HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(HERE, "dashboard.html")

# Só expomos o dashboard (não a árvore de arquivos, pra não vazar o código).
ALLOWED = {"/", "/dashboard.html", "/index.html"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._send(b"ok", "text/plain")
            return
        if path not in ALLOWED:
            self.send_error(404)
            return
        try:
            with open(FILE, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            self.send_error(503, "dashboard.html ainda nao publicado")
            return
        self._send(body, "text/html; charset=utf-8")

    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):        # silencia log ruidoso por request
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[serve] dashboard.html em http://0.0.0.0:{PORT} (arquivo: {FILE})")
    server.serve_forever()
