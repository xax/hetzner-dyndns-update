# Hetzner ® DNS Dynamic Update Service

![Version: 3.0.0](https://img.shields.io/badge/version-3.0.0-blue.svg)
![License: EUPL-1.2](https://img.shields.io/badge/license-EUPL%201.2-272398.svg?logo=europeanunion)

An HTTP(S) service running on Python 3.13+ with no other dependencies apart from the Python Standard Library.
Updates A and AAAA DNS resource records for specified subdomains (rr_names) in given zones using the Hetzner® Cloud API.

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
- ✅ Update AAAA records with current IPv6 address (if available)
- ✅ Graceful handling when records are already up to date
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
| `DYNDNS_HHS_TOKEN` | Access token that the service will ask for | `"s73kjbsesf63vdsr3b"` |
| `DYNDYS_HHS_PASSWORD` | Password of TLS private key, if required and TLS used | "secret_password" |

### Endpoints provided

- `/hc` \
  Healthcheck: expect an HTTP 200 OK reply if service running.
- `/update?token=‹authtoken›[&ipv4=‹ipv4›][&ipv6=‹ipv6›]` \
  Update DNS records for entries specified on service's start.

  | Parameter     | Description |
  |---------------|-------------|
  | `‹authtoken›` | authentification token as given on service's launch |
  | `‹ipv4›`      | new IPv4 address if known; otherwise service will use an external service to try to determine address |
  | `‹ipv6›`      | new IPv6 address if known; otherwise service will use an external service to try to determine address |

## Usage

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

## License

This project is licensed under the *European Union Public Licence* version 1.2. See the LICENSE file for more details.
