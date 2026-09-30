#!/usr/bin/env python3

from abc import ABC, abstractmethod
import argparse
import functools
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPSServer, HTTPServer
import json
import logging
import os
from pathlib import Path
import re
from socketserver import BaseServer
import subprocess
from types import EllipsisType
from typing import Any
from urllib.error import URLError
from urllib.parse import unquote_plus
from urllib.request import Request, urlopen

# SPDX-FileCopyrightText: Copyright (C) Oct 2026 XA. All rights reserved.
# SPDX-License-Identifier: EUPL-1.2
__version__ = "3.1.0"
__copyright__ = "Copyright (C) by XA, X 2026. All rights reserved. Licensed under EUPL-1.2."

log = logging.getLogger(__name__)


class IPState(ABC):

    @property
    @abstractmethod
    def ip_v4(self) -> str | None:
        pass

    @property
    @abstractmethod
    def ip_v6(self) -> str | None:
        pass

    @property
    def ip(self) -> tuple[str | None, str | None]:
        return self.ip_v4, self.ip_v6

    @abstractmethod
    def snapshot_v4(self, default: str | EllipsisType | None, *, timeout: int = 6) -> None:
        pass

    @abstractmethod
    def snapshot_v6(self, default: str | EllipsisType | None, *, timeout: int = 6) -> None:
        pass

    def snapshot(self, default: EllipsisType | None, *, timeout: int = 6) -> None:
        self.snapshot_v4(default, timeout=timeout)
        self.snapshot_v6(default, timeout=timeout)


class IPStateStatic(IPState):

    def __init__(self, /, ip_v4: str | None, ip_v6: str | None, **kwargs):
        super().__init_subclass__(**kwargs)
        self._ip_v4 = ip_v4
        self._ip_v6 = ip_v6

    @property
    def ip_v4(self) -> str | None:
        return self._ip_v4

    @property
    def ip_v6(self) -> str | None:
        return self._ip_v6

    def snapshot_v4(self, default: str | EllipsisType | None, *, timeout: int = 6) -> None:
        pass # leave unchanged

    def snapshot_v6(self, default: str | EllipsisType | None, *, timeout: int = 6) -> None:
        pass # leave unchanged


