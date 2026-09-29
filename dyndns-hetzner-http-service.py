#!/usr/bin/env python3

import argparse
import functools
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPSServer, HTTPServer
import logging
import os
from pathlib import Path
import re
from socketserver import BaseServer
import subprocess
from urllib.error import URLError
from urllib.parse import unquote_plus
from urllib.request import urlopen

# SPDX-FileCopyrightText: Copyright (C) Sep 2026 XA. All rights reserved.
# SPDX-License-Identifier: EUPL-1.2
__version__ = "2.0.0"
__copyright__ = "Copyright (C) by XA, IX 2026. All rights reserved. Licensed under EUPL-1.2."

log = logging.getLogger(__name__)


def _minsplit(what: str, sep: str, minsplit: int, maxsplit: int = -1, *, default: str = "") -> list[str]:
    return (what.split(sep, maxsplit) + [default * minsplit])[0 : minsplit + 1]


def _get_my_ip(urlv4: str = "https://ipv4.icanhazip.com") -> str | None:
    res = urlopen(urlv4, timeout=6)
    if res.status == HTTPStatus.OK:
        ip = res.read()
        return ip.decode()
    return None


def _get_my_ipv6(urlv6: str = "https://ipv6.icanhazip.com") -> str | None:
    res = urlopen(urlv6, timeout=6)
    if res.status == HTTPStatus.OK:
        ip = res.read()
        return ip.decode()
    return None


def _touch_url(url: str):
    try:
        if (url.find("{ip}") >= 0 or url.find("{ipv4}") >= 0) and (ip := _get_my_ip()) is not None:
            url = url.replace("{ip}", ip).replace("{ipv4}", ip)
        if url.find("{ipv6}") >= 0 and (ip := _get_my_ipv6()) is not None:
            url.replace("{ipv6}", ip)
    except (URLError, OSError) as e:
        log.warning(f"Unable to determine own external IP: {e}")
    log.info(f"URL: {unquote_plus(url)}")
    try:
        urlopen(url, timeout=8)
    except (URLError, ValueError) as e:
        log.warning(f'Failed touching additional url "{url}": {e}')


class DynDNSHandler(BaseHTTPRequestHandler):

    def __init__(
        self,
        request,
        client_address,
        server: BaseServer,
        *,
        token: str = "keykey123",
        routeUpdate: str = "update",
        routeHealthcheck: str = "hc",
        additional_urls: list[str] = [],
    ):
        self.token = token
        self.routeUpdate: str = routeUpdate
        self.routeHealthcheck: str = routeHealthcheck
        self.additional_urls: list[str] = additional_urls
        self._selfpath = os.path.dirname(os.path.abspath(__file__))
        super().__init__(request, client_address, server)

    def do_GET(self) -> None:
        log.info(self.path)
        p, q = _minsplit(self.path, "?", minsplit=1, maxsplit=1)
        log.info(f"{p=} {q=}")

        if len(q) > 0:
            defs = q.split("&")
            vars = {k: v for (k, v) in [_minsplit(d, "=", 1) for d in defs]}
            if "token" in vars.keys() and unquote_plus(vars["token"]) == self.token:
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
                # self.send_response(HTTPStatus.NOT_MODIFIED)
                self.end_headers()
            ##
            for contact in self.additional_urls:
                _touch_url(contact)

        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()


def run(
    *,
    handler_class=DynDNSHandler,
    server_bind: str = "",
    server_port: int = 8000,
    token: str,
    certfile: Path | None = None,
    keyfile: Path | None = None,
    password: str | None = None,
    additional_urls: list[str] = [],
):
    server_address = (server_bind, server_port)
    if certfile is not None:
        httpd = HTTPSServer(
            server_address,
            functools.partial(handler_class, token=token, additional_urls=additional_urls),
            certfile=certfile,
            keyfile=keyfile,
            password=password,
        )
    else:
        httpd = HTTPServer(
            server_address, functools.partial(handler_class, token=token, additional_urls=additional_urls)
        )
    httpd.serve_forever()


