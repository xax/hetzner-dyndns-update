#!/usr/bin/env python3

import argparse
import functools
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
from socketserver import BaseServer
import subprocess
from urllib.parse import unquote_plus

# SPDX-FileCopyrightText: Copyright (C) Sep 2026 XA. All rights reserved.
# SPDX-License-Identifier: EUPL-1.2
__version__ = "1.0.0"
__copyright__ = "Copyright (C) by XA, IX 2026. All rights reserved. Licensed under EUPL-1.2."


def _minsplit(what: str, sep: str, minsplit: int, maxsplit: int = -1, *, default: str = "") -> list[str]:
    return (what.split(sep, maxsplit) + [default * minsplit])[0:minsplit+1]


class DynDNSHandler(BaseHTTPRequestHandler):

    def __init__(self, request, client_address, server: BaseServer, *, key: str = "keykey", routeUpdate: str = "update", routeHealthcheck: str = "hc"):
        self.key = key
        self.routeUpdate: str = routeUpdate
        self.routeHealthcheck: str = routeHealthcheck
        self._selfpath = os.path.dirname(os.path.abspath(__file__))
        super().__init__(request, client_address, server)

    def do_GET(self) -> None:
        print(self.path)
        p, q = _minsplit(self.path, "?", minsplit=1, maxsplit=1)
        print(f"{p=} {q=}")

        if len(q) > 0:
            defs = q.split("&")
            vars = {k: v for (k, v) in [_minsplit(d, "=", 1) for d in defs]}
            if "key" in vars.keys() and unquote_plus(vars["key"]) == self.key:
                self._handle_request(unquote_plus(p), vars)
                return
        self.send_response(HTTPStatus.FORBIDDEN)
        self.end_headers()

    def _handle_request(self, path: str, vars: dict[str, str]) -> None:
        print(f"{path=} {vars=}")

        if path == f"/{self.routeHealthcheck}":
            self.send_response(HTTPStatus.OK)
            self.end_headers()
        elif path == f"/{self.routeUpdate}":
            try:
                subprocess.run(f"{self._selfpath}/dyndns-hetzner.sh", shell=True, timeout=10, check=True)
            except subprocess.CalledProcessError as e:
                self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
                self.end_headers()
                self.wfile.writelines(iter([f"OK\n".encode()]))
            else:
                self.send_response(HTTPStatus.OK)
                #self.send_response(HTTPStatus.NOT_MODIFIED)
                self.end_headers()
        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()


def run(
        *,
        handler_class=DynDNSHandler,
        server_bind: str = "",
        server_port: int = 8000,
        server_class=HTTPServer,
        certfile: Path | None = None,
        keyfile: Path | None = None,
        password: str | None = None,
        key: str = "keykey123"
    ):
    server_address = (server_bind, server_port)
    httpd = server_class(server_address, functools.partial(handler_class, key=key))
    httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--listen", type=str, default="0.0.0.0")
    parser.add_argument("-p", "--port", type=int, default=8000)
    parser.add_argument("-k", "--key", type=str, default="keykey123")
    parser.add_argument("-K", "--key-file", type=Path)
    args = parser.parse_args()

    if args.key_file is not None:
        with open(args.key_file, "r") as kf:
            key = kf.readline()
    else:
        key = args.key

    run(handler_class=DynDNSHandler, server_class=HTTPServer, server_bind=args.listen, server_port=args.port, key=key)


if __name__ == "__main__":
    main()