class IPStateHttpGet(IPState):
    target_v4: str = ""
    target_v6: str = ""

    def __init_subclass__(cls, /, target_v4: str, target_v6: str, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.target_v4 = target_v4
        cls.target_v6 = target_v6

    def __init__(self, instant_ip_v4: bool = True, instant_ip_v6: bool = True, *, raise_exceptions: bool = False):
        self._raise_exceptions = raise_exceptions
        self._ip_v4 = None
        self._ip_v6 = None
        if instant_ip_v4: self.snapshot_v4(None)
        if instant_ip_v6: self.snapshot_v6(None)

    @property
    def ip_v4(self) -> str | None:
        return self._ip_v4

    @property
    def ip_v6(self) -> str | None:
        return self._ip_v6

    def snapshot_v4(self, default: str | EllipsisType | None, *, timeout: int = 6) -> None:
        if (result := __class__._do_request(self.target_v4, timeout, self._raise_exceptions)) is not None:
            self._ip_v4 = result
        elif default is not ...:
            self._ip_v4 = default
        else:
            pass # leave unchanged

    def snapshot_v6(self, default: str | EllipsisType | None, *, timeout: int = 6) -> None:
        if (result := __class__._do_request(self.target_v6, timeout, self._raise_exceptions)) is not None:
            self._ip_v6 = result
        elif default is not ...:
            self._ip_v6 = default
        else:
            pass # leave unchanged

    @classmethod
    def _do_request(cls, target, timeout: int, raise_exceptions: bool = False) -> str | None:
        res = None
        try:
            res = urlopen(target, timeout=timeout)
        except (OSError, URLError) as e:
            log.warning(f"Unable to reach endpoint \"{target}\" with this IP version: {e}")
            if raise_exceptions:
                raise
        if res is not None and res.status == HTTPStatus.OK:
            ip = res.read()
            return ip.decode().strip()
        else:
            return None


class IPStateHaz(IPStateHttpGet, target_v4="https://ipv4.icanhazip.com", target_v6="https://ipv6.icanhazip.com"):
    pass


def _minsplit(what: str, sep: str, minsplit: int, maxsplit: int = -1, *, default: str = "") -> list[str]:
    return (what.split(sep, maxsplit) + [default * minsplit])[0 : minsplit + 1]


def touch_url(url: str, ipState: IPState):
    if (url.find("{ip}") >= 0 or url.find("{ipv4}") >= 0) and (ip := ipState.ip_v4) is not None:
        url = url.replace("{ip}", ip).replace("{ipv4}", ip)
    if url.find("{ipv6}") >= 0 and (ip := ipState.ip_v6) is not None:
        url.replace("{ipv6}", ip)
    log.debug(f"URL: {unquote_plus(url)}")
    try:
        urlopen(url, timeout=8)
    except (URLError, ValueError) as e:
        log.warning(f'Failed touching additional url "{url}": {e}')


class DynDNSUpdaterHCloud:
    API_URL: str = "https://api.hetzner.cloud/v1"
    TIMEOUT: int = 8

    def __init__(self, *, ipState: IPState, config: dict[str, Any] = {}):
        self.ipState = ipState
        self.config = config
        self.raise_exceptions: bool = False


    def __call__(self, snapshot_ip: bool = False):
        if snapshot_ip:
            self.ipState.snapshot(...)
        for spec in self.config.get("rrspecs", []):
            split = ["", *spec.split("@")]
            self._update_domain(*split[-2:])

        # for cname in self.config.get("cnames", []):
        #     self._update_cname(cname)


    def _update_cname(self, cname: str): ...


    def _update_domain(self, rrname: str, zone: str) -> bool:
        if rrname == "" or rrname == "@":
            rrname = "@"
            domain = zone
        else:
            domain = f"{rrname}.{zone}"
        log.debug(f"[{domain=}] ({rrname=}@{zone=}) {self.ipState.ip_v4=}")

        zone_id = self._get_zone_id(zone)
        if zone_id is None:
            log.error(f"❌ Unable to find zone for {domain}.")
            return False

        rrsets = self._zone_list_rrsets(zone_id)
        if rrsets is None:
            log.error(f"List of resource records empty.")
            return  False

        current_v4 = self._get_1st_value_by_rrname_rrtype(rrsets, rrname, "A")
        current_v6 = self._get_1st_value_by_rrname_rrtype(rrsets, rrname, "AAAA")

        if self.ipState.ip_v4 is not None and self.ipState.ip_v4 != current_v4:
            log.info(f"[{domain}] ➡️ Setting new A record to {self.ipState.ip_v4}")
            self._rrsets_remove_record(zone_id, rrname, "A", current_v4)
            #self._rrsets_remove(zone_id, rrname, "A")
            self._rrsets_add_record(zone_id, rrname, "A", self.ipState.ip_v4)
        else:
            log.info(f"[{domain}] ✅ A record already up to date ({self.ipState.ip_v4})")

        if self.ipState.ip_v6 is not None and self.ipState.ip_v6 != current_v6:
            log.info(f"[{domain}] ➡️ Setting new AAAA record to {self.ipState.ip_v6}")
            self._rrsets_remove_record(zone_id, rrname, "AAAA", current_v6)
            #self._rrsets_remove(zone_id, rrname, "AAAA")
            self._rrsets_add_record(zone_id, rrname, "AAAA", self.ipState.ip_v6)
        else:
            log.info(f"[{domain}] ✅ AAAA record already up to date ({self.ipState.ip_v6})")

        return True


    def _api_call(self, api_path: str, method: str | None = None, data = None):
        log.debug(f"Bearer {self.config.get("api_key", "none")}")
        log.debug(f"{data=}")
        headers = {
                "Authorization": f"Bearer {self.config.get("api_key", "none")}",
        }
        req = Request(
            url=__class__.API_URL + api_path,
            data=data,
            headers=headers,
            method=method,
        )
        if req.get_method() == "POST":
            req.add_header("Content-Type", "application/json")
        res = None
        try:
            res = urlopen(req, timeout=__class__.TIMEOUT)
        except (OSError, URLError) as e:
            log.warning(f"Error reaching API endpoint \"{req.full_url}\": {e}")
            if self.raise_exceptions:
                raise
        if res is not None and res.status == HTTPStatus.OK:
            return res.read() or ""
        else:
            return None

    def _get_zone_id(self, main_domain: str) -> str | None:
        if (res := self._api_call("/zones")) is None:
            log.error(f"Failed API call _get_zone_id.")
            return None
        data = json.loads(res)
        for zone in data["zones"]:
            if zone.get("name") == main_domain:
               return zone.get("id", None)
        log.error(f"Domain \"{main_domain}\" not in zone file.")
        return None


    def _zone_list_rrsets(self, zone_id) -> list[dict] | None:
        if (res := self._api_call(f"/zones/{zone_id}/rrsets")) is None:
            log.error(f"Failed API call _zone_list_rrsets.")
            return None
        data = json.loads(res)
        return data.get("rrsets", None)


    def _get_1st_value_by_rrname_rrtype(self, rrsets: list[dict], rr_name, rr_type) -> str | None:
        for rr in rrsets:
            if rr.get("name") == rr_name and rr.get("type") == rr_type and isinstance(rs := rr.get("records"), list):
               return rs[0].get("value")
        log.error(f"Record for subdomain \"{rr_name}\" not found.")
        return None


    def _rrsets_add_record(self, zone_id, rr_name, rr_type, value):
        res = self._api_call(
            f"/zones/{zone_id}/rrsets/{rr_name}/{rr_type}/actions/add_records",
            "POST",
            json.dumps({"ttl": self.config.get("ttl", 120), "records": [{"value": value}]}).encode()
        )
        if res is None:
            log.error(f"Failed API call _rrsets_add_record.")
            return None
        return True


    def _rrsets_remove_record(self, zone_id, rr_name, rr_type, value):
        res = self._api_call(
            f"/zones/{zone_id}/rrsets/{rr_name}/{rr_type}/actions/remove_records",
            "POST",
            json.dumps({"records": [{"value": value}]}).encode()
        )
        if res is None:
            log.error(f"Failed API call _rrsets_remove_record.")
            return None
        return True

    def _rrsets_remove(self, zone_id, rr_name, rr_type):
        res = self._api_call(
            f"/zones/{zone_id}/rrsets/{rr_name}/{rr_type}",
            "DELETE",
        )
        if res is None:
            log.error(f"Failed API call _rrsets_remove.")
            return None
        return True



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
        config: dict[str, Any] = {},
    ):
        self.token = token
        self.routeUpdate: str = routeUpdate
        self.routeHealthcheck: str = routeHealthcheck
        self.config = config
        self._selfpath = os.path.dirname(os.path.abspath(__file__))
        super().__init__(request, client_address, server)


    def do_GET(self) -> None:
        log.debug(self.path)

        ## split off query part
        path, query = _minsplit(self.path, "?", minsplit=1, maxsplit=1)
        log.debug(f"{path=} {query=}")

        ## security check: verify access token
        if len(query) > 0:
            params = query.split("&")
            vars = {k: v for (k, v) in [_minsplit(param, "=", 1) for param in params]}
            if "token" in vars and unquote_plus(vars["token"]) == self.token:
                self._handle_request(unquote_plus(path), vars)
                return

        ## send 403 FORBIDDEN on any verification failure
        self.send_response(HTTPStatus.FORBIDDEN)
        self.end_headers()


    def _handle_request(self, path: str, vars: dict[str, str]) -> None:
        print(f"{path=} {vars=}")

        ## route requests based on path
        if path == f"/{self.routeHealthcheck}":
            ## health check: respond with 200 OK
            self.send_response(HTTPStatus.OK)
            self.end_headers()
        elif path == f"/{self.routeUpdate}":
            ## process DNS update request
            if "ipv4" in vars or "ipv6" in vars:
                ipState = IPStateStatic(vars.get("ipv4"), vars.get("ipv6"))
            else:
                ipState = IPStateHaz(False, False)
            try:
                ipState.snapshot(...)
            except (URLError, OSError) as e:
                log.warning(f"Unable to determine own external IP: {e}")

            if self.config.get("use_shellscript", False):
                try:
                    subprocess.run(f"{self._selfpath}/dyndns-hetzner.sh", shell=True, timeout=10, check=True)
                except subprocess.CalledProcessError as e:
                    self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
                    self.end_headers()
                else:
                    self.send_response(HTTPStatus.OK)
                    # self.send_response(HTTPStatus.NOT_MODIFIED)
                    self.end_headers()
                    self.wfile.writelines(iter([f"OK\n".encode()]))
            else:
                dyndnsProvider = DynDNSUpdaterHCloud(ipState=ipState, config=self.config)
                dyndnsProvider()
                self.send_response(HTTPStatus.OK)
                # self.send_response(HTTPStatus.NOT_MODIFIED)
                self.end_headers()
                self.wfile.writelines(iter([f"OK\n".encode()]))

            ## touch additional urls, if any, as requested
            for contact in self.config.get("additional_urls", []):
                touch_url(contact, ipState)
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
    config: dict = {},
):
    server_address = (server_bind, server_port)
    if certfile is not None:
        httpd = HTTPSServer(
            server_address,
            functools.partial(handler_class, token=token, config=config),
            certfile=certfile,
            keyfile=keyfile,
            password=password,
        )
    else:
        httpd = HTTPServer(
            server_address, functools.partial(handler_class, token=token, config=config)
        )

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("Good-bye!")


