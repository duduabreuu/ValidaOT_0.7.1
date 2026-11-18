#!/usr/bin/env python3
"""Servidor local do front-end ValidaOT com proxy same-origin para FastAPI.

- Serve os arquivos desta pasta em http://127.0.0.1:5173
- Encaminha /api/* para o backend (por padrão http://127.0.0.1:8000/*)
- Não armazena credenciais, tokens ou corpos de requisição.
- Escuta somente em loopback por padrão; não exponha este servidor na rede.
"""
from __future__ import annotations

import argparse
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    server_version = "ValidaOTFrontend/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # Evita incluir query strings ou cabeçalhos potencialmente sensíveis no log.
        print(f"[{self.log_date_time_string()}] {self.command} {urlsplit(self.path).path} -> {args[1] if len(args) > 1 else ''}")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self) -> None:
        parsed = urlsplit(self.path)
        upstream_path = parsed.path[4:] or "/"
        if not upstream_path.startswith("/"):
            upstream_path = "/" + upstream_path
        target = self.server.backend.rstrip("/") + upstream_path
        if parsed.query:
            target += "?" + parsed.query
        body = None
        if self.command in {"POST", "PUT", "PATCH", "DELETE"}:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > 2_000_000:
                self._send(413, b'{"detail":"Payload muito grande."}', "application/json; charset=utf-8")
                return
            body = self.rfile.read(length) if length else None
        headers = {}
        for key in ("Authorization", "Content-Type", "Accept"):
            value = self.headers.get(key)
            if value:
                headers[key] = value
        req = Request(target, data=body, headers=headers, method=self.command)
        try:
            with urlopen(req, timeout=25) as response:
                content = response.read()
                self._send(response.status, content, response.headers.get("Content-Type", "application/json; charset=utf-8"))
        except HTTPError as exc:
            content = exc.read()
            self._send(exc.code, content, exc.headers.get("Content-Type", "application/json; charset=utf-8"))
        except (URLError, TimeoutError, OSError) as exc:
            message = '{"detail":"Não foi possível conectar ao backend FastAPI em ' + self.server.backend.replace('"', '') + '. Inicie a API e tente novamente."}'
            self._send(502, message.encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if urlsplit(self.path).path.startswith("/api/") or urlsplit(self.path).path == "/api":
            self._proxy()
            return
        self._static()

    def do_HEAD(self) -> None:
        if urlsplit(self.path).path.startswith("/api/"):
            self._proxy()
            return
        self._static(head_only=True)

    def do_POST(self) -> None:
        if urlsplit(self.path).path.startswith("/api/"):
            self._proxy()
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _static(self, head_only: bool = False) -> None:
        requested = urlsplit(self.path).path
        if requested == "/":
            requested = "/index.html"
        candidate = (ROOT / requested.lstrip("/")).resolve()
        if ROOT not in candidate.parents and candidate != ROOT:
            self._send(403, b"Forbidden", "text/plain; charset=utf-8")
            return
        if not candidate.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        content = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if not head_only:
            self.wfile.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor local ValidaOT Front-end")
    parser.add_argument("--host", default="127.0.0.1", help="Host local (padrão: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5173, help="Porta do front-end (padrão: 5173)")
    parser.add_argument("--backend", default=os.getenv("VALIDAOT_BACKEND", "http://127.0.0.1:8000"), help="URL base do backend FastAPI")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.backend = args.backend.rstrip("/")
    print("ValidaOT Front-end disponível em: http://127.0.0.1:%s" % args.port)
    print("Backend configurado em: %s" % server.backend)
    print("Proxy same-origin ativo em /api/*; nenhuma credencial será registrada no log.")
    print("Pressione Ctrl+C para encerrar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