def generate_cert(basename: Path = Path("dyndns_hhs")):
    selfpath = os.path.dirname(os.path.abspath(__file__))
    if basename.parent == "":
        basename = selfpath / basename
    key_name = basename.with_suffix(".key")
    cert_name = basename.with_suffix(".cer")
    chain_name = basename.with_suffix(".pem")

    bin_openssl = "openssl"
    try:
        subprocess.run([f"{bin_openssl}", "-v"], timeout=4, check=True)
    except subprocess.CalledProcessError as e:
        log.error(f'Unable to start OpenSSL ("{bin_openssl}"): {e}')

    try:
        subprocess.run(
            [f"{bin_openssl}", "genpkey", "-algorithm", "ed25519", "-out", str(key_name)], timeout=10, check=True
        )
        subprocess.run(
            [
                f"{bin_openssl}",
                "req",
                "-x509",
                "-noenc",
                "-days",
                "365",
                "-key",
                str(key_name),
                "-subj",
                "/C=EU/ST=EU/L=Europe/O=DynDNS-Hetzner-http-service",
                "-addext",
                "keyUsage=critical,keyCertSign",
                "-out",
                str(cert_name),
            ],
            timeout=15,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        log.error(f'Unable to generate key and/or certificate with OpenSSL ("{bin_openssl}"): {e}')

    chain_name.write_text(key_name.read_text() + cert_name.read_text())


def main():
    defaultPassword = os.environ.get("DYNDNY_HHS_PASSWORD", None)
    defaultToken = os.environ.get("DYNDNY_HHS_TOKEN", "keykey123")

    parser = argparse.ArgumentParser()
    pg_server = parser.add_argument_group(title="Server")
    pg_server.add_argument("-l", "--listen", type=str, default="0.0.0.0", help="IP address to listen on [%(default)s]")
    pg_server.add_argument("-p", "--port", type=int, default=8000, help="port to listen on [%(default)s]")
    pg_server.add_argument(
        "-t",
        "--token",
        type=str,
        default=defaultToken,
        help="access token used for authorization (also from DYNDNY_HHS_TOKEN environment variable) [%(default)s]",
    )
    pg_server.add_argument(
        "-c", "--certfile", type=Path, default=None, help="to use TLS: path to certificate or combined key/certificate"
    )
    pg_server.add_argument("-k", "--keyfile", type=Path, default=None, help="to use TLS: optional path to key")
    pg_server.add_argument(
        "-a",
        "--additional",
        nargs="*",
        action="extend",
        default=[],
        help='additional urls to be touched on update; can contain "{ipv4}"/"{ipv6}" placeholders (will use icanhazip.com to determine external IP in that case!)',
    )
    pg_utils = parser.add_argument_group(title="Utility functionality")
    pg_utils.add_argument(
        "-G",
        "--gen-cert",
        metavar="STEM",
        type=str,
        nargs="?",
        const="dyndns_hhs",
        default=None,
        help="Generate a key/certificate pair and a combined chain and place them into .key/.cer/.pem files, respectively [%(const)s]",
    )
    parser.add_argument(
        "-P",
        "--password",
        type=str,
        default=defaultPassword,
        help="Optional password to keyfile (also from DYNDNY_HHS_PASSWORD environment variable) [%(default)s]",
    )
    args = parser.parse_args()

    ## if requested, generate key/cert pair and exit
    if args.gen_cert is not None:
        generate_cert()
        return

    ## sanitize additional urls
    reCheckURL = re.compile(r"^https?://\w+")
    for i, url in enumerate(args.additional):
        if reCheckURL.search(url) is None:
            args.additional[i] = "https://" + url

    ## run the server process
    run(
        handler_class=DynDNSHandler,
        server_bind=args.listen,
        server_port=args.port,
        token=args.token,
        certfile=args.certfile,
        keyfile=args.keyfile,
        password=args.password,
        additional_urls=args.additional,
    )


if __name__ == "__main__":
    # logging.basicConfig(level=logging.INFO)
    main()