def generate_cert(*, basename: Path = Path("dyndns_hhs"), password: str | None = None):
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
        args = [f"{bin_openssl}", "genpkey", "-algorithm", "ed25519", "-out", str(key_name)]
        if password is not None:
            args += ["-pass", f"pass:{password}"]
        subprocess.run(args, timeout=10, check=True)
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
    defaultPassword = os.environ.get("DYNDYS_HHS_PASSWORD", None)
    defaultToken = os.environ.get("DYNDNS_HHS_TOKEN", "keykey123")
    defaultAPIKey = os.environ.get("DYNDNS_HHS_API_KEY", None)

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""\
Enrolls a server listening for HTTP-GET requests, upon which it uses the Hetzner-Cloud-API
to update DNS A/AAAA records for given entries.

Endpoints:
    /hc
        Healthcheck: expect an HTTP 200 OK reply if service running
    /update?token=‹authtoken›[&ipv4=‹ipv4›][&ipv6=‹ipv6›]
        Update DNS records for entries specified on service's start.
            ‹authtoken› - authentification token as given on service's launch
            ‹ipv4› - new IPv4 address if known;
                     otherwise service will use an external service to try to determine address
            ‹ipv6› - new IPv6 address if known;
                     otherwise service will use an external service to try to determine address
""",
        epilog=f"Version {__version__}. {__copyright__}"
    )
    pg_api = parser.add_argument_group(title="API")
    pg_api.add_argument(
        "-A",
        "--api-key",
        type=str,
        default=defaultAPIKey,
        help="key to authenticate against Hetzner Cloud API (also from DYNDNS_HHS_API_KEY environment variable) [%(default)s]",
    )
    pg_api.add_argument(
        "-t",
        "--ttl",
        type=int,
        default=120,
        help="TTL in seconds for A/AAAA/CNAME DNS resource records [%(default)s]",
    )
    pg_api.add_argument(
        "-H",
        "--hosts",
        "--rrspecs",
        metavar="HOST@ZONE",
        nargs="*",
        action="extend",
        help="DNS resource record sets names to change A/AAAA records of in given zone (e.g. \"@domain.tld\" for zone origin, \"www@domain.tld\" for www subdomain)",
    )

    pg_server = parser.add_argument_group(title="Server")
    pg_server.add_argument("-l", "--listen", type=str, default="0.0.0.0", help="IP address to listen on [%(default)s]")
    pg_server.add_argument("-p", "--port", type=int, default=8000, help="port to listen on [%(default)s]")
    pg_server.add_argument(
        "-T",
        "--token",
        type=str,
        default=defaultToken,
        help="access token used for authorization (also from DYNDNS_HHS_TOKEN environment variable) [%(default)s]",
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
        help="Optional password to keyfile (also from DYNDNS_HHS_PASSWORD environment variable) [%(default)s]",
    )
    args = parser.parse_args()

    ## if requested, generate key/cert pair and exit
    if args.gen_cert is not None:
        generate_cert(basename=args.gen_cert, password=args.password)
        return

    if args.api_key is None:
        log.error("An API key is required. Use option -A or environment variable DYNDNS_HHS_API_KEY to specify it.")
        return 1

    if len(args.hosts) == 0:
        log.error("At least on resource record name and a zone has to be specified (try \"-H @yourdomain.tld\").")
        return 1

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
        config={
            "additional_urls": args.additional,
            "api_key": args.api_key,
            "ttl": args.ttl,
            "zone": "",
            "rrspecs": args.hosts
        }
    )

    return 0

if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG)
    exit(main())
