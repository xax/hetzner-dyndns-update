# Hetzner ® DNS Dynamic Update Service

![Version: 3.4.0](https://img.shields.io/badge/version-3.4.0-blue.svg)
![License: EUPL-1.2](https://img.shields.io/badge/license-EUPL%201.2-272398.svg?logo=europeanunion)

An HTTP(S) service running on Python 3.13+ with no other dependencies apart from the Python Standard Library.
Updates A and AAAA DNS resource records for specified subdomains (rr_names) in given zones using the
[Hetzner® Cloud API](https://docs.hetzner.cloud/reference/cloud).

> [!note]
> For a ”fire and forget“ bash script to perform the same job, refer to [README-cli](./README-cli.md).

## Overview

This script updates DNS records on Hetzner Cloud to your public IP address. It supports:

- **A records** - IPv4 addresses
- **AAAA records** - IPv6 addresses

Upon update requests, the service fetches your current public IP addresses if not provided,
compares them with existing DNS records, and updates them if they differ.
It can also call further 3rd party URIs to trigger updates there as well.

To make this script update the resource records whenever your public IP changes, make it run as a systemd service
on a host - preferably inside your secure LAN - and provide its endpoint URI as DynDNS update URI
to your primary internet providing router or modem, e.g. you FritzBox.

## Features

- ✅ Update A records with current IPv4 address
- ✅ Update AAAA records with current IPv6 address
- ✅ Update AAAA records with current IPv6 address network prefix and a specified fixed IPv6 interface address

Additionally:

- ✅ Back-off and retry a limited number of times if DNS service not yet (re-)established
- ✅ Skip resource record update when records are already up to date
- ✅ Configurable TTL for DNS records
- ✅ Support for multiple domains
- ✅ Support for cascading upgrade event calls

## Prerequisites

- [Hetzner® Cloud API key](https://hetzner.cloud/console/api) with DNS zone read/write permissions
- Python 3.13 or newer with its standard library
- Python 3.14 or newer with its standard library to use a TLS enabled service

## Configuration

Edit `dyndns-hetzner-http-service.service` or use appropriate environment variables or command line parameters.

### Environment variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DYNDNS_HHS_API_KEY` | Your Hetzner Cloud API key | `"Ksdf97HJGH8we63hH86LKGG8dsfjHjvsdfjgJHF875BHNmvbsdf87543J7BJG65j"` |
| `DYNDNS_HHS_TOKEN` | Access token that this service will ask for | `"s73kjbsesf63vdsr3b"` |
| `DYNDYS_HHS_PASSWORD` | Password of TLS private key, if required and TLS used | "secret_password" |

### Endpoints provided

- `/hc` \
  Healthcheck: expect an HTTP 200 OK reply if service running.
- `/update?token=‹authtoken›[&ipv4=‹ipv4›][&ipv6=‹ipv6›][&ipv6prefix=‹ipv6prefix›]` \
  Update DNS records for entries specified on service's start.

  | Parameter      | Description |
  |----------------|-------------|
  | `‹authtoken›`  | authentication token as given on service's launch |
  | `‹ipv4›`       | new IPv4 address if known; otherwise service will use an external service to try to determine address |
  | `‹ipv6›`       | new IPv6 address if known; otherwise service will use an external service to try to determine address |
  | `‹ipv6prefix›` | new IPv6 network prefix if known; if given, pass a fixed IPv6 interface address as `‹ipv6›` parameter |

## Usage

### Hosting the service

- Install service script `dyndns-hetzner-http-service.py` into `/opt/hetzner-dyndns-update/`: \
  `sudo install -m 0754 -D -t /opt/hetzner-dyndns-update dyndns-hetzner-http-service.py`
- Copy modified service file to systemd directory: \
  `sudo cp dyndns-hetzner-http-service.service /etc/systemd/system/`
- Reload systemd to recognize the new service: \
  `sudo systemctl daemon-reload`
- Enable the service to start on boot and actually start it: \
  `sudo systemctl enable --now dyndns-hetzner-http-service`
- Check status
  `sudo systemctl status dyndns-hetzner-http-service`

### Calling the service – performing a DynDNS upgrade request

Consider a common situation, running services on *local IPs* in a LAN behind a router that provides an uplink
to the outside world under a *public IP* (provided by your chosen internet provider).

In the **IPv4** case the router will probably perform NAT; in order to expose services running in the LAN there
will have to be port forwarding rules set up. Local services will then be reachable from the outside at the
*public IPv4* under a certain *port*.

In case of **IPv6** usually no NAT will take place. Updating your DNS AAA resource records with the current IPv6
will usually let them point to your router, not a host inside your LAN! Many internet service providers provide
you an /64 or /56 IPv6 network prefix, that allows making your local hosts publicly reachable with an IPv6
address constructed by combining the IPv6 network prefix with the host's IPv6 interface address.[^1]

[^1]: To provide various services it may be easiest to use subdomains in DNS and expose just one host
      and let it act as a reverse proxy, redirecting requests to their designated handling services
      based on the requested host name.

      ([NginxProxyManager](https://github.com/NginxProxyManager/nginx-proxy-manager) springs to mind.)

#### Examples

- **FritzBox**

  FritzBox uses angle-bracketed placeholders to compose the update url it uses
  once the external IP addresses change.

  In this example the local host interface `::1234:cafe:1337:abcd` will be exposed to the public internet
  using the public IPv6 network prefix:

  ```
  http://dyndns-updater.internal:8080/update?token=s73kjbsesf63vdsr3b&ipv4=<ipaddr>&ipv6=::1234:cafe:1337:abcd&ipv6prefix=<ip6lanprefix>
  ```



## License

This project is licensed under the *European Union Public Licence* version 1.2. See the LICENSE file for more details.
